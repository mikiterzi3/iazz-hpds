"""Confronto multi-refrigerante sullo stesso regime.

PROBLEMA
    La domanda vera del progettista non è "che COP ha R1234ze?" ma
    "tra R1234ze, R290 e R134a, su QUESTO regime, chi vince e a che
    prezzo (GWP, sicurezza, pressioni)?".

CONCETTO
    Stessa `Regime`, N fluidi → una riga di sintesi per fluido,
    ordinata per COP. I fluidi non calcolabili (es. CO2 transcritica)
    NON spariscono in silenzio: compaiono con il motivo dell'esclusione.
    Regola di progetto: mai nascondere un fallimento, sempre spiegarlo.
"""

from __future__ import annotations

from pydantic import BaseModel

from iazz.compute.cycle import compute_cycle
from iazz.core import refrigerants
from iazz.core.project import Regime


class ComparisonRow(BaseModel):
    """Riga di sintesi del confronto per un refrigerante."""

    refrigerant: str
    GWP100: int
    safety_class: str
    COP_cooling: float | None = None
    COP_heating: float | None = None
    Q_cond_kW: float | None = None
    W_comp_kW: float | None = None
    T_discharge_C: float | None = None
    p_evap_bar: float | None = None
    p_cond_bar: float | None = None
    pressure_ratio: float | None = None
    error: str | None = None          # motivo se il calcolo è impossibile


def compare_refrigerants(
    regime: Regime, names: list[str] | None = None
) -> list[ComparisonRow]:
    """Calcola lo stesso regime con più refrigeranti e ordina per COP.

    Args:
        regime: punto operativo comune a tutti i fluidi.
        names: nomi dei refrigeranti (default: tutto il DB).

    Returns:
        Righe ordinate per COP decrescente; in coda i fluidi non
        calcolabili, con il motivo in `error`.
    """
    rows: list[ComparisonRow] = []
    for name in names or sorted(refrigerants.REFRIGERANTS):
        ref = refrigerants.get(name)
        base = dict(refrigerant=ref.name, GWP100=ref.GWP100,
                    safety_class=ref.safety_class)
        try:
            res = compute_cycle(ref, regime)
        except ValueError as exc:
            rows.append(ComparisonRow(**base, error=str(exc)))
            continue
        p_by_label = {p.label: p for p in res.points}
        rows.append(ComparisonRow(
            **base,
            COP_cooling=round(res.COP_cooling, 3),
            COP_heating=round(res.COP_heating, 3),
            Q_cond_kW=round(res.Q_cond_kW, 2),
            W_comp_kW=round(res.W_comp_kW, 2),
            T_discharge_C=round(res.T_discharge_C, 1),
            p_evap_bar=round(p_by_label["1"].p_bar, 3),
            p_cond_bar=round(p_by_label["2"].p_bar, 3),
            pressure_ratio=round(res.pressure_ratio, 2),
        ))
    rows.sort(key=lambda r: (r.COP_cooling is None, -(r.COP_cooling or 0)))
    return rows
