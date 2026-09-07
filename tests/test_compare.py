"""Test del confronto multi-refrigerante sul regime A di Thomas."""

from iazz.compute.compare import compare_refrigerants
from iazz.core.project import Regime

REGIME_A = Regime(label="A", T_evap_C=-2, T_cond_C=40,
                  Q_evap_required_kW=21.76)


def test_all_db_fluids_present():
    rows = compare_refrigerants(REGIME_A)
    assert len(rows) == 6  # tutto il DB v0.5


def test_sorted_by_cop_with_failures_last():
    rows = compare_refrigerants(REGIME_A)
    cops = [r.COP_cooling for r in rows if r.COP_cooling is not None]
    assert cops == sorted(cops, reverse=True)
    assert rows[-1].error is not None          # la CO2 transcritica in coda
    assert "R744" in rows[-1].refrigerant


def test_subset_selection():
    rows = compare_refrigerants(REGIME_A, names=["R1234ze(E)", "R290"])
    assert len(rows) == 2
    assert all(r.COP_cooling is not None for r in rows)
