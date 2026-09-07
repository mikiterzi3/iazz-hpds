"""Classe base degli agenti AI: system prompt dinamico + provider.

PROBLEMA
    Un LLM generico risponde "in generale". I nostri agenti devono
    rispondere "in QUESTO progetto": coi numeri a schermo, i range del
    mestiere e i PDF di refrigerazione studiati da Michele.

CONCETTO
    Un agente = system prompt costruito da 4 ingredienti:
    1. RUOLO        (chi sei, come rispondi)         → rules YAML
    2. REGOLE       (range, best practice, red flag) → rules YAML
    3. KNOWLEDGE    (estratti dei PDF processati)    → knowledge/<agente>/
    4. STATO        (il Project serializzato JSON)   → gratis con pydantic
    più una MODALITÀ: explain / find_problems / suggest, che cambia
    l'istruzione finale (sono i 3 pulsanti della UI).

SCELTE
    - Niente RAG in v0: la KB si allega per file (troncata a un budget
      di caratteri). Quando la KB crescerà, qui si innesterà la
      selezione intelligente — l'interfaccia non cambia.
    - La risposta include anche il system prompt usato: trasparenza
      totale per debug e per il portfolio.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from iazz.agents.llm_provider import LLMProvider, get_provider
from iazz.core.project import Project

REPO_ROOT = Path(__file__).resolve().parents[3]
RULES_DIR = Path(__file__).resolve().parent / "rules"
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"

# Budget caratteri per la KB nel prompt (~12k token). Vedi SCELTE.
KB_CHAR_BUDGET = 48_000

MODES = {
    "explain": (
        "MODALITÀ: SPIEGAMI. Spiega in linguaggio chiaro i numeri del "
        "progetto rilevanti per la domanda: cosa significano, da dove "
        "vengono, se sono buoni valori per questo tipo di impianto."),
    "find_problems": (
        "MODALITÀ: TROVA PROBLEMI. Esamina criticamente input e "
        "risultati del progetto rispetto ai range e red flag delle tue "
        "regole. Elenca i problemi in ordine di gravità; se non ne "
        "trovi, dillo esplicitamente e indica cosa hai controllato."),
    "suggest": (
        "MODALITÀ: SUGGERISCI ALTERNATIVE. Proponi 2-3 modifiche "
        "concrete e quantificate (es. 'rilassa T_cond a 35 °C → COP "
        "+X%') con pro e contro di ciascuna."),
}


class AgentResponse(BaseModel):
    """Risposta dell'agente + il prompt usato (trasparenza/debug)."""

    agent: str
    mode: str
    text: str
    system_prompt: str


class Agent:
    """Agente specialista generico: i singoli agenti lo configurano."""

    def __init__(self, name: str, rules_file: str,
                 provider: LLMProvider | None = None):
        """
        Args:
            name: nome dell'agente (= cartella KB, chiave nel YAML provider).
            rules_file: nome del file YAML in agents/rules/.
            provider: LLMProvider esplicito (nei test: MockProvider).
                Se None, viene scelto da config/providers.yaml.
        """
        self.name = name
        self.rules_path = RULES_DIR / rules_file
        self.provider = provider or get_provider(name)

    # ------------------------------------------------------------ prompt
    def _load_rules(self) -> dict:
        return yaml.safe_load(self.rules_path.read_text(encoding="utf-8"))

    def _load_knowledge(self) -> str:
        """Concatena i markdown della KB dell'agente, entro il budget."""
        kb_dir = KNOWLEDGE_DIR / self.name
        if not kb_dir.is_dir():
            return "(Knowledge base non ancora processata per questo agente.)"
        chunks, used = [], 0
        for md in sorted(kb_dir.glob("*.md")):
            text = md.read_text(encoding="utf-8")
            room = KB_CHAR_BUDGET - used
            if room <= 0:
                chunks.append(f"\n[...altri file KB omessi per budget: "
                              f"{md.name}...]")
                break
            if len(text) > room:
                text = text[:room] + f"\n[...{md.name} troncato per budget...]"
            chunks.append(f"\n--- FILE KB: {md.name} ---\n{text}")
            used += len(text)
        return "\n".join(chunks) or "(KB vuota.)"

    def build_system_prompt(self, project: Project | None, mode: str) -> str:
        """Assembla i 4 ingredienti + la modalità. Vedi CONCETTO."""
        rules = self._load_rules()
        parts = [
            rules.get("ruolo", f"Sei l'agente {self.name} di I.A.zz."),
            "\n## REGOLE DI DOMINIO (vincolanti)\n"
            + yaml.dump(
                # 'modalita' è esclusa dal dump generale: la checklist
                # della SOLA modalità attiva viene iniettata sotto, con
                # l'istruzione — tre checklist insieme sarebbero rumore.
                {k: v for k, v in rules.items()
                 if k not in ("ruolo", "modalita")},
                allow_unicode=True, sort_keys=False),
            "\n## KNOWLEDGE BASE\n" + self._load_knowledge(),
        ]
        if project is not None:
            parts.append("\n## STATO CORRENTE DEL PROGETTO (JSON)\n"
                         + project.model_dump_json(indent=2))
        else:
            parts.append("\n## STATO PROGETTO\n(nessun progetto caricato: "
                         "rispondi in termini generali ma dichiaralo)")
        istruzione = MODES[mode]
        checklist = rules.get("modalita", {}).get(mode)
        if checklist:
            istruzione += (
                "\nSegui questa checklist nell'ordine, senza saltare "
                "voci:\n" + yaml.dump(checklist, allow_unicode=True,
                                      sort_keys=False))
        parts.append("\n## ISTRUZIONE\n" + istruzione)
        return "\n".join(parts)

    # -------------------------------------------------------------- ask
    def ask(self, question: str, project: Project | None = None,
            mode: str = "explain") -> AgentResponse:
        """Pone una domanda all'agente nella modalità scelta.

        Args:
            question: domanda dell'utente (o generata dal pulsante UI).
            project: stato corrente (None = domanda generale).
            mode: "explain" | "find_problems" | "suggest".

        Returns:
            AgentResponse con testo e system prompt usato.
        """
        if mode not in MODES:
            raise ValueError(f"Modalità '{mode}' sconosciuta. "
                             f"Valide: {', '.join(MODES)}")
        system = self.build_system_prompt(project, mode)
        text = self.provider.complete(system=system, user=question)
        return AgentResponse(agent=self.name, mode=mode, text=text,
                             system_prompt=system)


def thermodynamic_agent(provider: LLMProvider | None = None) -> Agent:
    """L'agente Termodinamico (il primo dei 7 + Coordinatore)."""
    return Agent(name="thermodynamic",
                 rules_file="thermodynamic_rules.yaml",
                 provider=provider)
