"""Range di plausibilità e red flag sul ciclo calcolato.

PROBLEMA
    Un numero può essere matematicamente corretto e ingegneristicamente
    assurdo (T_mandata 135 °C: CoolProp la calcola senza battere ciglio,
    il compressore reale cuoce l'olio). Serve un posto UNICO dove vivono
    i range del mestiere.

CONCETTO
    Una lista di regole dichiarative → una funzione `check_cycle` che
    restituisce Flag tipizzati (info / warning / critical). La UI li
    colora; in F5 le STESSE regole entreranno nel system prompt
    dell'agente Termodinamico. Una sola fonte di verità, due usi.

SCELTE
    - I range sono conoscenza di dominio di Michele: vanno revisionati
      e raffinati da lui, non dati per scontati.
    - `Flag.code` è una stringa stabile (es. "T_DISCHARGE_HIGH"): i test
      e l'agente ragionano sui codici, non sui messaggi in italiano.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from iazz.compute.cycle import CycleResults
from iazz.core.project import Project, Regime

_K = 273.15

# Range del mestiere (DA REVISIONARE da Michele — fase F2/F5)
RANGES = {
    "T_discharge_warning_C": 110.0,   # sopra: olio sotto stress
    "T_discharge_critical_C": 125.0,  # sopra: fuori specifica quasi ovunque
    "pressure_ratio_warning": 8.0,    # sopra: valutare doppio stadio
    "superheat_min_K": 4.0,           # sotto: rischio colpi di liquido
    "superheat_max_K": 10.0,          # sopra: penalizza COP e T_mandata
    "subcooling_min_K": 2.0,          # sotto: rischio flash gas in valvola
    "eta_is_min": 0.60,               # fuori range: ipotesi da giustificare
    "eta_is_max": 0.85,
    "second_law_eff_min": 0.30,       # COP/COP_Carnot sospettosamente basso
    "second_law_eff_max": 0.75,       # ...o sospettosamente alto
    "approach_min_K": 2.0,            # ΔT minimo perché il calore fluisca
                                      # con aree di scambio realistiche
}


class Flag(BaseModel):
    """Segnalazione su un risultato: livello + codice stabile + spiegazione."""

    level: Literal["info", "warning", "critical"]
    code: str
    message: str


def check_cycle(res: CycleResults, regime: Regime,
                project: Project | None = None) -> list[Flag]:
    """Applica i range del mestiere a un ciclo calcolato.

    Args:
        res: risultati di `compute_cycle`.
        regime: il regime di input (per SH, SC, η_is).
        project: se fornito, abilita i CONTROLLI INCROCIATI col carico
            (secondo principio applicato all'impianto: il freddo deve
            stare sotto il target, il caldo sopra il pozzo). Sono i
            controlli che intercettano gli assurdi fisici che un ciclo
            "in sé corretto" non può vedere.

    Returns:
        Lista di Flag, vuota se tutto è nei range.
    """
    flags: list[Flag] = []
    R = RANGES

    # --- Controlli incrociati ciclo ↔ carichi del progetto -------------
    # Il calore fluisce spontaneamente solo da caldo a freddo: se
    # T_evap non sta SOTTO la temperatura finale del carico freddo,
    # l'evaporatore non può raffreddarlo — indipendentemente da quanti
    # circuiti intermedi (glicole ecc.) ci siano in mezzo.
    if project is not None:
        t_target = project.cold_load.T_out_C
        approach_ev = t_target - regime.T_evap_C
        if approach_ev <= 0:
            flags.append(Flag(level="critical", code="T_EVAP_ABOVE_COLD_TARGET",
                message=(f"T_evap {regime.T_evap_C:.1f} °C ≥ T finale del "
                         f"carico freddo «{project.cold_load.name}» "
                         f"({t_target:.1f} °C): FISICAMENTE IMPOSSIBILE "
                         "raffreddare il carico — il calore non risale da "
                         "solo. Abbassare T_evap sotto il target di almeno "
                         f"{R['approach_min_K']:.0f} K per ogni scambiatore "
                         "interposto.")))
        elif approach_ev < R["approach_min_K"]:
            flags.append(Flag(level="warning", code="APPROACH_EVAP_TIGHT",
                message=(f"Approccio evaporatore {approach_ev:.1f} K < "
                         f"{R['approach_min_K']:.0f} K: al limite della "
                         "fattibilità, servirebbero aree di scambio enormi; "
                         "con circuiti intermedi è di fatto insufficiente.")))

        if project.hot_load is not None:
            t_sink = project.hot_load.T_out_C
            approach_cd = regime.T_cond_C - t_sink
            if approach_cd <= 0:
                flags.append(Flag(level="critical", code="T_COND_BELOW_HOT_TARGET",
                    message=(f"T_cond {regime.T_cond_C:.1f} °C ≤ T finale del "
                             f"carico caldo «{project.hot_load.name}» "
                             f"({t_sink:.1f} °C): impossibile cedere calore "
                             "al pozzo — il recupero termico non può "
                             "scaldare oltre la T di condensazione.")))
            elif approach_cd < R["approach_min_K"]:
                flags.append(Flag(level="warning", code="APPROACH_COND_TIGHT",
                    message=(f"Approccio condensatore {approach_cd:.1f} K < "
                             f"{R['approach_min_K']:.0f} K: recupero termico "
                             "al limite, area di scambio irrealistica.")))

    # --- Temperatura di mandata ---
    if res.T_discharge_C > R["T_discharge_critical_C"]:
        flags.append(Flag(level="critical", code="T_DISCHARGE_CRITICAL",
            message=(f"T mandata {res.T_discharge_C:.0f} °C oltre "
                     f"{R['T_discharge_critical_C']:.0f} °C: fuori specifica "
                     "per quasi tutti i compressori, degrado olio rapido.")))
    elif res.T_discharge_C > R["T_discharge_warning_C"]:
        flags.append(Flag(level="warning", code="T_DISCHARGE_HIGH",
            message=(f"T mandata {res.T_discharge_C:.0f} °C sopra "
                     f"{R['T_discharge_warning_C']:.0f} °C: verificare limiti "
                     "del costruttore e raffreddamento testa.")))

    # --- Rapporto di compressione ---
    if res.pressure_ratio > R["pressure_ratio_warning"]:
        flags.append(Flag(level="warning", code="PRESSURE_RATIO_HIGH",
            message=(f"Rapporto di compressione {res.pressure_ratio:.1f} > "
                     f"{R['pressure_ratio_warning']:.0f}: η_is reale crolla, "
                     "valutare doppio stadio o economizzatore.")))

    # --- Surriscaldamento / sottoraffreddamento ---
    if regime.superheat_K < R["superheat_min_K"]:
        flags.append(Flag(level="warning", code="SUPERHEAT_LOW",
            message=(f"SH {regime.superheat_K:.1f} K < {R['superheat_min_K']:.0f} K: "
                     "rischio colpi di liquido al compressore.")))
    elif regime.superheat_K > R["superheat_max_K"]:
        flags.append(Flag(level="info", code="SUPERHEAT_HIGH",
            message=(f"SH {regime.superheat_K:.1f} K > {R['superheat_max_K']:.0f} K: "
                     "penalizza COP e alza la T di mandata.")))
    if regime.subcooling_K < R["subcooling_min_K"]:
        flags.append(Flag(level="info", code="SUBCOOLING_LOW",
            message=(f"SC {regime.subcooling_K:.1f} K < {R['subcooling_min_K']:.0f} K: "
                     "possibile flash gas a monte della valvola.")))

    # --- Rendimento isoentropico dichiarato ---
    if not (R["eta_is_min"] <= regime.eta_isentropic <= R["eta_is_max"]):
        flags.append(Flag(level="info", code="ETA_IS_UNUSUAL",
            message=(f"η_is = {regime.eta_isentropic:.2f} fuori dal range "
                     f"tipico {R['eta_is_min']}-{R['eta_is_max']}: "
                     "ipotesi da giustificare con dati del costruttore.")))

    # --- Sanity di secondo principio ---
    T_ev, T_cd = regime.T_evap_C + _K, regime.T_cond_C + _K
    cop_carnot = T_ev / (T_cd - T_ev)
    eff = res.COP_cooling / cop_carnot
    if eff < R["second_law_eff_min"]:
        flags.append(Flag(level="warning", code="SECOND_LAW_EFF_LOW",
            message=(f"COP/COP_Carnot = {eff:.2f}: ciclo molto inefficiente "
                     "rispetto al limite teorico, ricontrollare input.")))
    elif eff > R["second_law_eff_max"]:
        flags.append(Flag(level="warning", code="SECOND_LAW_EFF_HIGH",
            message=(f"COP/COP_Carnot = {eff:.2f}: sospettosamente vicino al "
                     "limite teorico, ricontrollare η_is e temperature.")))

    return flags
