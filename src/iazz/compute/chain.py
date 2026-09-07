"""Catena delle temperature: il cuore della sintesi (fase F4).

PROBLEMA
    In modalità analisi T_evap e T_cond sono input liberi: si possono
    scrivere assurdi fisici (T_evap sopra il target del latte) e il
    sistema al massimo li flagga. In modalità SINTESI le temperature
    devono NASCERE dai carichi, così l'assurdo è impossibile per
    costruzione (docs/design_flow.md, principio 2).

CONCETTO
    Lato freddo: una catena di anelli dal target in giù. Ogni anello è
    uno scambio termico che "costa" un approccio ΔT:
        T_evap = T_target_freddo − Σ approcci
    (Thomas: 4 °C − 3 K [latte→glicole] − 3 K [glicole→evap] = −2 °C.)

    Lato caldo: ogni pozzo che deve RICEVERE calore impone un minimo:
        T_cond ≥ T_pozzo + approccio
    e la condensazione deve accontentare il pozzo più esigente:
        T_cond = max_i (T_pozzo_i + ΔT_i)
    (Thomas: max(acqua 19+2, aria estate 38+2) = 40 °C — il valore
    dell'Excel, che ora è SPIEGATO: lo governa l'aria d'estate.)

    Ogni approccio è una DECISIONE con un prezzo: ~2-3 % di COP per K
    (L1b). `sensitivity_COP_per_K` lo quantifica anello per anello,
    così l'utente decide guardando i numeri, non a sensazione.

SCELTE
    - Gli approcci hanno un minimo fisico-pratico (approach_min_K da
      plausibility.RANGES): pydantic li rifiuta alla costruzione.
      Il guardrail di plausibility resta per la modalità analisi;
      qui l'errore non può proprio entrare.
    - Il lato caldo è una lista di vincoli, non un valore: aggiungere
      un pozzo (nuovo recupero, nuova stagione) = aggiungere una riga,
      e T_cond si aggiorna da sola.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from iazz.compute.cycle import compute_cycle
from iazz.compute.plausibility import RANGES
from iazz.core.project import Refrigerant, Regime

APPROACH_MIN_K = RANGES["approach_min_K"]


class ColdLink(BaseModel):
    """Anello della catena fredda: uno scambio col suo approccio.

    Attributes:
        name: etichetta leggibile, es. "latte → glicole".
        approach_K: ΔT dell'anello [K]. Deciso dall'utente (default
            dal range di mestiere); minimo fisico imposto qui.
        reason: perché l'anello esiste (es. "vincolo alimentare:
            doppia parete / loop intermedio"). La tracciabilità delle
            decisioni è parte del progetto (design_flow §2-F2).
    """

    name: str
    approach_K: float = Field(ge=APPROACH_MIN_K)
    reason: str = ""


class HotSink(BaseModel):
    """Pozzo caldo: impone T_cond ≥ T_sink_C + approach_K.

    Attributes:
        name: es. "acqua vacche (recupero)", "aria estiva".
        T_sink_C: temperatura che il pozzo deve RAGGIUNGERE (per un
            recupero: la T di uscita richiesta; per l'aria: la T aria
            di progetto).
        approach_K: ΔT di scambio del condensatore verso quel pozzo.
    """

    name: str
    T_sink_C: float
    approach_K: float = Field(ge=APPROACH_MIN_K)

    @property
    def T_cond_required_C(self) -> float:
        """Condensazione minima perché il calore fluisca verso il pozzo."""
        return self.T_sink_C + self.approach_K


class TemperatureChain(BaseModel):
    """Catena completa: dai carichi alle temperature del ciclo.

    Il costruttore valida; le property derivano. Non esistono setter
    per T_evap/T_cond: chi vuole cambiarle deve cambiare un anello —
    cioè prendere una decisione ingegneristica esplicita.
    """

    cold_target_C: float                    # T finale del carico freddo
    cold_links: list[ColdLink] = Field(min_length=1)
    hot_sinks: list[HotSink] = Field(min_length=1)

    @field_validator("cold_links")
    @classmethod
    def _at_least_one_exchanger(cls, v: list[ColdLink]) -> list[ColdLink]:
        # Anche in espansione diretta esiste ALMENO l'evaporatore.
        return v

    # ------------------------------------------------------- derivate
    @property
    def T_evap_C(self) -> float:
        """T_target − Σ approcci: sotto il target PER COSTRUZIONE."""
        return self.cold_target_C - sum(l.approach_K for l in self.cold_links)

    @property
    def T_cond_C(self) -> float:
        """Il pozzo più esigente governa la condensazione."""
        return max(s.T_cond_required_C for s in self.hot_sinks)

    @property
    def governing_sink(self) -> HotSink:
        """Quale pozzo sta dettando T_cond (per spiegarlo all'utente)."""
        return max(self.hot_sinks, key=lambda s: s.T_cond_required_C)

    # ------------------------------------------------------ al ciclo
    def to_regime(self, label: str, Q_evap_required_kW: float,
                  superheat_K: float = 5.0, subcooling_K: float = 3.0,
                  eta_isentropic: float = 0.70) -> Regime:
        """Costruisce il Regime per compute_cycle: F4 → F5 senza mani."""
        return Regime(label=label,
                      T_evap_C=self.T_evap_C, T_cond_C=self.T_cond_C,
                      Q_evap_required_kW=Q_evap_required_kW,
                      superheat_K=superheat_K, subcooling_K=subcooling_K,
                      eta_isentropic=eta_isentropic)

    # --------------------------------------------------- sensibilità
    def sensitivity_COP_per_K(self, refrigerant: Refrigerant,
                              Q_evap_kW: float = 20.0
                              ) -> dict[str, float | None]:
        """ΔCOP per −1 K di approccio, anello per anello.

        Per ogni anello freddo: stringere di 1 K alza T_evap di 1 K.
        Per i pozzi caldi: stringere muove T_cond solo se il pozzo è
        (o diventa) quello governante.

        Returns:
            {nome anello/pozzo: ΔCOP stringendo di 1 K}, dove:
            - valore > 0  → COP guadagnabile (il prezzo della decisione);
            - valore = 0  → stringere qui non muove nulla (pozzo non
              governante): "ottimizzare qui non serve";
            - None        → approccio GIÀ al minimo fisico
              (approach_min_K): non c'è margine, il vincolo è saturo.
            La distinzione 0/None è informazione di progetto: nel caso
            Thomas l'aria estiva è a None — lato condensazione la
            macchina è già al limite (design_flow §2-F4).
        """
        base = compute_cycle(
            refrigerant, self.to_regime("base", Q_evap_kW)).COP_cooling
        out: dict[str, float | None] = {}

        def cop_of(variant: "TemperatureChain") -> float:
            return compute_cycle(
                refrigerant, variant.to_regime("v", Q_evap_kW)).COP_cooling

        for i, link in enumerate(self.cold_links):
            tighter = link.approach_K - 1.0
            if tighter < APPROACH_MIN_K:
                out[link.name] = None      # vincolo saturo
                continue
            links = [l.model_copy() for l in self.cold_links]
            links[i] = links[i].model_copy(update={"approach_K": tighter})
            out[link.name] = cop_of(
                self.model_copy(update={"cold_links": links})) - base

        for i, sink in enumerate(self.hot_sinks):
            tighter = sink.approach_K - 1.0
            if tighter < APPROACH_MIN_K:
                out[sink.name] = None      # vincolo saturo
                continue
            sinks = [s.model_copy() for s in self.hot_sinks]
            sinks[i] = sinks[i].model_copy(update={"approach_K": tighter})
            out[sink.name] = cop_of(
                self.model_copy(update={"hot_sinks": sinks})) - base

        return out


def thomas_chain() -> TemperatureChain:
    """La catena del caso fondativo, per test, demo e documentazione.

    Riproduce ESATTAMENTE le temperature dell'Excel (-2 °C / 40 °C)
    a partire dai bisogni — è la dimostrazione che la sintesi
    funziona sul caso validato.
    """
    return TemperatureChain(
        cold_target_C=4.0,                       # latte a 4 °C
        cold_links=[
            ColdLink(name="latte → glicole", approach_K=3.0,
                     reason="vincolo alimentare: il latte non può "
                            "toccare il refrigerante → loop intermedio"),
            ColdLink(name="glicole → evaporazione", approach_K=3.0),
        ],
        hot_sinks=[
            HotSink(name="acqua vacche (recupero)", T_sink_C=19.0,
                    approach_K=2.0),
            HotSink(name="aria estiva (condensatore aria)",
                    T_sink_C=38.0, approach_K=2.0),
        ],
    )
