"""Test del compute engine del ciclo termodinamico.

Strategia di validazione a 2 livelli:
1. FISICA: bilancio energetico, T_discharge > T_cond, COP < COP_Carnot.
   Devono valere per QUALSIASI input sensato.
2. CASO THOMAS: i 2 regimi del caso fondativo devono dare numeri
   plausibili e coerenti (validazione fine contro l'Excel HP_THOM
   quando verrà caricato come fixture).
"""

import pytest

from iazz.compute.cycle import compute_cycle
from iazz.core import refrigerants
from iazz.core.project import Regime

R1234ZE = refrigerants.get("R1234ze(E)")

REGIME_A = Regime(label="A worst", T_evap_C=-2, T_cond_C=40,
                  Q_evap_required_kW=21.76)
REGIME_B = Regime(label="B alleggerito", T_evap_C=2, T_cond_C=40,
                  Q_evap_required_kW=15.06)


@pytest.mark.parametrize("regime", [REGIME_A, REGIME_B], ids=["A", "B"])
def test_energy_balance(regime):
    """Primo principio: Q_cond = Q_evap + W (entro 0.1%)."""
    res = compute_cycle(R1234ZE, regime)
    assert abs(res.energy_balance_error_kW()) < 0.001 * res.Q_cond_kW


@pytest.mark.parametrize("regime", [REGIME_A, REGIME_B], ids=["A", "B"])
def test_cop_below_carnot(regime):
    """Secondo principio: COP reale < COP di Carnot tra le stesse T."""
    res = compute_cycle(R1234ZE, regime)
    T_ev, T_cd = regime.T_evap_C + 273.15, regime.T_cond_C + 273.15
    cop_carnot = T_ev / (T_cd - T_ev)
    assert 0 < res.COP_cooling < cop_carnot


def test_regime_a_plausibility():
    """Regime A Thomas: il COP di ciclo deve stare in un range credibile.

    NOTA: il COP Bitzer reale è 3.53 e include perdite elettriche/
    meccaniche; il COP di ciclo con η_is=0.70 è leggermente diverso.
    Il confronto esatto con l'Excel arriverà in F7 (fixture HP_THOM).
    """
    res = compute_cycle(R1234ZE, REGIME_A)
    assert 2.5 < res.COP_cooling < 4.5
    assert res.T_discharge_C > 40          # mandata sopra T_cond
    assert res.T_discharge_C < 120         # red flag oltre 120 °C
    assert 2.0 < res.pressure_ratio < 5.0  # tipico per questi salti
    assert res.m_dot_kg_s > 0


def test_regime_b_better_cop_than_a():
    """T_evap più alta a pari T_cond → salto minore → COP migliore."""
    res_a = compute_cycle(R1234ZE, REGIME_A)
    res_b = compute_cycle(R1234ZE, REGIME_B)
    assert res_b.COP_cooling > res_a.COP_cooling


def test_heat_recovery_potential():
    """Il calore al condensatore (recuperabile per l'acqua delle
    vacche) deve superare il carico frigorifero."""
    res = compute_cycle(R1234ZE, REGIME_A)
    assert res.Q_cond_kW > res.Q_evap_kW


@pytest.mark.parametrize("name", sorted(refrigerants.REFRIGERANTS))
def test_all_refrigerants_work_in_coolprop(name):
    """Ogni fluido del DB deve essere calcolabile da CoolProp.

    Per la CO2 (T_crit = 31 °C) un regime con T_cond = 40 °C è
    transcritico: ci aspettiamo l'errore esplicito, non un numero.
    (R513A è escluso dal DB v0.5: CoolProp non fa il flash P-s
    sulle miscele — vedi nota in core/refrigerants.py.)
    """
    ref = refrigerants.get(name)
    regime = Regime(label="std", T_evap_C=-2, T_cond_C=40,
                    Q_evap_required_kW=20)
    if name == "R744":
        with pytest.raises(ValueError, match="transcritico"):
            compute_cycle(ref, regime)
    else:
        res = compute_cycle(ref, regime)
        assert res.COP_cooling > 1.0
