"""Test del telaio agenti con MockProvider: zero rete, zero costi.

Cosa verifichiamo: che il system prompt contenga DAVVERO i 4
ingredienti (ruolo, regole, KB, progetto) e che le modalità cambino
l'istruzione. Quando in F5 si passerà al provider vero, questi test
continueranno a girare identici (è il senso dell'astrazione).
"""

import pytest

from iazz.agents.base import MODES, thermodynamic_agent
from iazz.agents.llm_provider import MockProvider, get_provider
from iazz.core import refrigerants
from iazz.core.project import FluidTarget, Project, Regime


def _project() -> Project:
    return Project(
        name="Chiller Thomas 500 vacche",
        refrigerant=refrigerants.get("R1234ze(E)"),
        cold_load=FluidTarget(name="Latte", fluid_type="milk",
                              flow_rate_kg_s=0.4292, cp_kJ_kgK=3.9,
                              T_in_C=35, T_out_C=4),
        regimes=[Regime(label="A", T_evap_C=-2, T_cond_C=40,
                        Q_evap_required_kW=21.76)],
    )


@pytest.fixture
def agent():
    return thermodynamic_agent(provider=MockProvider())


def test_system_prompt_contains_all_ingredients(agent):
    prompt = agent.build_system_prompt(_project(), "explain")
    assert "agente Termodinamico" in prompt          # 1. ruolo
    assert "REGOLE DI DOMINIO" in prompt             # 2. regole
    assert "T_discharge_max_C" in prompt             #    (range dal YAML)
    assert "KNOWLEDGE BASE" in prompt                # 3. KB
    assert "Chiller Thomas 500 vacche" in prompt     # 4. stato progetto
    assert "R1234ze(E)" in prompt


@pytest.mark.parametrize("mode", list(MODES))
def test_modes_change_instruction(agent, mode):
    prompt = agent.build_system_prompt(_project(), mode)
    assert MODES[mode] in prompt
    others = [m for m in MODES if m != mode]
    assert all(MODES[m] not in prompt for m in others)


def test_ask_returns_response_with_transparency(agent):
    resp = agent.ask("Perché il COP è 3,7?", _project(), mode="explain")
    assert resp.agent == "thermodynamic"
    assert "MOCK" in resp.text                      # è il provider finto
    assert "REGOLE DI DOMINIO" in resp.system_prompt  # trasparenza


def test_no_project_is_declared(agent):
    prompt = agent.build_system_prompt(None, "explain")
    assert "nessun progetto caricato" in prompt


def test_invalid_mode_raises(agent):
    with pytest.raises(ValueError, match="Modalità"):
        agent.ask("ciao", mode="modalita_inventata")


def test_mode_checklists_injected_one_at_a_time(agent):
    """Ogni modalità riceve la SUA checklist, non le altre (richiesta
    di Michele: istruzioni specifiche, non generiche)."""
    p_explain = agent.build_system_prompt(_project(), "explain")
    assert "4 stati del ciclo" in p_explain
    assert "vincoli fisici" not in p_explain

    p_problems = agent.build_system_prompt(_project(), "find_problems")
    assert "vincoli fisici" in p_problems
    assert "secco è vietato" in p_problems
    assert "Prima leva sempre il lift" not in p_problems

    p_suggest = agent.build_system_prompt(_project(), "suggest")
    assert "Prima leva sempre il lift" in p_suggest
    assert "4 stati del ciclo" not in p_suggest


def test_style_rules_always_present(agent):
    """Lo stile asciutto vale in tutte le modalità."""
    for mode in MODES:
        prompt = agent.build_system_prompt(_project(), mode)
        assert "niente emoji" in prompt
        assert "compiacente" in prompt


def test_provider_factory_reads_config(tmp_path):
    """La factory costruisce il provider dal YAML indicato — test con
    config propria, INDIPENDENTE da config/providers.yaml dell'utente
    (che in sviluppo può legittimamente puntare al provider vero)."""
    cfg = tmp_path / "providers.yaml"
    cfg.write_text(
        "default_provider: mock\n"
        "providers:\n  mock:\n    type: mock\n",
        encoding="utf-8")
    assert isinstance(get_provider("thermodynamic", cfg), MockProvider)


def test_agent_specific_provider_overrides_default(tmp_path):
    """agent_providers vince sul default: è la trappola trovata al
    primo collaudo (default a claude_sonnet ma agente ancora su mock)."""
    cfg = tmp_path / "providers.yaml"
    cfg.write_text(
        "default_provider: finto_default\n"
        "providers:\n"
        "  mock:\n    type: mock\n"
        "  finto_default:\n    type: mock\n"
        "agent_providers:\n"
        "  thermodynamic: mock\n",
        encoding="utf-8")
    assert isinstance(get_provider("thermodynamic", cfg), MockProvider)
