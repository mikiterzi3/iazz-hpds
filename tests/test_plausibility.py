"""Test dei red flag: il caso Thomas deve essere pulito, i casi
volutamente estremi devono accendere le spie giuste."""

from pathlib import Path

from iazz.compute.cycle import compute_cycle
from iazz.compute.plausibility import check_cycle
from iazz.core import refrigerants
from iazz.core.project import Project, Regime

R1234ZE = refrigerants.get("R1234ze(E)")
R717 = refrigerants.get("R717")

THOMAS_JSON = (Path(__file__).parent.parent / "examples"
               / "thomas_chiller.json")


def _codes(flags):
    return {f.code for f in flags}


def _thomas() -> Project:
    return Project.load_json(THOMAS_JSON)


def test_thomas_regime_a_is_clean():
    """Il caso fondativo non deve avere warning/critical."""
    regime = Regime(label="A", T_evap_C=-2, T_cond_C=40,
                    Q_evap_required_kW=21.76)
    flags = check_cycle(compute_cycle(R1234ZE, regime), regime)
    assert not [f for f in flags if f.level in ("warning", "critical")]


def test_ammonia_high_lift_flags_discharge():
    """NH3 con grande salto: la T di mandata schizza → spia accesa.

    L'ammoniaca ha un esponente isoentropico alto: è IL caso classico
    di T_discharge proibitiva, perfetto per testare la regola.
    """
    regime = Regime(label="estremo", T_evap_C=-20, T_cond_C=45,
                    Q_evap_required_kW=20)
    flags = check_cycle(compute_cycle(R717, regime), regime)
    assert _codes(flags) & {"T_DISCHARGE_HIGH", "T_DISCHARGE_CRITICAL"}


def test_low_superheat_flagged():
    regime = Regime(label="sh basso", T_evap_C=-2, T_cond_C=40,
                    Q_evap_required_kW=20, superheat_K=1.0)
    flags = check_cycle(compute_cycle(R1234ZE, regime), regime)
    assert "SUPERHEAT_LOW" in _codes(flags)


def test_extreme_pressure_ratio_flagged():
    regime = Regime(label="salto enorme", T_evap_C=-35, T_cond_C=55,
                    Q_evap_required_kW=20)
    flags = check_cycle(compute_cycle(R1234ZE, regime), regime)
    assert "PRESSURE_RATIO_HIGH" in _codes(flags)


def test_unusual_eta_flagged():
    regime = Regime(label="eta strano", T_evap_C=-2, T_cond_C=40,
                    Q_evap_required_kW=20, eta_isentropic=0.95)
    flags = check_cycle(compute_cycle(R1234ZE, regime), regime)
    assert "ETA_IS_UNUSUAL" in _codes(flags)


# ------------------- controlli incrociati ciclo ↔ carichi del progetto
# Nati dal collaudo di Michele (2026-07-13): T_evap sopra la temperatura
# target del latte passava senza alcun avviso. Mai più.

def test_milk_case_t_evap_above_target_is_critical():
    """T_evap = +8 °C con latte da portare a 4 °C: assurdo fisico.

    È il caso esatto trovato da Michele al primo collaudo: il calore
    non fluisce dal latte (4 °C) a un evaporatore più caldo (8 °C).
    Deve scattare un CRITICAL, sempre, senza AI di mezzo.
    """
    project = _thomas()
    regime = Regime(label="assurdo", T_evap_C=8.0, T_cond_C=40,
                    Q_evap_required_kW=20)
    flags = check_cycle(compute_cycle(R1234ZE, regime), regime,
                        project=project)
    critical = [f for f in flags if f.code == "T_EVAP_ABOVE_COLD_TARGET"]
    assert critical and critical[0].level == "critical"


def test_tight_evap_approach_is_warned():
    """T_evap a 3 °C con target 4 °C: possibile ma irrealistico (1 K)."""
    project = _thomas()
    regime = Regime(label="stretto", T_evap_C=3.0, T_cond_C=40,
                    Q_evap_required_kW=20)
    flags = check_cycle(compute_cycle(R1234ZE, regime), regime,
                        project=project)
    assert "APPROACH_EVAP_TIGHT" in _codes(flags)


def test_t_cond_below_hot_target_is_critical():
    """T_cond = 15 °C con acqua vacche da scaldare a 19 °C: il recupero
    termico non può scaldare oltre la T di condensazione."""
    project = _thomas()
    regime = Regime(label="cond bassa", T_evap_C=-5, T_cond_C=15.0,
                    Q_evap_required_kW=20)
    flags = check_cycle(compute_cycle(R1234ZE, regime), regime,
                        project=project)
    assert "T_COND_BELOW_HOT_TARGET" in _codes(flags)


def test_thomas_regimes_stay_clean_with_project_checks():
    """I controlli incrociati NON devono accendersi sul caso validato:
    regime A (-2/40) ha approccio 6 K sul latte e 21 K sull'acqua."""
    project = _thomas()
    for regime in project.regimes:
        flags = check_cycle(compute_cycle(R1234ZE, regime), regime,
                            project=project)
        assert not [f for f in flags if f.level in ("warning", "critical")], \
            f"flag inattesi su {regime.label}: {_codes(flags)}"


def test_without_project_no_cross_checks():
    """Senza project i controlli incrociati restano spenti (modalità
    analisi pura): stesso ciclo assurdo, nessun flag di cross-check."""
    regime = Regime(label="assurdo", T_evap_C=8.0, T_cond_C=40,
                    Q_evap_required_kW=20)
    flags = check_cycle(compute_cycle(R1234ZE, regime), regime)
    assert "T_EVAP_ABOVE_COLD_TARGET" not in _codes(flags)
