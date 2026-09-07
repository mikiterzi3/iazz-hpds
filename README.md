# I.A.zz — Heat Pumps Design & Sizing ❄️

Tool web-based per progettare e dimensionare pompe di calore e impianti
frigoriferi (chiller 5-100 kW). Il calcolo è deterministico e verificabile;
sopra ci sta uno strato di agenti AI che spiega ogni numero, segnala i
valori fuori range e propone alternative.

> **Stato onesto in una riga:** il nucleo di calcolo è funzionante e
> validato su un caso reale; degli agenti AI previsti dall'architettura
> **oggi è implementato quello termodinamico**, gli altri sono in roadmap.

> Progetto portfolio + studio di Michele Terzi (Ing. Energetica, UniPd).
> Caso fondativo di validazione: chiller con recupero termico per stalla
> da 500 vacche (R1234ze(E), Bitzer 4NES-14Y-40P).

<details>
<summary><b>English summary</b></summary>

Web tool for the design and sizing of heat pumps and chillers in the
5–100 kW range. A deterministic calculation core — CoolProp properties,
EN 12900 and extended manufacturer polynomials, operating-envelope checks
over a compressor database — with an AI agent layer on top that explains
each figure, flags out-of-range values and suggests alternatives. The
agent layer **never performs the physics**.

The architecture defines seven specialist agents plus a coordinator;
**the thermodynamic agent is the one implemented today**, the others are
on the roadmap. ~4 000 lines of Python, 81 test functions, including a
regression test that cross-checks refrigerant mass flow along two
independent paths (thermodynamic cycle and manufacturer polynomial),
which agree within 1.2 %.

</details>

## Quick start

```bash
# 1. clona e entra nel repo
git clone https://github.com/mikiterzi3/iazz-hpds.git
cd iazz-hpds

# 2. ambiente virtuale + dipendenze
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -e ".[dev]"

# 3. verifica che tutto funzioni — la suite deve passare interamente
pytest

# 4. demo: caso Thomas dal terminale
python examples/thomas_chiller_demo.py

# 5. web app
streamlit run src/iazz/ui/app.py
```

Guida completa per chi parte da zero: [`docs/setup.md`](docs/setup.md).

## Stato del progetto

| Componente | Stato |
|---|---|
| Modello dati `Project` (pydantic) | ✅ + carichi derivati, simultaneity check, test hypothesis |
| Database refrigeranti (6 fluidi) | ✅ v0 |
| Ciclo termodinamico (CoolProp) | ✅ + diagrammi p-h e T-s |
| Red flag / range di plausibilità | ✅ `compute/plausibility.py` |
| Confronto multi-refrigerante | ✅ `compute/compare.py` |
| UI: carica/salva, multi-regime, smoke test AppTest | ✅ |
| Knowledge extractor PDF → markdown | ✅ v0 |
| Mappa compressori EN 12900 + dati Bitzer 4NES-14Y | ✅ validata vs Excel |
| Validazione vs Excel Thomas (`docs/validation_thomas.md`) | ✅ |
| Suite di test | ✅ 81 funzioni di test |
| Parser polinomi Danfoss (Extended 30 coeff) | ⏳ F3 |
| Selezione compressore | ⏳ F4 |
| Telaio agenti AI: provider abstraction + **agente Termodinamico** + 3 pulsanti UI (mock) | ✅ da accendere con chiave API |
| Agenti restanti (6 su 7) + KB processata + risposte reali | ⏳ F5-F6 |

Roadmap completa: `IAZZ_MASTER_ROADMAP.md` (nella cartella di progetto).

## Architettura in 10 secondi

```
UI Streamlit  →  Project state (pydantic, JSON)  →  CoolProp / Agenti AI / DB
```

L'architettura prevede **sette agenti specialisti più un coordinatore**;
oggi ne è implementato uno. Dettagli: `docs/architecture.md`.

## Knowledge base

Gli agenti si appoggiano a una knowledge base testuale che **ogni utente
costruisce con il proprio materiale**: `scripts/ingest_pdfs.py` converte i
PDF in markdown dentro `knowledge/<agente>/`. Il repository **non
distribuisce materiale didattico di terzi** — né i PDF né il testo
estratto, esclusi entrambi da `.gitignore`.

## Licenza

[MIT](LICENSE) © 2026 Michele Terzi
