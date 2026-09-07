"""Calcolo del ciclo frigorifero a compressione di vapore single-stage.

PROBLEMA
    Dato un regime (T_evap, T_cond, carico, surriscaldamento, sottoraffr.,
    rendimento isoentropico) e un refrigerante, calcolare i 4 stati del
    ciclo, la portata di refrigerante, le potenze e il COP.
    È la replica come libreria dello script `cycle_v2.py` del caso Thomas.

CONCETTO
    Il ciclo standard ha 4 stati:
      1: uscita evaporatore  — vapore surriscaldato a p_evap
      2: mandata compressore — vapore ad alta p (compressione reale, η_is)
      3: uscita condensatore — liquido sottoraffreddato a p_cond
      4: uscita valvola      — bifase a p_evap (espansione isoentalpica)
    CoolProp ci dà le proprietà (h, s, T, p) di ogni stato con qualità
    NIST. Tutti i bilanci sono per unità di massa, poi scalati con la
    portata m_dot = Q_evap / (h1 - h4).

SCELTE
    - Internamente CoolProp lavora in SI puro (K, Pa, J/kg). Convertiamo
      in °C, bar, kJ/kg SOLO nei risultati: gli errori di unità sono la
      prima causa di bug nei calcoli termodinamici.
    - Lo stato 2s (compressione ideale) è incluso nei risultati: serve a
      disegnare il confronto ideale/reale sul diagramma p-h.
    - Se T_cond supera la temperatura critica (es. CO2 transcritico)
      solleviamo un errore esplicito: il ciclo transcritico è fuori
      scope v0.5 e meglio un errore chiaro che un numero sbagliato.
"""

from __future__ import annotations

from CoolProp.CoolProp import PropsSI
from pydantic import BaseModel

from iazz.core.project import Refrigerant, Regime

_K = 273.15  # offset Celsius → Kelvin


class CyclePoint(BaseModel):
    """Stato termodinamico in un punto del ciclo."""

    label: str          # "1", "2s", "2", "3", "4"
    description: str
    T_C: float
    p_bar: float
    h_kJ_kg: float
    s_kJ_kgK: float


class CycleResults(BaseModel):
    """Risultati completi del calcolo di un ciclo."""

    refrigerant: str
    regime_label: str
    points: list[CyclePoint]
    m_dot_kg_s: float           # portata di refrigerante
    Q_evap_kW: float            # potenza frigorifera (= richiesta)
    Q_cond_kW: float            # potenza al condensatore (recuperabile!)
    W_comp_kW: float            # potenza assorbita dal compressore
    COP_cooling: float          # Q_evap / W
    COP_heating: float          # Q_cond / W (ottica pompa di calore)
    T_discharge_C: float        # temperatura di mandata (red flag se >120 °C)
    pressure_ratio: float       # p_cond / p_evap
    rho_suction_kg_m3: float    # densità all'aspirazione (stato 1)
    V_dot_suction_m3_h: float   # portata volumetrica aspirata — è il numero
                                # che dimensiona il compressore (F4)

    def energy_balance_error_kW(self) -> float:
        """Residuo del bilancio energetico: deve essere ~0.

        Primo principio: Q_cond = Q_evap + W_comp. Se non torna,
        c'è un bug nel calcolo — questo metodo è il nostro "allarme".
        """
        return self.Q_cond_kW - (self.Q_evap_kW + self.W_comp_kW)


def compute_cycle(refrigerant: Refrigerant, regime: Regime) -> CycleResults:
    """Calcola il ciclo a compressione di vapore per un regime dato.

    Args:
        refrigerant: refrigerante (serve `coolprop_name`).
        regime: punto operativo con T_evap, T_cond, carico, SH, SC, η_is.

    Returns:
        CycleResults con i 5 punti (1, 2s, 2, 3, 4), portate, potenze, COP.

    Raises:
        ValueError: se T_cond è sopra la temperatura critica del fluido
            (ciclo transcritico, fuori scope v0.5).
    """
    fluid = refrigerant.coolprop_name
    T_ev = regime.T_evap_C + _K
    T_cd = regime.T_cond_C + _K

    # --- Controllo transcritico (es. CO2 con T_cond > 31 °C) ---
    # NOTA: per le miscele predefinite (es. "R513A.mix") CoolProp non
    # espone "Tcrit" come proprietà banale → in quel caso saltiamo il
    # controllo esplicito e ci affidiamo al fallimento (gestito) della
    # pressione di saturazione qui sotto.
    try:
        T_crit: float | None = PropsSI("Tcrit", fluid)
    except ValueError:
        T_crit = None
    if T_crit is not None and T_cd >= T_crit:
        raise ValueError(
            f"T_cond = {regime.T_cond_C:.1f} °C è sopra la temperatura "
            f"critica di {refrigerant.name} ({T_crit - _K:.1f} °C): "
            "ciclo transcritico non supportato in v0.5."
        )

    # --- Pressioni di saturazione ---
    try:
        p_evap = PropsSI("P", "T", T_ev, "Q", 1, fluid)   # [Pa]
        p_cond = PropsSI("P", "T", T_cd, "Q", 1, fluid)   # [Pa]
    except ValueError as exc:
        raise ValueError(
            f"Impossibile calcolare la saturazione di {refrigerant.name} "
            f"a T_evap={regime.T_evap_C} °C / T_cond={regime.T_cond_C} °C: "
            "probabile ciclo transcritico o temperatura fuori range. "
            f"Dettaglio CoolProp: {exc}"
        ) from exc

    # --- Stato 1: uscita evaporatore (vapore surriscaldato) ---
    # Con SH=0 il punto (T_sat, p_sat) è ambiguo (bifase): usiamo Q=1.
    if regime.superheat_K > 1e-6:
        T1 = T_ev + regime.superheat_K
        h1 = PropsSI("H", "T", T1, "P", p_evap, fluid)
        s1 = PropsSI("S", "T", T1, "P", p_evap, fluid)
    else:
        T1 = T_ev
        h1 = PropsSI("H", "P", p_evap, "Q", 1, fluid)
        s1 = PropsSI("S", "P", p_evap, "Q", 1, fluid)

    # Densità all'aspirazione: serve per la portata volumetrica,
    # cioè la grandezza con cui si seleziona il compressore.
    rho1 = PropsSI("D", "T", T1, "P", p_evap, fluid) if regime.superheat_K > 1e-6 \
        else PropsSI("D", "P", p_evap, "Q", 1, fluid)

    # --- Stato 2s: compressione isoentropica ideale (s2s = s1) ---
    h2s = PropsSI("H", "P", p_cond, "S", s1, fluid)
    T2s = PropsSI("T", "P", p_cond, "S", s1, fluid)

    # --- Stato 2: compressione reale ---
    # Definizione di rendimento isoentropico: η = (h2s - h1) / (h2 - h1)
    h2 = h1 + (h2s - h1) / regime.eta_isentropic
    T2 = PropsSI("T", "P", p_cond, "H", h2, fluid)
    s2 = PropsSI("S", "P", p_cond, "H", h2, fluid)

    # --- Stato 3: uscita condensatore (liquido sottoraffreddato) ---
    if regime.subcooling_K > 1e-6:
        T3 = T_cd - regime.subcooling_K
        h3 = PropsSI("H", "T", T3, "P", p_cond, fluid)
        s3 = PropsSI("S", "T", T3, "P", p_cond, fluid)
    else:
        T3 = T_cd
        h3 = PropsSI("H", "P", p_cond, "Q", 0, fluid)
        s3 = PropsSI("S", "P", p_cond, "Q", 0, fluid)

    # --- Stato 4: espansione isoentalpica nella valvola (h4 = h3) ---
    h4 = h3
    T4 = PropsSI("T", "P", p_evap, "H", h4, fluid)
    s4 = PropsSI("S", "P", p_evap, "H", h4, fluid)

    # --- Bilanci ---
    q_evap = h1 - h4                                   # [J/kg]
    w_comp = h2 - h1                                   # [J/kg]
    q_cond = h2 - h3                                   # [J/kg]
    m_dot = regime.Q_evap_required_kW * 1000.0 / q_evap  # [kg/s]

    def _pt(label: str, desc: str, T: float, h: float, s: float, p: float) -> CyclePoint:
        return CyclePoint(
            label=label, description=desc,
            T_C=T - _K, p_bar=p / 1e5,
            h_kJ_kg=h / 1000.0, s_kJ_kgK=s / 1000.0,
        )

    return CycleResults(
        refrigerant=refrigerant.name,
        regime_label=regime.label,
        points=[
            _pt("1", "Uscita evaporatore (vapore SH)", T1, h1, s1, p_evap),
            _pt("2s", "Mandata ideale (isoentropica)", T2s, h2s, s1, p_cond),
            _pt("2", "Mandata compressore (reale)", T2, h2, s2, p_cond),
            _pt("3", "Uscita condensatore (liquido SC)", T3, h3, s3, p_cond),
            _pt("4", "Uscita valvola (bifase)", T4, h4, s4, p_evap),
        ],
        m_dot_kg_s=m_dot,
        Q_evap_kW=regime.Q_evap_required_kW,
        Q_cond_kW=m_dot * q_cond / 1000.0,
        W_comp_kW=m_dot * w_comp / 1000.0,
        COP_cooling=q_evap / w_comp,
        COP_heating=q_cond / w_comp,
        T_discharge_C=T2 - _K,
        pressure_ratio=p_cond / p_evap,
        rho_suction_kg_m3=rho1,
        V_dot_suction_m3_h=m_dot / rho1 * 3600.0,
    )
