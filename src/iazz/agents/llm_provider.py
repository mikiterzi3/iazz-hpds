"""Astrazione dei provider LLM: il tool non sa con chi sta parlando.

PROBLEMA
    Se le chiamate all'API Claude fossero sparse nel codice, passare a
    Gemini (free tier) o a un modello locale costerebbe giorni di
    refactoring. E senza chiave API non si potrebbe nemmeno testare.

CONCETTO
    Pattern "adapter", lo stesso dei parser compressori: N provider →
    1 interfaccia (`LLMProvider.complete`). Gli agenti parlano SOLO con
    l'interfaccia. Un file YAML (config/providers.yaml) decide chi
    risponde davvero. Il `MockProvider` permette di sviluppare e
    testare TUTTO il telaio senza chiave e senza spendere un centesimo.

SCELTE
    - `complete()` restituisce una stringa, non uno stream: semplicità
      prima. Lo streaming (st.write_stream) è un upgrade di F5 che non
      cambia l'interfaccia concettuale.
    - L'import di `anthropic` avviene DENTRO AnthropicProvider: chi usa
      solo il mock non ha bisogno del pacchetto installato.
    - La chiave API si legge dall'ambiente (.env), MAI da file
      committati.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO_ROOT / "config" / "providers.yaml"


class LLMProvider(ABC):
    """Interfaccia comune a tutti i provider LLM."""

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Invia (system prompt, messaggio utente) e restituisce la risposta."""


class MockProvider(LLMProvider):
    """Provider finto per sviluppo e test: nessuna rete, nessun costo.

    Restituisce una risposta deterministica che RIASSUME cosa ha
    ricevuto: così i test possono verificare che il system prompt
    contenga le cose giuste, e la UI è dimostrabile senza chiave API.
    """

    def complete(self, system: str, user: str) -> str:
        return (
            "🧪 RISPOSTA MOCK (nessuna chiamata API reale).\n\n"
            f"Domanda ricevuta: «{user[:200]}»\n\n"
            f"System prompt ricevuto: {len(system)} caratteri, "
            f"di cui regole e knowledge base inclusi.\n\n"
            "Per risposte vere: imposta ANTHROPIC_API_KEY nel file .env "
            "e cambia il provider in config/providers.yaml "
            "(vedi roadmap, fase F5)."
        )


class AnthropicProvider(LLMProvider):
    """Provider reale: Claude API (richiede `pip install -e .[ai]` e chiave)."""

    def __init__(self, model: str, max_tokens: int = 1500):
        try:
            from anthropic import Anthropic  # import locale: vedi SCELTE
        except ImportError as exc:
            raise ImportError(
                "Pacchetto 'anthropic' non installato: "
                'esegui  pip install -e ".[ai]"') from exc
        # Carica il file .env del repo, se esiste (best-effort: se
        # python-dotenv non è installato si usa solo l'ambiente).
        try:
            from dotenv import load_dotenv
            load_dotenv(REPO_ROOT / ".env")
        except ImportError:
            pass
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY non trovata. Copia .env.example in "
                ".env nella cartella del repo e inserisci la chiave "
                "(serve anche: pip install -e \".[ai]\").")
        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text


def get_provider(agent_name: str,
                 config_path: str | Path = DEFAULT_CONFIG) -> LLMProvider:
    """Factory: legge il YAML e costruisce il provider per un agente.

    Il YAML mappa agente → nome provider → tipo/modello. Cambiare
    provider = modificare una riga di configurazione, zero codice.
    """
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    name = cfg.get("agent_providers", {}).get(agent_name,
                                              cfg["default_provider"])
    spec = cfg["providers"][name]
    if spec["type"] == "mock":
        return MockProvider()
    if spec["type"] == "anthropic":
        return AnthropicProvider(model=spec["model"],
                                 max_tokens=spec.get("max_tokens", 1500))
    raise ValueError(f"Tipo provider sconosciuto: {spec['type']}")
