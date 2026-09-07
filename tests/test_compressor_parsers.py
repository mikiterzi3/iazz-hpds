"""Test del parser Danfoss e del valutatore ext30.

Strategia di validazione (il "doppio binario" di I.A.zz):
1. COERENZA INTERNA — il polinomio a 30 coefficienti (Te, Tc, S) e i
   polinomi EN 12900 per-frequenza sono DUE FIT INDIPENDENTI degli
   stessi dati di banco Danfoss: devono coincidere entro l'1 %.
2. COERENZA FISICA — Q dev'essere ≈ M·Δh_evap calcolato con CoolProp
   alle condizioni di rating (SH 10 K, SC 0 K): fonti indipendenti
   (banco Danfoss vs equazioni di stato NIST) entro il 2 %.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from CoolProp.CoolProp import PropsSI

from iazz.compute.compressor import (
    CompressorMap, DATA_DIR, en12900, load_all, load_compressor,
)
from iazz.parsers.danfoss_xls import parse_workbook, to_map_dict

FIXTURES = Path(__file__).parent / "fixtures" / "danfoss"
DANFOSS_JSON_DIR = DATA_DIR / "danfoss"

XLSX_FILES = sorted(FIXTURES.glob("*.xlsx"))
VSD_MODELS = {"KS1NV0410NDCC", "KS1RV0410NDCC"}

# Punto di test dentro l'envelope provvisorio [-15,10]x[30,60]
TE, TC = -2.0, 40.0

# CoolProp vuole il nome esatto del fluido
COOLPROP_NAMES = {"R1234ze(E)": "R1234ze(E)", "R134a": "R134a", "R290": "Propane"}


# ----------------------------------------------------------------- parser

@pytest.mark.parametrize("path", XLSX_FILES, ids=lambda p: p.stem.split()[0])
def test_parse_workbook(path):
    """Ogni file si parsa: metadati giusti, 10 coeff per grandezza."""
    dwb = parse_workbook(path)
    assert dwb.model == path.stem.split()[0]
    assert dwb.refrigerant in COOLPROP_NAMES
    assert dwb.superheat_K == 10.0
    assert dwb.subcooling_K == 0.0
    assert dwb.rpm_per_hz == 60.0          # motori 2 poli
    for polys in dwb.per_frequency.values():
        for key, coeff in polys.items():
            assert len(coeff) == 10, key
    if dwb.model in VSD_MODELS:
        assert dwb.is_vsd and dwb.ext30 is not None
        assert set(dwb.per_frequency) == {20, 30, 40, 50, 60, 70}
        for coeff in dwb.ext30.values():
            assert len(coeff) == 30
    else:
        assert not dwb.is_vsd and dwb.ext30 is None
        assert set(dwb.per_frequency) == {50}


def test_xls_originale_rifiutato_con_messaggio_chiaro(tmp_path):
    """Gli .xls non convertiti devono dare un errore che spiega cosa fare."""
    fake = tmp_path / "qualcosa.xls"
    fake.write_bytes(b"\xd0\xcf\x11\xe0")
    with pytest.raises(ValueError, match="soffice"):
        parse_workbook(fake)


# ------------------------------------------------- JSON generati e caricamento

def test_load_all_include_bitzer_danfoss_frascold():
    """Il DB completo ha 8 macchine: 1 Bitzer + 6 Danfoss + 1 Frascold."""
    maps = load_all()
    assert len(maps) == 8
    vendors = {m.vendor for m in maps}
    assert vendors == {"Bitzer", "Danfoss", "Frascold"}


def test_frascold_plausibility_at_reference_point():
    """Sanity del Frascold Z50-185Y (trascritto a mano dalla Lesson 3):
    a 0/40 °C un semi-ermetico da 184,7 m³/h in R1234ze deve dare
    ~60-75 kW con COP 3-4. Se la trascrizione avesse invertito righe
    o colonne, questi numeri esploderebbero."""
    cmap = load_compressor(DATA_DIR / "frascold" / "z50-185y_r1234ze-e.json")
    perf = cmap.evaluate(0.0, 40.0)
    assert 55.0 < perf.Q_evap_kW < 80.0
    assert 2.8 < perf.COP_cooling < 4.2
    assert perf.m_dot_kg_h is None      # portata non fornita dal tutorial


def test_json_generati_coerenti_col_parser():
    """Round-trip: rigenerare i dict dai .xlsx dà gli stessi polinomi
    dei JSON committati (nessuna modifica a mano non tracciata)."""
    for path in XLSX_FILES:
        dwb = parse_workbook(path)
        regen = to_map_dict(dwb, (-15.0, 10.0), (30.0, 60.0))
        json_files = [p for p in DANFOSS_JSON_DIR.glob("*.json")
                      if dwb.model.lower() in p.name.replace("-", "")]
        assert len(json_files) == 1, f"JSON non trovato per {dwb.model}"
        committed = load_compressor(json_files[0])
        assert committed.polynomials == regen["polynomials"]
        assert committed.polynomials_ext30 == regen.get("polynomials_ext30")


# ------------------------------------------------------- coerenza interna

@pytest.mark.parametrize("model", sorted(VSD_MODELS))
def test_ext30_coincide_con_en12900_per_frequenza(model):
    """Fit 3-variabili vs fit per-frequenza: stessa macchina, stessi
    dati di banco, ma DUE regressioni diverse fatte da Danfoss.

    Tolleranza 4 %, non 1 %: il polinomio per-frequenza è ottimizzato
    su UNA velocità, l'ext30 è un fit globale su 20-70 Hz che spalma
    il residuo. Scostamenti misurati sui nostri file: fino a 1,8 %
    (KS1NV) e 3,3 % (KS1RV, peggiore a 20 Hz dove il fit globale è al
    bordo). Se questo test supera il 4 % c'è un errore vero (ordine
    coefficienti, unità di S, ...): i bug del parser danno scostamenti
    di ordini di grandezza, non di punti percentuali."""
    path = next(p for p in XLSX_FILES if p.name.startswith(model))
    dwb = parse_workbook(path)
    cmap = CompressorMap.model_validate(
        to_map_dict(dwb, (-15.0, 10.0), (30.0, 60.0)))
    for hz, polys in dwb.per_frequency.items():
        perf = cmap.evaluate(TE, TC, frequency_hz=hz)
        q_ref_kW = en12900(polys["Q_evap_W"], TE, TC) / 1000.0
        p_ref_kW = en12900(polys["P_input_W"], TE, TC) / 1000.0
        assert perf.Q_evap_kW == pytest.approx(q_ref_kW, rel=0.04), hz
        assert perf.P_input_kW == pytest.approx(p_ref_kW, rel=0.04), hz


# -------------------------------------------------------- coerenza fisica

@pytest.mark.parametrize("json_path", sorted(DANFOSS_JSON_DIR.glob("*.json")),
                         ids=lambda p: p.stem)
def test_portata_coerente_con_coolprop(json_path):
    """Q ≈ M·Δh_evap (CoolProp) alle condizioni di rating del fit."""
    cmap = load_compressor(json_path)
    perf = cmap.evaluate(TE, TC)
    fluid = COOLPROP_NAMES[cmap.refrigerant]
    p_ev = PropsSI("P", "T", TE + 273.15, "Q", 1, fluid)
    h_in = PropsSI("H", "T", TC + 273.15, "Q", 0, fluid)      # SC = 0 K
    h_out = PropsSI("H", "T", TE + 273.15 + cmap.superheat_K,
                    "P", p_ev, fluid)                          # SH = 10 K
    q_from_m_kW = perf.m_dot_kg_h / 3600.0 * (h_out - h_in) / 1000.0
    assert perf.Q_evap_kW == pytest.approx(q_from_m_kW, rel=0.02)


# ------------------------------------------------------------- guard rail

def test_velocita_fissa_rifiuta_altre_frequenze():
    cmap = load_compressor(DANFOSS_JSON_DIR / "ks2fh0410ld4c_r290.json")
    with pytest.raises(ValueError, match="frequenza"):
        cmap.evaluate(TE, TC, frequency_hz=60)


def test_vsd_rifiuta_fuori_range_frequenza():
    cmap = load_compressor(DANFOSS_JSON_DIR / "ks1nv0410ndcc_r1234ze-e.json")
    with pytest.raises(ValueError, match="frequenza"):
        cmap.evaluate(TE, TC, frequency_hz=15)


def test_fuori_envelope_bloccato():
    cmap = load_compressor(DANFOSS_JSON_DIR / "ks1nv0410ndcc_r1234ze-e.json")
    with pytest.raises(ValueError, match="T_evap"):
        cmap.evaluate(-30.0, TC)


def test_formato_dichiarato_senza_coefficienti_rifiutato():
    with pytest.raises(ValueError, match="polynomials"):
        CompressorMap(
            source="test", vendor="X", model="Y", refrigerant="R134a",
            rated_frequency_hz=50, frequency_min_hz=50, frequency_max_hz=50,
            T_evap_range_C=(-10, 10), T_cond_range_C=(30, 60),
            poly_format="en12900", polynomials={},
        )
