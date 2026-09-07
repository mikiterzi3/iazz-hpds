"""Validazione contro l'Excel del caso Thomas (HP_THOM_v2.4.xlsx).

È il test più importante del progetto: I.A.zz deve riprodurre i numeri
del progetto reale consegnato. I valori attesi e le tolleranze NON sono
nel codice ma in `tests/fixtures/thomas_expected.json`, modificabile a
mano — se un valore va aggiornato, si tocca il JSON e si documenta in
`docs/validation_thomas.md`, non si riscrive il test.
"""

import json
from pathlib import Path

import pytest

from iazz.compute.compressor import load_all
from iazz.compute.cycle import compute_cycle
from iazz.core import refrigerants
from iazz.core.project import Regime

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "thomas_expected.json")
    .read_text(encoding="utf-8"))


def _assert_within(actual: float, spec: dict, label: str) -> None:
    value, tol = spec["value"], spec["tol_pct"]
    assert actual == pytest.approx(value, rel=tol / 100.0), (
        f"{label}: atteso {value} ±{tol}% (fixture), calcolato {actual:.5g}. "
        "Se il nuovo valore è giustificato, aggiorna la fixture e "
        "documenta in docs/validation_thomas.md.")


# ---------------------------------------------------------------- ciclo
@pytest.mark.parametrize("regime_key", ["A", "B"])
def test_cycle_matches_excel(regime_key):
    fx = FIXTURES["regimes"][regime_key]
    regime = Regime(label=regime_key, **fx["input"])
    res = compute_cycle(refrigerants.get(FIXTURES["refrigerant"]), regime)

    pts = {p.label: p for p in res.points}
    actual = {
        "p_evap_bar": pts["1"].p_bar,
        "p_cond_bar": pts["2"].p_bar,
        "pressure_ratio": res.pressure_ratio,
        "h1_kJ_kg": pts["1"].h_kJ_kg,
        "h2s_kJ_kg": pts["2s"].h_kJ_kg,
        "h2_kJ_kg": pts["2"].h_kJ_kg,
        "h3_kJ_kg": pts["3"].h_kJ_kg,
        "T_discharge_C": res.T_discharge_C,
        "COP_cooling": res.COP_cooling,
        "COP_heating": res.COP_heating,
        "m_dot_kg_s": res.m_dot_kg_s,
        "W_comp_kW": res.W_comp_kW,
        "Q_cond_kW": res.Q_cond_kW,
        "rho_suction_kg_m3": res.rho_suction_kg_m3,
        "V_dot_suction_m3_h": res.V_dot_suction_m3_h,
    }
    for key, spec in fx["expected"].items():
        _assert_within(actual[key], spec, f"regime {regime_key} / {key}")


# ----------------------------------------------------------- compressore
@pytest.fixture(scope="module")
def bitzer():
    maps = [m for m in load_all() if m.model == "4NES-14Y-40P"]
    assert maps, "JSON Bitzer non trovato in data/compressors/"
    return maps[0]


@pytest.mark.parametrize("case_key", ["what_if_design_point",
                                      "regime_B_33hz",
                                      "catalog_design_point_56hz"])
def test_compressor_matches_excel(bitzer, case_key):
    case = FIXTURES["compressor_bitzer"][case_key]
    perf = bitzer.evaluate(**case["input"])
    for key, spec in case["expected"].items():
        _assert_within(getattr(perf, key), spec, f"{case_key} / {key}")


def test_compressor_out_of_range_raises(bitzer):
    """Estrapolare i polinomi fuori fit è vietato per design."""
    with pytest.raises(ValueError, match="fuori"):
        bitzer.evaluate(-30, 40)            # T_evap sotto il range
    with pytest.raises(ValueError, match="Hz"):
        bitzer.evaluate(-2, 40, frequency_hz=80)


# -------------------------------------------- cross-validation dei binari
def test_cross_validation_cycle_vs_polynomial(bitzer):
    """I due binari indipendenti (CoolProp vs catalogo Bitzer) devono
    raccontare la stessa storia al punto di progetto.

    La portata massica del ciclo (a pari Q) e quella del polinomio
    devono stare entro il 5%: è il check che in F4 diventerà una
    feature del tool (e un red flag dell'agente AI quando sfora).
    """
    regime = Regime(label="A", **FIXTURES["regimes"]["A"]["input"])
    cycle = compute_cycle(refrigerants.get(FIXTURES["refrigerant"]), regime)
    perf = bitzer.evaluate(-2, 40, frequency_hz=56)

    m_cycle_kg_h = cycle.m_dot_kg_s * 3600
    diff_pct = abs(m_cycle_kg_h - perf.m_dot_kg_h) / perf.m_dot_kg_h * 100
    assert diff_pct < 5.0, (
        f"Portata ciclo {m_cycle_kg_h:.1f} kg/h vs polinomio "
        f"{perf.m_dot_kg_h:.1f} kg/h: scostamento {diff_pct:.1f}% > 5%")
