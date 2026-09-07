"""Selezione compressori dal DB: la fase F6 del flusso di sintesi.

PROBLEMA
    Il ciclo dice "servono Q kW a (T_evap, T_cond)". Il DB contiene
    macchine reali con envelope e capacità quantizzate. Serve la
    risposta all'unica domanda che conta: QUALI macchine coprono il
    punto, a che frequenza, con che margine e che COP reale?

CONCETTO
    Per ogni mappa del DB:
    1. il punto (T_evap, T_cond) è dentro l'envelope? No → scartata
       (con motivo, l'utente deve vedere PERCHÉ una macchina non c'è);
    2. VSD: si cerca per bisezione la frequenza f* tale che
       Q(f*) = Q_richiesto — Q è monotona in f, la bisezione è
       garantita; velocità fissa: si valuta a 50 Hz e si guarda il
       margine;
    3. si riportano frequenza, margine, P, COP reale, T_mandata.
    L'ordinamento di default è per COP reale al punto: l'efficienza
    paga per tutta la vita dell'impianto.

SCELTE
    - La bisezione lavora su evaluate() (formato-agnostica: EN 12900
      scalato o Danfoss ext30, non le interessa).
    - Una macchina VSD che copre Q solo sopra la frequenza nominale
      resta candidata ma con nota: girare sempre al massimo consuma
      i cuscinetti — decisione all'utente, informata.
    - Il fluido deve combaciare col refrigerante del progetto: i
      polinomi valgono SOLO per il fluido del fit.
"""

from __future__ import annotations

from pydantic import BaseModel

from iazz.compute.compressor import CompressorMap, CompressorPerformance, load_all

# Tolleranza della bisezione sulla capacità [kW]
_Q_TOL_KW = 0.05


class Candidate(BaseModel):
    """Una macchina che copre il punto, coi numeri per decidere."""

    vendor: str
    model: str
    vsd: bool
    frequency_hz: float          # frequenza necessaria per Q_richiesto
    performance: CompressorPerformance
    margin_at_max: float         # Q_max_al_punto / Q_richiesto
    note: str = ""


class Rejected(BaseModel):
    """Una macchina scartata e il PERCHÉ (trasparenza verso l'utente)."""

    vendor: str
    model: str
    reason: str


class SelectionResult(BaseModel):
    candidates: list[Candidate]
    rejected: list[Rejected]


def _q_at(cmap: CompressorMap, Te: float, Tc: float, f: float) -> float:
    return cmap.evaluate(Te, Tc, frequency_hz=f).Q_evap_kW


def _solve_frequency(cmap: CompressorMap, Te: float, Tc: float,
                     Q_req_kW: float) -> float | None:
    """Bisezione: f tale che Q(f) = Q_req. None se fuori dal range.

    Q cresce con f (macchina volumetrica): se Q(f_min) > Q_req la
    macchina è sovradimensionata anche al minimo; se Q(f_max) < Q_req
    non ce la fa nemmeno al massimo.
    """
    f_lo, f_hi = cmap.frequency_min_hz, cmap.frequency_max_hz
    q_lo, q_hi = _q_at(cmap, Te, Tc, f_lo), _q_at(cmap, Te, Tc, f_hi)
    if Q_req_kW < q_lo - _Q_TOL_KW or Q_req_kW > q_hi + _Q_TOL_KW:
        return None
    for _ in range(60):
        f_mid = 0.5 * (f_lo + f_hi)
        q_mid = _q_at(cmap, Te, Tc, f_mid)
        if abs(q_mid - Q_req_kW) < _Q_TOL_KW:
            return f_mid
        if q_mid < Q_req_kW:
            f_lo = f_mid
        else:
            f_hi = f_mid
    return 0.5 * (f_lo + f_hi)


def select_compressors(T_evap_C: float, T_cond_C: float, Q_req_kW: float,
                       refrigerant_name: str,
                       maps: list[CompressorMap] | None = None,
                       ) -> SelectionResult:
    """Interroga il DB: chi copre (T_evap, T_cond, Q_req) con questo fluido?

    Args:
        T_evap_C, T_cond_C: punto di lavoro (dalla catena F4).
        Q_req_kW: capacità frigorifera richiesta al regime dimensionante.
        refrigerant_name: fluido del progetto (deve combaciare col fit).
        maps: mappe da considerare (default: tutto il DB su disco).

    Returns:
        SelectionResult: candidate ordinate per COP reale decrescente
        + scartate con motivo.
    """
    maps = maps if maps is not None else load_all()
    candidates: list[Candidate] = []
    rejected: list[Rejected] = []

    for cmap in maps:
        def skip(reason: str) -> None:
            rejected.append(Rejected(vendor=cmap.vendor, model=cmap.model,
                                     reason=reason))

        if cmap.refrigerant != refrigerant_name:
            skip(f"fluido del fit: {cmap.refrigerant} ≠ {refrigerant_name}")
            continue

        lo, hi = cmap.T_evap_range_C
        if not lo <= T_evap_C <= hi:
            skip(f"T_evap {T_evap_C:.1f} °C fuori envelope [{lo}, {hi}]")
            continue
        lo, hi = cmap.T_cond_range_C
        if not lo <= T_cond_C <= hi:
            skip(f"T_cond {T_cond_C:.1f} °C fuori envelope [{lo}, {hi}]")
            continue

        q_max = _q_at(cmap, T_evap_C, T_cond_C, cmap.frequency_max_hz)
        if q_max + _Q_TOL_KW < Q_req_kW:
            skip(f"capacità insufficiente: {q_max:.1f} kW alla frequenza "
                 f"massima < {Q_req_kW:.1f} kW richiesti")
            continue

        if cmap.vsd:
            f_star = _solve_frequency(cmap, T_evap_C, T_cond_C, Q_req_kW)
            if f_star is None:
                q_min = _q_at(cmap, T_evap_C, T_cond_C,
                              cmap.frequency_min_hz)
                skip(f"sovradimensionata: eroga {q_min:.1f} kW già alla "
                     f"frequenza minima (> {Q_req_kW:.1f} kW richiesti); "
                     "lavorerebbe a cicli on/off")
                continue
            note = ""
            if f_star > cmap.rated_frequency_hz:
                note = (f"copre il carico solo sopra la frequenza nominale "
                        f"({cmap.rated_frequency_hz:.0f} Hz): margine di "
                        "riserva ridotto")
        else:
            f_star = cmap.rated_frequency_hz
            note = ""
            over = q_max / Q_req_kW
            if over > 1.5:
                note = (f"velocità fissa sovradimensionata del "
                        f"{(over - 1) * 100:.0f}%: valutare parzializzazione "
                        "o accumulo")

        perf = cmap.evaluate(T_evap_C, T_cond_C, frequency_hz=f_star)
        candidates.append(Candidate(
            vendor=cmap.vendor, model=cmap.model, vsd=cmap.vsd,
            frequency_hz=round(f_star, 1), performance=perf,
            margin_at_max=q_max / Q_req_kW, note=note))

    candidates.sort(key=lambda c: c.performance.COP_cooling, reverse=True)
    return SelectionResult(candidates=candidates, rejected=rejected)
