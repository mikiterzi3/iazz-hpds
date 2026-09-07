"""Test della selezione compressori (F6) sul DB reale (7 macchine).

Punto di prova: il regime A di Thomas derivato dalla catena F4
(-2 °C / 40 °C, 21,76 kW, R1234ze(E)).
"""

import pytest

from iazz.compute.chain import thomas_chain
from iazz.compute.selection import select_compressors

TE, TC = -2.0, 40.0
Q_REQ = 21.76
FLUID = "R1234ze(E)"


@pytest.fixture(scope="module")
def result():
    chain = thomas_chain()
    return select_compressors(chain.T_evap_C, chain.T_cond_C,
                              Q_REQ, FLUID)


def test_bitzer_thomas_is_candidate(result):
    """La macchina realmente scelta nel progetto Thomas deve uscire
    candidata: è il test di realtà dell'intero motore di selezione."""
    models = [c.model for c in result.candidates]
    assert "4NES-14Y-40P" in models


def test_bitzer_frequency_and_capacity(result):
    """La bisezione trova una frequenza nel range VSD e la capacità
    al punto coincide con la richiesta (entro tolleranza)."""
    bitzer = next(c for c in result.candidates if c.model == "4NES-14Y-40P")
    assert 25.0 <= bitzer.frequency_hz <= 70.0
    assert bitzer.performance.Q_evap_kW == pytest.approx(Q_REQ, abs=0.1)
    assert bitzer.performance.COP_cooling > 2.5


def test_wrong_fluid_machines_rejected_with_reason(result):
    """R134a e R290 non possono candidarsi su un progetto R1234ze:
    i polinomi valgono solo per il fluido del fit."""
    reasons = {r.model: r.reason for r in result.rejected}
    assert any("R134a" in reasons[m] for m in reasons
               if m.startswith("KS1RV") or m.startswith("KS2RH"))
    assert any("R290" in reasons[m] for m in reasons
               if m.startswith("KS2FH"))


def test_oversized_vsd_rejected_with_explanation(result):
    """Il Danfoss KS1NV (60-240 kW) eroga troppo anche alla frequenza
    minima per un carico da 22 kW: scartato con motivo parlante, non
    sparito in silenzio."""
    reasons = {r.model: r.reason for r in result.rejected}
    if "KS1NV0410NDCC" in reasons:
        assert "sovradimensionata" in reasons["KS1NV0410NDCC"]
    else:
        # se mai candidata, deve almeno portare una nota di allarme
        cand = next(c for c in result.candidates
                    if c.model == "KS1NV0410NDCC")
        assert cand.note != ""


def test_candidates_sorted_by_real_cop(result):
    cops = [c.performance.COP_cooling for c in result.candidates]
    assert cops == sorted(cops, reverse=True)


def test_every_db_machine_is_either_candidate_or_rejected(result):
    """Nessuna macchina sparisce: 8 nel DB = candidate + scartate."""
    assert len(result.candidates) + len(result.rejected) == 8


def test_frascold_candidate_but_oversized_at_thomas_point(result):
    """Il Frascold copre il punto Thomas (-2/40 dentro l'envelope)
    ma eroga ~62 kW contro 21,76 richiesti: candidato con nota di
    sovradimensionamento, non scartato in silenzio."""
    fra = [c for c in result.candidates if c.model == "Z50-185Y"]
    assert fra and "sovradimensionata" in fra[0].note
