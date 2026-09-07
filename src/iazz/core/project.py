"""Modello dati centrale del progetto I.A.zz.

PROBLEMA
    Tutti i moduli del tool (ciclo, compressore, scambiatori, economia)
    devono leggere e scrivere gli stessi dati senza pestarsi i piedi.
    Nell'Excel di Thomas questo ruolo lo facevano i fogli 2_INPUT_GLOBALE
    e 3_REGIMI: una "fonte unica di verità".

CONCETTO
    Definiamo una classe `Project` che contiene TUTTO lo stato di un
    progetto. Usiamo pydantic, che ci regala tre cose:
    1. Validazione automatica (una portata negativa solleva subito errore)
    2. Serializzazione JSON gratis (salva/carica progetto con 1 riga)
    3. Documentazione implicita: i tipi dicono cosa è ogni campo

SCELTE
    - Unità SI con suffisso nel nome campo (es. `flow_rate_kg_s`): il
      nome stesso documenta l'unità, niente ambiguità °C vs K.
    - `Regime` è una lista: un chiller reale lavora in più punti operativi
      (caso Thomas: regime A "worst" e regime B "alleggerito").
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class FluidTarget(BaseModel):
    """Carico termico generico: latte, acqua, glicole, aria...

    Rappresenta "cosa devo raffreddare/scaldare": un fluido con portata,
    calore specifico e temperature di ingresso/uscita.
    """

    name: str
    fluid_type: Literal["water", "milk", "glycol30", "air", "brine"]
    flow_rate_kg_s: float = Field(gt=0, description="Portata massica [kg/s]")
    cp_kJ_kgK: float = Field(gt=0, description="Calore specifico [kJ/(kg K)]")
    T_in_C: float
    T_out_C: float

    @property
    def Q_kW(self) -> float:
        """Potenza termica scambiata [kW] (positiva = raffreddamento)."""
        return self.flow_rate_kg_s * self.cp_kJ_kgK * (self.T_in_C - self.T_out_C)

    @property
    def heating_Q_kW(self) -> float:
        """Potenza di riscaldamento [kW] (positiva = il fluido si scalda).

        È semplicemente -Q_kW: definiamo ENTRAMBE le viste perché un
        carico caldo letto come "raffreddamento negativo" è una fonte
        classica di errori di segno.
        """
        return -self.Q_kW


class Regime(BaseModel):
    """Punto operativo del chiller (es. regime A worst case, B alleggerito)."""

    label: str
    T_evap_C: float = Field(description="Temperatura di evaporazione [°C]")
    T_cond_C: float = Field(description="Temperatura di condensazione [°C]")
    Q_evap_required_kW: float = Field(gt=0, description="Carico frigorifero richiesto [kW]")
    superheat_K: float = Field(default=5.0, ge=0, le=30)
    subcooling_K: float = Field(default=3.0, ge=0, le=20)
    eta_isentropic: float = Field(default=0.70, gt=0.3, le=1.0)

    @model_validator(mode="after")
    def _check_temperatures(self) -> "Regime":
        """T_cond deve stare sopra T_evap, sennò il ciclo non esiste."""
        if self.T_cond_C <= self.T_evap_C:
            raise ValueError(
                f"T_cond ({self.T_cond_C} °C) deve essere > T_evap "
                f"({self.T_evap_C} °C): un ciclo frigorifero scarica calore "
                "a temperatura più alta di quella a cui lo assorbe."
            )
        return self


class Refrigerant(BaseModel):
    """Refrigerante con i suoi metadati ambientali e di sicurezza."""

    name: str                        # nome commerciale, es. "R1234ze(E)"
    GWP100: int = Field(ge=0)        # Global Warming Potential a 100 anni
    safety_class: Literal["A1", "A2L", "A3", "B1", "B2L"]
    coolprop_name: str               # nome esatto per il lookup CoolProp


class AmbientConditions(BaseModel):
    """Condizioni al contorno del sito di installazione."""

    T_air_summer_design_C: float = 38
    T_air_winter_typical_C: float = 5
    T_well_water_C: float = 12
    days_winter: int = Field(default=200, ge=0, le=366)
    days_summer: int = Field(default=165, ge=0, le=366)


class Project(BaseModel):
    """Stato centrale di un progetto I.A.zz: la fonte unica di verità.

    Ogni modulo del tool legge da qui e scrive i propri risultati qui.
    """

    # --- Metadata ---
    name: str
    created_at: datetime = Field(default_factory=datetime.now)
    modified_at: datetime = Field(default_factory=datetime.now)
    description: str = ""

    # --- Carichi termici ---
    cold_load: FluidTarget                    # cosa raffreddiamo (es. latte)
    hot_load: Optional[FluidTarget] = None    # cosa scaldiamo (es. acqua vacche)

    # --- Operativo ---
    refrigerant: Refrigerant
    regimes: list[Regime] = Field(min_length=1)
    ambient: AmbientConditions = Field(default_factory=AmbientConditions)

    # --- Architettura impianto ---
    architecture: Literal[
        "direct_chiller",
        "with_precooler",
        "precooler_glycol_dual_condenser",
        "custom",
    ] = "with_precooler"

    # --- Risultati dei moduli (popolati dai compute engines) ---
    cycle_results: dict = Field(default_factory=dict)
    compressor_selected: Optional[dict] = None
    heat_exchangers: list[dict] = Field(default_factory=list)
    storage: Optional[dict] = None
    bom: list[dict] = Field(default_factory=list)
    economics: Optional[dict] = None

    # --- Tariffe ---
    cost_electricity_eur_kWh: float = Field(default=0.20, gt=0)
    cost_gas_eur_Nm3: float = Field(default=0.95, gt=0)

    # ------------------------------------------------------------------
    # Proprietà derivate sui carichi (modulo Loads del D1, v0).
    # ------------------------------------------------------------------
    @property
    def Q_cold_design_kW(self) -> float:
        """Carico frigorifero di progetto [kW] (lato utenza fredda)."""
        return self.cold_load.Q_kW

    @property
    def Q_hot_design_kW(self) -> float:
        """Richiesta termica di progetto [kW] (0 se non c'è carico caldo)."""
        return self.hot_load.heating_Q_kW if self.hot_load else 0.0

    def simultaneity_check(self) -> dict:
        """Confronta il calore recuperabile con la richiesta calda.

        PROBLEMA: nel caso Thomas il condensatore scarica ~27 kW mentre
        l'acqua delle vacche ne chiede ~21: il recupero copre tutto?
        Questo check risponde alla domanda A LIVELLO DI CARICHI MEDI.
        La risposta vera (con le finestre di mungitura) richiede la
        simulazione 24h del modulo StorageTank (fase v1.0).

        Returns:
            dict con Q_cold, Q_hot, Q_cond stimato (Q_cold * (1+1/COP)
            con COP ipotizzato 3.5) e un verdetto testuale.
        """
        COP_HYP = 3.5  # ipotesi conservativa pre-calcolo ciclo
        q_cond_est = self.Q_cold_design_kW * (1 + 1 / COP_HYP)
        covered = q_cond_est >= self.Q_hot_design_kW
        return {
            "Q_cold_kW": round(self.Q_cold_design_kW, 2),
            "Q_hot_kW": round(self.Q_hot_design_kW, 2),
            "Q_cond_estimated_kW": round(q_cond_est, 2),
            "recovery_covers_hot_load": covered,
            "note": (
                "Stima su carichi medi con COP ipotizzato "
                f"{COP_HYP}; la verifica oraria richiede StorageTank (v1.0)."
            ),
        }

    # ------------------------------------------------------------------
    # Persistenza: salva/carica su JSON.
    # ------------------------------------------------------------------
    def save_json(self, path: str | Path) -> None:
        """Salva il progetto su file JSON (leggibile e versionabile su git)."""
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, path: str | Path) -> "Project":
        """Ricarica un progetto da file JSON, con validazione completa."""
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
