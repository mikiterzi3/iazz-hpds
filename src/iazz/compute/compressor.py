"""Mappa prestazioni compressore: polinomi EN 12900 + scala in frequenza.

PROBLEMA
    Il ciclo CoolProp dice "servono 54 m³/h aspirati". I cataloghi dei
    costruttori dicono cosa eroga una macchina REALE: polinomi misurati
    Q(T_ev, T_cond), P(T_ev, T_cond), ecc. Serve un oggetto che li
    rappresenti e li valuti in modo uniforme per qualsiasi vendor.

CONCETTO
    EN 12900 definisce un polinomio cubico in due variabili:
        X = c1 + c2·Te + c3·Tc + c4·Te² + c5·Te·Tc + c6·Tc²
            + c7·Te³ + c8·Te²·Tc + c9·Te·Tc² + c10·Tc³
    con Te, Tc in °C (ATTENZIONE: °C, non K — è la convenzione dello
    standard). Per i VSD, il fit vale a una frequenza nominale; alle
    altre frequenze si scala (qui: linearmente con f/f_rated, come da
    nota Bitzer nel foglio Thomas).

    Danfoss usa in più un formato "Extended" a 30 coefficienti dove la
    velocità S è una VARIABILE del fit (vedi parsers/danfoss_xls.py):
    più accurato dello scaling lineare, perché il banco prova ha
    misurato davvero la macchina alle diverse velocità.

SCELTE
    - I dati della macchina vivono in JSON in `data/compressors/`
      (modificabili a mano), il codice è solo il valutatore: separare
      dati e logica permette di aggiungere compressori senza toccare
      codice.
    - Fuori range di validità → ValueError parlante. Un polinomio
      estrapolato fuori dal fit dà numeri plausibili ma FALSI: è il
      bug più subdolo che esista, meglio bloccarlo subito.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Cartella dati di default (relativa al pacchetto installato)
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "compressors"


def en12900(c: list[float], Te: float, Tc: float) -> float:
    """Valuta il polinomio EN 12900 (Te, Tc in °C)."""
    return (c[0] + c[1] * Te + c[2] * Tc
            + c[3] * Te**2 + c[4] * Te * Tc + c[5] * Tc**2
            + c[6] * Te**3 + c[7] * Te**2 * Tc + c[8] * Te * Tc**2
            + c[9] * Tc**3)


def danfoss_ext30(c: list[float], Te: float, Tc: float, S: float) -> float:
    """Valuta il polinomio Danfoss Extended a 30 coefficienti.

    Args:
        c: coefficienti C0..C29 (ordine del foglio Coolselector2).
        Te: temperatura di evaporazione [°C].
        Tc: temperatura di condensazione [°C].
        S: velocità del compressore in GIRI AL SECONDO (rpm/60 —
            determinato numericamente, vedi parsers/danfoss_xls.py).
    """
    return (c[0] + c[1] * Te + c[2] * Tc + c[3] * Te**2 + c[4] * Tc**2
            + c[5] * Te * Tc * S**2 + c[6] * Te**2 * Tc * S**2
            + c[7] * Te * Tc**2 * S**2
            + c[8] * Te * Tc * S + c[9] * Te**2 * Tc * S
            + c[10] * Te * Tc**2 * S
            + c[11] * Te * Tc + c[12] * Te**2 * Tc + c[13] * Te * Tc**2
            + c[14] * Te**3 + c[15] * Tc**3
            + c[16] * S + c[17] * Te * S + c[18] * Tc * S
            + c[19] * Te**2 * S + c[20] * Tc**2 * S
            + c[21] * Te**3 * S + c[22] * Tc**3 * S
            + c[23] * S**2 + c[24] * Te * S**2 + c[25] * Tc * S**2
            + c[26] * Te**2 * S**2 + c[27] * Tc**2 * S**2
            + c[28] * Te**3 * S**2 + c[29] * Tc**3 * S**2)


class CompressorPerformance(BaseModel):
    """Prestazioni della macchina in un punto (T_ev, T_cond, f)."""

    model: str
    T_evap_C: float
    T_cond_C: float
    frequency_hz: float
    Q_evap_kW: float
    P_input_kW: float
    m_dot_kg_h: float | None = None   # non tutti i fit hanno la portata
    current_A: float | None = None
    T_discharge_C: float | None = None
    COP_cooling: float
    Q_cond_kW: float           # stima: Q_evap + P_input (bilancio macchina)


class CompressorMap(BaseModel):
    """Mappa completa di un compressore (dati da JSON in data/compressors)."""

    source: str
    vendor: str
    model: str
    compressor_type: str = ""
    refrigerant: str
    vsd: bool = False
    rated_frequency_hz: float = Field(gt=0)
    frequency_min_hz: float = Field(gt=0)
    frequency_max_hz: float = Field(gt=0)
    frequency_scaling: Literal["linear", "none"] = "none"
    T_evap_range_C: tuple[float, float]
    T_cond_range_C: tuple[float, float]

    # Formato dei polinomi:
    # - "en12900":       10 coeff in (Te, Tc), dict `polynomials`
    # - "danfoss_ext30": 30 coeff in (Te, Tc, S), dict `polynomials_ext30`
    poly_format: Literal["en12900", "danfoss_ext30"] = "en12900"
    polynomials: dict[str, list[float]] = Field(default_factory=dict)
    polynomials_ext30: dict[str, list[float]] | None = None
    rpm_per_hz: float = 60.0   # giri/frequenza del motore (60 = 2 poli)

    # Condizioni di rating del fit (se note): SH/SC ai quali valgono
    # i polinomi. Il confronto col ciclo va fatto a QUESTE condizioni.
    superheat_K: float | None = None
    subcooling_K: float | None = None

    @model_validator(mode="after")
    def _check_poly_presence(self) -> "CompressorMap":
        """Il formato dichiarato deve avere i suoi coefficienti."""
        if self.poly_format == "danfoss_ext30" and not self.polynomials_ext30:
            raise ValueError(
                f"{self.model}: poly_format='danfoss_ext30' ma "
                "'polynomials_ext30' è vuoto.")
        if self.poly_format == "en12900" and not self.polynomials:
            raise ValueError(
                f"{self.model}: poly_format='en12900' ma 'polynomials' "
                "è vuoto.")
        return self

    def _check_range(self, Te: float, Tc: float, f: float) -> None:
        """Blocca le estrapolazioni fuori dal range di fit."""
        lo, hi = self.T_evap_range_C
        if not lo <= Te <= hi:
            raise ValueError(
                f"{self.model}: T_evap {Te} °C fuori dal range di validità "
                f"dei polinomi [{lo}, {hi}] °C — il fit non è estrapolabile.")
        lo, hi = self.T_cond_range_C
        if not lo <= Tc <= hi:
            raise ValueError(
                f"{self.model}: T_cond {Tc} °C fuori range [{lo}, {hi}] °C.")
        if not self.frequency_min_hz <= f <= self.frequency_max_hz:
            raise ValueError(
                f"{self.model}: frequenza {f} Hz fuori range "
                f"[{self.frequency_min_hz}, {self.frequency_max_hz}] Hz.")

    def evaluate(self, T_evap_C: float, T_cond_C: float,
                 frequency_hz: float | None = None) -> CompressorPerformance:
        """Prestazioni della macchina nel punto richiesto.

        Args:
            T_evap_C: temperatura di evaporazione [°C].
            T_cond_C: temperatura di condensazione [°C].
            frequency_hz: frequenza VSD (default: quella nominale del fit).

        Returns:
            CompressorPerformance con potenze, portata, COP.

        Raises:
            ValueError: se il punto è fuori dal range di validità del fit.
        """
        f = frequency_hz if frequency_hz is not None else self.rated_frequency_hz
        self._check_range(T_evap_C, T_cond_C, f)

        if self.poly_format == "danfoss_ext30":
            return self._evaluate_ext30(T_evap_C, T_cond_C, f)
        return self._evaluate_en12900(T_evap_C, T_cond_C, f)

    def _evaluate_en12900(self, Te: float, Tc: float,
                          f: float) -> CompressorPerformance:
        """Valutazione formato EN 12900 (+ eventuale scala in frequenza)."""
        # Scala in frequenza (nota Bitzer: Q e P lineari con f/f_rated;
        # estendiamo a m_dot e corrente — stessa fisica volumetrica).
        k = f / self.rated_frequency_hz if self.frequency_scaling == "linear" else 1.0

        def val(key: str) -> float:
            return en12900(self.polynomials[key], Te, Tc) * k

        Q_W = val("Q_evap_W")
        P_W = val("P_input_W")
        # T_disc è una temperatura: NON si scala con la frequenza.
        T_disc = (en12900(self.polynomials["T_discharge_C"], Te, Tc)
                  if "T_discharge_C" in self.polynomials else None)
        return CompressorPerformance(
            model=self.model, T_evap_C=Te, T_cond_C=Tc,
            frequency_hz=f,
            Q_evap_kW=Q_W / 1000.0,
            P_input_kW=P_W / 1000.0,
            m_dot_kg_h=(val("m_dot_kg_h")
                        if "m_dot_kg_h" in self.polynomials else None),
            current_A=val("current_A") if "current_A" in self.polynomials else None,
            T_discharge_C=T_disc,
            COP_cooling=Q_W / P_W,
            Q_cond_kW=(Q_W + P_W) / 1000.0,
        )

    def _evaluate_ext30(self, Te: float, Tc: float,
                        f: float) -> CompressorPerformance:
        """Valutazione formato Danfoss Extended (Te, Tc, S).

        Niente scala in frequenza: la velocità è una VARIABILE del fit,
        non un fattore moltiplicativo — è il vantaggio di questo formato.
        """
        assert self.polynomials_ext30 is not None
        S = f * self.rpm_per_hz / 60.0   # rev/s (vedi parsers/danfoss_xls.py)

        def val(key: str) -> float:
            return danfoss_ext30(self.polynomials_ext30[key], Te, Tc, S)

        Q_kW = val("Q_evap_kW")
        P_kW = val("P_input_kW")
        return CompressorPerformance(
            model=self.model, T_evap_C=Te, T_cond_C=Tc,
            frequency_hz=f,
            Q_evap_kW=Q_kW,
            P_input_kW=P_kW,
            m_dot_kg_h=val("m_dot_kg_h"),
            current_A=(val("current_A")
                       if "current_A" in self.polynomials_ext30 else None),
            T_discharge_C=(val("T_discharge_C")
                           if "T_discharge_C" in self.polynomials_ext30 else None),
            COP_cooling=Q_kW / P_kW,
            Q_cond_kW=Q_kW + P_kW,
        )


def load_compressor(path: str | Path) -> CompressorMap:
    """Carica una mappa compressore da JSON (ignora i campi _README)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("_README", None)
    return CompressorMap.model_validate(data)


def load_all(data_dir: str | Path = DATA_DIR) -> list[CompressorMap]:
    """Carica tutte le mappe presenti in data/compressors/<vendor>/*.json."""
    return [load_compressor(p) for p in sorted(Path(data_dir).rglob("*.json"))]
