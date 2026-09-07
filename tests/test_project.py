"""Test del modello dati Project.

Verifichiamo le 3 promesse di pydantic: validazione, round-trip JSON,
errori parlanti su dati assurdi.
"""

import pytest
from pydantic import ValidationError

from iazz.core.project import FluidTarget, Project, Regime
from iazz.core import refrigerants


def _thomas_project() -> Project:
    """Fixture: il caso fondativo Thomas (500 vacche)."""
    return Project(
        name="Chiller Thomas 500 vacche",
        refrigerant=refrigerants.get("R1234ze(E)"),
        cold_load=FluidTarget(
            name="Latte mungitura", fluid_type="milk",
            flow_rate_kg_s=0.4292, cp_kJ_kgK=3.9, T_in_C=35, T_out_C=4,
        ),
        hot_load=FluidTarget(
            name="Acqua vacche", fluid_type="water",
            flow_rate_kg_s=0.724, cp_kJ_kgK=4.186, T_in_C=12, T_out_C=19,
        ),
        regimes=[
            Regime(label="A worst 4°C", T_evap_C=-2, T_cond_C=40,
                   Q_evap_required_kW=21.76),
            Regime(label="B alleggerito 8°C", T_evap_C=2, T_cond_C=40,
                   Q_evap_required_kW=15.06),
        ],
        architecture="precooler_glycol_dual_condenser",
    )


def test_project_creation():
    p = _thomas_project()
    assert p.refrigerant.GWP100 == 7
    assert len(p.regimes) == 2


def test_cold_load_power():
    """Il carico latte deve dare ~51.9 kW (0.4292 * 3.9 * 31)."""
    p = _thomas_project()
    assert p.cold_load.Q_kW == pytest.approx(51.9, rel=0.01)


def test_json_round_trip(tmp_path):
    """Salva → ricarica → deve essere identico."""
    p = _thomas_project()
    path = tmp_path / "thomas.json"
    p.save_json(path)
    p2 = Project.load_json(path)
    assert p2 == p


def test_negative_flow_rate_rejected():
    """Una portata negativa è un errore di input, non un calcolo da fare."""
    with pytest.raises(ValidationError):
        FluidTarget(name="x", fluid_type="water", flow_rate_kg_s=-1,
                    cp_kJ_kgK=4.186, T_in_C=10, T_out_C=5)


def test_tcond_below_tevap_rejected():
    """T_cond <= T_evap: ciclo fisicamente impossibile."""
    with pytest.raises(ValidationError):
        Regime(label="impossibile", T_evap_C=40, T_cond_C=-2,
               Q_evap_required_kW=10)


def test_unknown_refrigerant_has_helpful_error():
    with pytest.raises(KeyError, match="Disponibili"):
        refrigerants.get("R22")  # obsoleto, fuori scope


# ---------------------------------------------------------------------------
# F1 — carichi derivati e simultaneity check
# ---------------------------------------------------------------------------

def test_q_cold_design():
    p = _thomas_project()
    assert p.Q_cold_design_kW == pytest.approx(51.9, rel=0.01)


def test_q_hot_design_positive():
    """L'acqua delle vacche si scalda 12→19 °C: heating_Q_kW > 0."""
    p = _thomas_project()
    assert p.Q_hot_design_kW == pytest.approx(0.724 * 4.186 * 7, rel=0.01)


def test_simultaneity_thomas():
    """Nel caso Thomas il recupero medio copre la richiesta calda."""
    p = _thomas_project()
    chk = p.simultaneity_check()
    assert chk["recovery_covers_hot_load"] is True
    assert chk["Q_cond_estimated_kW"] > chk["Q_hot_kW"]


def test_simultaneity_without_hot_load():
    p = _thomas_project()
    p2 = p.model_copy(update={"hot_load": None})
    assert p2.Q_hot_design_kW == 0.0
    assert p2.simultaneity_check()["recovery_covers_hot_load"] is True


# ---------------------------------------------------------------------------
# F1 — property-based testing con hypothesis: il computer cerca i casi
# limite al posto nostro, generando centinaia di input casuali.
# ---------------------------------------------------------------------------

from hypothesis import given, strategies as st


@given(
    T_evap=st.floats(min_value=-40, max_value=19),
    dT=st.floats(min_value=0.5, max_value=60),
)
def test_regime_accepts_any_physical_pair(T_evap, dT):
    """Qualsiasi coppia con T_cond > T_evap deve essere accettata."""
    r = Regime(label="hp", T_evap_C=T_evap, T_cond_C=T_evap + dT,
               Q_evap_required_kW=10)
    assert r.T_cond_C > r.T_evap_C


@given(
    m=st.floats(min_value=0.001, max_value=100),
    cp=st.floats(min_value=0.5, max_value=10),
    T_in=st.floats(min_value=-30, max_value=90),
    dT=st.floats(min_value=-50, max_value=50),
)
def test_fluidtarget_q_sign_convention(m, cp, T_in, dT):
    """Q_kW > 0 sse il fluido si raffredda; heating_Q_kW è l'opposto."""
    f = FluidTarget(name="x", fluid_type="water", flow_rate_kg_s=m,
                    cp_kJ_kgK=cp, T_in_C=T_in, T_out_C=T_in - dT)
    assert f.Q_kW == pytest.approx(-f.heating_Q_kW)
    # NOTA DIDATTICA: la prima versione diceva "if dT > 0: Q > 0" e
    # hypothesis l'ha SMENTITA al primo colpo: con dT piccolissimo,
    # in virgola mobile T_in - dT == T_in, quindi Q == 0. La proprietà
    # onesta si scrive sulle temperature effettivamente memorizzate:
    if f.T_in_C > f.T_out_C:
        assert f.Q_kW > 0  # si raffredda
