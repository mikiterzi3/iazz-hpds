"""Test dell'intake F0: parsing, domande, costruzione del Project.

L'LLM è finto (FakeIntakeProvider): i test verificano il CONTRATTO —
JSON → bozza validata → domande → Project — non l'intelligenza.
"""

import json

import pytest

from iazz.agents.intake import (
    IntakeDraft, build_project, missing_fields, run_intake,
)
from iazz.agents.llm_provider import LLMProvider


class FakeIntakeProvider(LLMProvider):
    """Risponde con un JSON prefissato (simula Claude ben educato)."""

    def __init__(self, payload: dict):
        self._payload = payload

    def complete(self, system: str, user: str) -> str:
        self.last_system = system
        self.last_user = user
        return f"```json\n{json.dumps(self._payload)}\n```"


THOMAS_LIKE = {
    "draft": {
        "name": "Chiller stalla 500 vacche",
        "cold_name": "latte mungitura",
        "cold_fluid_type": "milk",
        "cold_T_in_C": 35.0,
        "cold_T_out_C": 4.0,
        "cold_volume_L_day": 12000.0,
        "cold_hours_per_day": 8.0,
        "hot_name": "acqua abbeverata",
        "hot_fluid_type": "water",
        "hot_T_in_C": 12.0,
        "hot_T_out_C": 19.0,
        "T_well_water_C": 12.0,
        "food_contact": True,
    },
    "questions": [
        "Qual è la temperatura dell'aria estiva di progetto del sito?",
    ],
}


def test_run_intake_parses_fenced_json():
    provider = FakeIntakeProvider(THOMAS_LIKE)
    result = run_intake("chiller latte 500 vacche...", provider=provider)
    assert result.draft.cold_fluid_type == "milk"
    assert result.draft.cold_T_out_C == 4.0
    assert len(result.questions) == 1
    # il prompt contiene le regole ferree
    assert "NON INVENTARE" in provider.last_system


def test_previous_draft_is_passed_back():
    provider = FakeIntakeProvider(THOMAS_LIKE)
    prev = IntakeDraft(name="x")
    run_intake("aria estiva 38", previous=prev, provider=provider)
    assert "BOZZA ATTUALE" in provider.last_user


def test_missing_fields_flow_alternative():
    """Portata O volume+ore: una delle due strade deve esserci."""
    draft = IntakeDraft.model_validate(THOMAS_LIKE["draft"])
    assert missing_fields(draft) == []          # volume+ore bastano
    incompleto = draft.model_copy(update={"cold_volume_L_day": None})
    assert any("flow_rate" in m for m in missing_fields(incompleto))


def test_build_project_from_thomas_like_draft():
    draft = IntakeDraft.model_validate(THOMAS_LIKE["draft"])
    project = build_project(draft)
    assert project.cold_load.fluid_type == "milk"
    # portata: 12000 L/g * 1.03 kg/L / (8 h * 3600 s) ≈ 0.429 kg/s
    assert project.cold_load.flow_rate_kg_s == pytest.approx(0.429, abs=0.001)
    assert project.hot_load is not None
    assert project.regimes[0].T_evap_C < project.cold_load.T_out_C
    assert "bozza F0" in project.regimes[0].label


def test_build_project_refuses_incomplete_draft():
    with pytest.raises(ValueError, match="mancano"):
        build_project(IntakeDraft(name="solo un nome"))


def test_garbage_response_raises_clean_error():
    class Garbage(LLMProvider):
        def complete(self, system, user):
            return "Ciao! Che bel progetto!"

    with pytest.raises(ValueError, match="JSON"):
        run_intake("...", provider=Garbage())
