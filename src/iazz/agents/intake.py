"""Intake del progetto (fase F0): dalla descrizione libera al Project.

PROBLEMA
    Il flusso di sintesi parte da un Project compilato, ma compilare
    un modello dati a mano è ostile. L'utente vuole DESCRIVERE il
    problema ("chiller per il latte di 500 vacche, ho acqua di pozzo
    a 12 gradi...") e farsi guidare.

CONCETTO
    L'agente legge la descrizione e restituisce DUE cose:
    1. una BOZZA strutturata (IntakeDraft): solo i campi che la
       descrizione supporta davvero;
    2. le DOMANDE sui campi mancanti o ambigui.
    Il ciclo si ripete finché la bozza non regge; poi l'utente
    CONFERMA guardando il modulo compilato, e solo lì nasce il
    Project. Tre linee di difesa: il prompt vieta di inventare,
    pydantic valida i tipi e i range, l'utente firma.

SCELTE
    - L'LLM emette SOLO JSON (schema nel prompt): il parsing è un
      contratto, non un'interpretazione. Se il JSON non si parsa, si
      mostra l'errore e si richiede — mai "aggiustare" in silenzio.
    - IntakeDraft è più povero di Project: F0 raccoglie i BISOGNI;
      temperature del ciclo, regimi definitivi ecc. nascono nelle
      fasi a valle (design_flow §2). Il regime bozza serve solo a
      far partire la pagina Dimensiona.
    - I vincoli (contatto alimentare, safety class del locale) si
      chiedono SEMPRE: sono loro che filtrano le architetture (F2).
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field, ValidationError

from iazz.agents.llm_provider import LLMProvider, get_provider
from iazz.core import refrigerants
from iazz.core.project import (
    AmbientConditions, FluidTarget, Project, Regime,
)

# --------------------------------------------------------------- schema

class IntakeDraft(BaseModel):
    """I bisogni del progetto, come l'agente li ha capiti.

    Ogni campo è Optional di fatto: None = "non detto" → domanda.
    """

    name: str | None = None
    description: str | None = None

    # carico freddo (obbligatorio per procedere)
    cold_name: str | None = None
    cold_fluid_type: str | None = None          # water/milk/glycol30/air/brine
    cold_T_in_C: float | None = None
    cold_T_out_C: float | None = None
    cold_flow_rate_kg_s: float | None = None
    cold_volume_L_day: float | None = None      # alternativa alla portata
    cold_hours_per_day: float | None = None

    # carico caldo / recupero (opzionale ma da CHIEDERE)
    hot_name: str | None = None
    hot_fluid_type: str | None = None
    hot_T_in_C: float | None = None
    hot_T_out_C: float | None = None
    hot_flow_rate_kg_s: float | None = None

    # ambiente e sorgenti
    T_air_summer_C: float | None = None
    T_well_water_C: float | None = None

    # vincoli (F2 dipende da questi!)
    food_contact: bool | None = None
    safety_constraints: str | None = None

    # preferenze
    refrigerant_preference: str | None = None
    Q_design_kW: float | None = None            # se l'utente la conosce

    # argomenti CHIUSI: l'utente ha risposto "non lo so" / "non serve"
    # → l'agente non deve MAI più chiederli (memoria anti-tormentone).
    closed_topics: list[str] = Field(default_factory=list)


class IntakeResult(BaseModel):
    draft: IntakeDraft
    questions: list[str]
    raw_response: str


_SCHEMA_LINES = "\n".join(
    f"  {name}: {f.annotation}" for name, f in IntakeDraft.model_fields.items())

SYSTEM_PROMPT = f"""Sei l'agente di intake di I.A.zz (progettazione di
chiller e pompe di calore). L'utente descrive il suo problema in
linguaggio naturale; tu lo trasformi in dati strutturati.

CAMPI OBBLIGATORI (senza questi il progetto non nasce):
  name, cold_name, cold_fluid_type, cold_T_in_C, cold_T_out_C,
  e la portata (cold_flow_rate_kg_s OPPURE cold_volume_L_day +
  cold_hours_per_day).
TRE CHIARIMENTI da fare UNA SOLA VOLTA se non emergono da soli:
  contatto alimentare/sanitario, T aria estiva del sito, esistenza
  di un recupero termico. Tutto il resto è FACOLTATIVO.

REGOLE FERREE:
1. NON INVENTARE MAI un valore. Se la descrizione non lo dice,
   lascialo null e (se serve) fai una domanda.
2. QUANDO SMETTERE: fai domande SOLO su campi obbligatori ancora
   null e sui tre chiarimenti non ancora affrontati. Se sono tutti
   coperti, "questions" DEVE essere []. Non chiedere rifiniture,
   non chiedere conferme, non fare domande di cortesia.
3. MAI richiedere: un campo già non-null nella bozza, o un argomento
   elencato in closed_topics. Se l'utente risponde "non lo so",
   "non serve", "lascia stare" su un campo facoltativo: aggiungi
   quell'argomento a closed_topics e chiudilo per sempre (per i tre
   chiarimenti: contatto alimentare non noto → chiedi se il fluido
   è alimentare una volta sola, poi closed_topics).
4. MASSIMO 4 domande per giro, in ordine di importanza.
5. Converti le unità a quelle dello schema (portate in kg/s, volumi
   in L/giorno, temperature in °C) mostrando la conversione nella
   domanda se c'è ambiguità.
6. cold_fluid_type ∈ [water, milk, glycol30, air, brine].
7. Rispondi SOLO con un blocco JSON, nessun testo fuori:

{{{{
  "draft": {{{{ ... campi di IntakeDraft, null se non noti ... }}}},
  "questions": ["domanda 1", "domanda 2", ...]
}}}}

SCHEMA IntakeDraft:
{_SCHEMA_LINES}
"""


# -------------------------------------------------------------- parsing

def _extract_json(text: str) -> dict:
    """Estrae il primo blocco JSON dalla risposta (tollera i fence)."""
    cleaned = re.sub(r"```(?:json)?", "", text)
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("Nessun JSON nella risposta dell'agente.")
    depth = 0
    for i, ch in enumerate(cleaned[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start:i + 1])
    raise ValueError("JSON non chiuso nella risposta dell'agente.")


def run_intake(description: str,
               previous: IntakeDraft | None = None,
               provider: LLMProvider | None = None) -> IntakeResult:
    """Un giro di intake: descrizione (+ bozza precedente) → bozza nuova.

    Args:
        description: testo dell'utente (descrizione o risposte alle
            domande del giro precedente).
        previous: bozza del giro precedente, da completare.
        provider: LLMProvider (nei test: uno finto).

    Returns:
        IntakeResult con bozza validata e domande residue.

    Raises:
        ValueError: JSON assente/malformato (da mostrare all'utente).
        ValidationError: campi fuori schema (idem).
    """
    provider = provider or get_provider("coordinator")
    user = description
    if previous is not None:
        user = (f"BOZZA ATTUALE (da completare, non riscrivere ciò che "
                f"è già noto):\n{previous.model_dump_json()}\n\n"
                f"NUOVE INFORMAZIONI DALL'UTENTE:\n{description}")
    raw = provider.complete(system=SYSTEM_PROMPT, user=user)
    payload = _extract_json(raw)
    draft = IntakeDraft.model_validate(payload.get("draft", {}))
    questions = [str(q) for q in payload.get("questions", [])]
    return IntakeResult(draft=draft, questions=questions, raw_response=raw)


# ------------------------------------------------- bozza → Project vero

#: Campi senza i quali il Project non può nascere.
REQUIRED_FOR_BUILD = ["name", "cold_name", "cold_fluid_type",
                      "cold_T_in_C", "cold_T_out_C"]


def missing_fields(draft: IntakeDraft) -> list[str]:
    """Cosa manca ancora per costruire il Project."""
    missing = [f for f in REQUIRED_FOR_BUILD if getattr(draft, f) is None]
    if draft.cold_flow_rate_kg_s is None and (
            draft.cold_volume_L_day is None
            or draft.cold_hours_per_day is None):
        missing.append("cold_flow_rate_kg_s OPPURE "
                       "cold_volume_L_day + cold_hours_per_day")
    return missing


_CP_DEFAULTS = {"water": 4.186, "milk": 3.9, "glycol30": 3.95,
                "air": 1.005, "brine": 3.5}
_DENSITY_KG_L = {"water": 1.0, "milk": 1.03, "glycol30": 1.025,
                 "air": 0.0012, "brine": 1.1}


def build_project(draft: IntakeDraft) -> Project:
    """Costruisce il Project dalla bozza confermata.

    Il regime incluso è una BOZZA F0 (etichettata come tale): serve a
    far partire la pagina Dimensiona, dove la catena F4 lo sostituirà.

    Raises:
        ValueError: se mancano campi obbligatori (usa missing_fields
        prima di chiamare).
    """
    lacking = missing_fields(draft)
    if lacking:
        raise ValueError(f"Bozza incompleta, mancano: {', '.join(lacking)}")

    flow = draft.cold_flow_rate_kg_s
    if flow is None:
        density = _DENSITY_KG_L[draft.cold_fluid_type]
        flow = (draft.cold_volume_L_day * density
                / (draft.cold_hours_per_day * 3600.0))

    cold = FluidTarget(
        name=draft.cold_name, fluid_type=draft.cold_fluid_type,
        flow_rate_kg_s=flow,
        cp_kJ_kgK=_CP_DEFAULTS[draft.cold_fluid_type],
        T_in_C=draft.cold_T_in_C, T_out_C=draft.cold_T_out_C)

    hot = None
    if draft.hot_T_out_C is not None and draft.hot_T_in_C is not None:
        hot = FluidTarget(
            name=draft.hot_name or "recupero termico",
            fluid_type=draft.hot_fluid_type or "water",
            flow_rate_kg_s=draft.hot_flow_rate_kg_s or 0.5,
            cp_kJ_kgK=_CP_DEFAULTS[draft.hot_fluid_type or "water"],
            T_in_C=draft.hot_T_in_C, T_out_C=draft.hot_T_out_C)

    ambient = AmbientConditions()
    if draft.T_air_summer_C is not None:
        ambient.T_air_summer_design_C = draft.T_air_summer_C
    if draft.T_well_water_C is not None:
        ambient.T_well_water_C = draft.T_well_water_C

    ref_name = draft.refrigerant_preference or "R1234ze(E)"
    try:
        refrigerant = refrigerants.get(ref_name)
    except KeyError:
        refrigerant = refrigerants.get("R1234ze(E)")

    Q_design = draft.Q_design_kW or cold.Q_kW

    # Regime bozza: approcci di default 3+3 sotto il target freddo,
    # condensazione dal pozzo più esigente noto (aria estiva + 2 K,
    # o recupero + 2 K). La F4 lo ricalcolerà con l'utente.
    T_evap_draft = draft.cold_T_out_C - 6.0
    sinks = [ambient.T_air_summer_design_C + 2.0]
    if hot is not None:
        sinks.append(hot.T_out_C + 2.0)
    regime = Regime(label="bozza F0 (da raffinare in Dimensiona)",
                    T_evap_C=T_evap_draft, T_cond_C=max(sinks),
                    Q_evap_required_kW=Q_design)

    from datetime import datetime
    now = datetime.now()
    return Project(
        name=draft.name, created_at=now, modified_at=now,
        description=draft.description or "",
        cold_load=cold, hot_load=hot,
        refrigerant=refrigerant, regimes=[regime], ambient=ambient)
