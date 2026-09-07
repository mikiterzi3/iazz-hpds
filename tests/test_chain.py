"""Test della catena delle temperature (F4): la sintesi sul caso Thomas.

Il criterio di accettazione è nel design doc: le temperature del
ciclo devono NASCERE dai bisogni, riprodurre il caso validato, e
rendere gli assurdi fisici impossibili per costruzione.
"""

import pytest
from pydantic import ValidationError

from iazz.compute.chain import (
    ColdLink, HotSink, TemperatureChain, thomas_chain,
)
from iazz.compute.cycle import compute_cycle
from iazz.core import refrigerants

R1234ZE = refrigerants.get("R1234ze(E)")


# ----------------------------------------------------- caso fondativo

def test_thomas_chain_reproduces_excel_temperatures():
    """Dai bisogni (latte 4, acqua 19, aria 38) alle temperature
    dell'Excel: -2 / 40. La sintesi riproduce il caso validato."""
    chain = thomas_chain()
    assert chain.T_evap_C == pytest.approx(-2.0)
    assert chain.T_cond_C == pytest.approx(40.0)


def test_governing_sink_is_summer_air():
    """T_cond=40 è dettata dall'aria estiva, non dal recupero: la
    catena SPIEGA la decisione, non la subisce."""
    assert "aria" in thomas_chain().governing_sink.name


def test_chain_regime_matches_validated_cycle():
    """Il Regime costruito dalla catena produce lo stesso ciclo del
    regime A validato contro l'Excel."""
    regime = thomas_chain().to_regime("A", Q_evap_required_kW=21.76)
    res = compute_cycle(R1234ZE, regime)
    reference = compute_cycle(
        R1234ZE, thomas_chain().to_regime("rif", 21.76))
    assert res.COP_cooling == pytest.approx(reference.COP_cooling)
    assert regime.T_evap_C == -2.0 and regime.T_cond_C == 40.0


# ------------------------------------- impossibile per costruzione

def test_absurd_approach_rejected_at_construction():
    """L'assurdo del primo collaudo (T_evap sopra il target) qui non
    può nemmeno essere scritto: un approccio nullo o negativo viene
    rifiutato da pydantic PRIMA di qualsiasi calcolo."""
    with pytest.raises(ValidationError):
        ColdLink(name="impossibile", approach_K=0.0)
    with pytest.raises(ValidationError):
        ColdLink(name="impossibile", approach_K=-6.0)
    with pytest.raises(ValidationError):
        HotSink(name="impossibile", T_sink_C=19.0, approach_K=1.0)


def test_t_evap_always_below_cold_target():
    """Con qualunque catena valida, T_evap < target: è strutturale."""
    chain = TemperatureChain(
        cold_target_C=4.0,
        cold_links=[ColdLink(name="unico", approach_K=2.0)],
        hot_sinks=[HotSink(name="aria", T_sink_C=30.0, approach_K=5.0)],
    )
    assert chain.T_evap_C < chain.cold_target_C


# ------------------------------------------------------- sensibilità

def test_sensitivity_cold_links_positive():
    """Stringere un anello freddo di 1 K (T_evap su) regala COP:
    ~2-3%/K secondo L1b."""
    sens = thomas_chain().sensitivity_COP_per_K(R1234ZE)
    for name in ("latte → glicole", "glicole → evaporazione"):
        assert sens[name] > 0
        # ordine di grandezza: tra 1% e 5% del COP base (~3.7)
        assert 0.01 * 3.7 < sens[name] < 0.05 * 3.7


def test_sensitivity_saturated_and_non_governing_sinks():
    """Due verità diverse, due risposte diverse:
    - aria estiva: approccio già a 2 K = minimo fisico → None
      ("sei al limite, non c'è margine") — per Thomas è un'info di
      progetto: lato condensazione la macchina è già spremuta;
    - acqua recupero: se avesse margine, stringerla non muoverebbe
      comunque T_cond (non governante) → 0."""
    sens = thomas_chain().sensitivity_COP_per_K(R1234ZE)
    assert sens["aria estiva (condensatore aria)"] is None
    assert sens["acqua vacche (recupero)"] is None  # anche lei a 2 K

    # variante con margini: acqua a 5 K (non governante), aria a 4 K
    chain = thomas_chain().model_copy(update={"hot_sinks": [
        HotSink(name="acqua", T_sink_C=19.0, approach_K=5.0),
        HotSink(name="aria", T_sink_C=38.0, approach_K=4.0),
    ]})
    sens2 = chain.sensitivity_COP_per_K(R1234ZE)
    assert sens2["acqua"] == pytest.approx(0.0, abs=1e-9)  # non governa
    assert sens2["aria"] > 0                               # governa
