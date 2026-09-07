# I.A.zz — Heat Pumps Design & Sizing

**Architecture Document v0.1** — *2026-05-09*

> Tool web-based per progettazione e dimensionamento di pompe di calore e
> impianti frigoriferi, con team di agenti AI specializzati che assistono
> il progettista a ogni step decisionale.

---

## 1. Visione e scope

**Cosa fa il tool**: prende in input la specifica funzionale di un sistema
frigorifero (carico, temperature target, vincoli) e restituisce un
**progetto completo dimensionato**: ciclo termodinamico, compressore
selezionato, scambiatori dimensionati, accumuli, controllo, BOM con prezzi,
relazione tecnica.

**Cosa lo distingue da RefBox / CoolPack / EES**:
1. **Multi-agente AI integrato**: ogni step ha un esperto virtuale che
   spiega, contesta, suggerisce alternative — non più scatole nere.
2. **Cross-validation automatica**: i numeri da fonti indipendenti
   (CoolProp + cataloghi compressore) si parlano e segnalano discrepanze.
3. **Vendor-agnostic**: parser plug-in per Bitzer, Danfoss, Frascold,
   Copeland — tu scegli il costruttore, il tool capisce il formato.
4. **Workflow end-to-end**: dal concept iniziale alla relazione di
   consegna, in una sola interfaccia.
5. **Web-based**: gira ovunque, niente installazione client.

**Scope iniziale** (v1.0): progettazione di chiller a compressione di vapore
single-stage con recupero termico, focus sul mid-range (5–100 kW frigo).
Refrigeranti supportati: HFO (R1234ze, R1234yf), HFC (R134a, R513A),
naturali (R290, R744 CO₂, R717 NH₃).

**Fuori scope per v1.0**: cicli ad assorbimento, criogenia, multi-stage,
aria condizionata residenziale, impianti centrifughi >500 kW.

---

## 2. Architettura ad alto livello

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTERFACE                        │
│              (Streamlit web app, browser-based)          │
│  ┌──────────┬─────────┬─────────┬─────────┬──────────┐   │
│  │ Project  │ Cycle   │ Compr.  │ HE      │ ...      │   │
│  │ overview │ Analysis│ Select. │ Sizing  │          │   │
│  └────┬─────┴────┬────┴────┬────┴────┬────┴────┬─────┘   │
└───────┼──────────┼─────────┼─────────┼─────────┼─────────┘
        │          │         │         │         │
        ▼          ▼         ▼         ▼         ▼
┌─────────────────────────────────────────────────────────┐
│                   PROJECT STATE                          │
│         (single source of truth, in memory + JSON)       │
└────────────────────────┬────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  COMPUTE    │  │  AI AGENTS  │  │  EXTERNAL   │
│  ENGINES    │  │             │  │  DATA       │
│             │  │  Claude API │  │             │
│  - CoolProp │  │  + KB pdfs  │  │  - Compr.   │
│  - HE corr. │  │  + rules    │  │    polynom. │
│  - Cycle    │  │  + history  │  │  - Refr.    │
│    math     │  │             │  │    GWP DB   │
│  - Pricing  │  │             │  │             │
└─────────────┘  └─────────────┘  └─────────────┘
```

Tre layer:

- **UI** (Streamlit): pagine separate per ogni modulo, navigabili a sinistra
- **Project State**: oggetto centrale in RAM, persistito su JSON
- **Compute / AI / Data**: backend che fa i calcoli, gli agenti, i database

Il flusso è: utente modifica un input nella UI → cambia il Project State →
i moduli ricalcolano in cascata (come l'Excel di Thomas) → gli agenti AI
osservano i risultati e propongono interventi.

---

## 3. Modello dati: `Project`

Il cuore del tool. Replica concettualmente il foglio `2_INPUT_GLOBALE` +
`3_REGIMI` dell'Excel Thomas, ma con tipizzazione Python rigorosa.

```python
# src/iazz/core/project.py

from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

class FluidTarget(BaseModel):
    """Carico termico generico — latte, acqua, glicole, aria, ecc."""
    name: str
    fluid_type: Literal["water", "milk", "glycol30", "air", "brine"]
    flow_rate_kg_s: float
    cp_kJ_kgK: float
    T_in_C: float
    T_out_C: float

class Regime(BaseModel):
    """Punto operativo del chiller (es. regime A worst case, B alleggerito)."""
    label: str                       # "Worst case latte 4°C"
    T_evap_C: float
    T_cond_C: float
    Q_evap_required_kW: float        # carico frigorifero al chiller
    superheat_K: float = 5.0
    subcooling_K: float = 3.0
    eta_isentropic: float = 0.70

class Refrigerant(BaseModel):
    name: str                        # "R1234ze(E)", "R290", ...
    GWP100: int
    safety_class: Literal["A1", "A2L", "A3", "B1", "B2L"]
    coolprop_name: str               # nome esatto per CoolProp lookup

class AmbientConditions(BaseModel):
    T_air_summer_design_C: float = 38
    T_air_winter_typical_C: float = 5
    T_well_water_C: float = 12
    days_winter: int = 200
    days_summer: int = 165

class Project(BaseModel):
    """Stato centrale di un progetto."""
    # Metadata
    name: str
    created_at: datetime
    modified_at: datetime
    description: str = ""

    # Carichi termici
    cold_load: FluidTarget                    # cosa raffredda (es. latte)
    hot_load: Optional[FluidTarget] = None    # cosa riscalda (es. acqua)

    # Operativo
    refrigerant: Refrigerant
    regimes: list[Regime]                     # 1, 2 o N regimi paralleli
    ambient: AmbientConditions

    # Architettura scelta (preset o custom)
    architecture: Literal[
        "direct_chiller",
        "with_precooler",
        "precooler_glycol_dual_condenser",
        "custom"
    ] = "with_precooler"

    # Risultati moduli (popolati dai compute engines)
    cycle_results: dict = Field(default_factory=dict)
    compressor_selected: Optional[dict] = None
    heat_exchangers: list[dict] = Field(default_factory=list)
    storage: Optional[dict] = None
    bom: list[dict] = Field(default_factory=list)
    economics: Optional[dict] = None

    # Tariffe (per economics)
    cost_electricity_eur_kWh: float = 0.20
    cost_gas_eur_Nm3: float = 0.95

    def save_json(self, path: str): ...
    @classmethod
    def load_json(cls, path: str) -> "Project": ...
```

**Esempio dal caso Thomas**:

```python
project = Project(
    name="Chiller Thomas 500 vacche",
    refrigerant=Refrigerant(name="R1234ze(E)", GWP100=7, safety_class="A2L",
                             coolprop_name="R1234ze(E)"),
    cold_load=FluidTarget(
        name="Latte mungitura",
        fluid_type="milk",
        flow_rate_kg_s=0.4292,
        cp_kJ_kgK=3.9,
        T_in_C=35, T_out_C=4
    ),
    hot_load=FluidTarget(
        name="Acqua vacche",
        fluid_type="water",
        flow_rate_kg_s=0.724,
        cp_kJ_kgK=4.186,
        T_in_C=12, T_out_C=19
    ),
    regimes=[
        Regime(label="Worst case 4°C", T_evap_C=-2, T_cond_C=40,
               Q_evap_required_kW=21.76),
        Regime(label="Alleggerito 8°C", T_evap_C=2, T_cond_C=40,
               Q_evap_required_kW=15.06),
    ],
    architecture="precooler_glycol_dual_condenser",
)
```

**Pourquoi pydantic**: validazione automatica tipi/range, serializzazione
JSON gratuita, ottima integrazione con Streamlit forms e con Claude API.

---

## 4. Moduli del tool

Ogni modulo ha **inputs**, **calcoli**, **outputs**, e una **pagina UI**
dedicata. Si parlano via il `Project` state.

| # | Modulo | Inputs | Output principale | Compute engine |
|---|---|---|---|---|
| 1 | `ProjectOverview` | dati anagrafici | progetto vuoto | — |
| 2 | `Loads` | cold/hot loads, ambient | carichi termici stagionali | math base |
| 3 | `RefrigerantSelector` | requisiti (GWP, safety, T) | refrigerante consigliato | DB + rules |
| 4 | `ThermodynamicCycle` | regime, refrig, η | 4 stati ciclo, COP, portate | **CoolProp** |
| 5 | `CompressorSelection` | ciclo, V_aspir | modello selezionato + polin. | DB poli + rules |
| 6 | `Precooler` | carico, fluido | area, U, ΔT_lm | corr. plate HE |
| 7 | `Evaporator` | carico, glicole | area, U, ΔT_lm | corr. BPHE |
| 8 | `Condenser` (acqua/aria) | Q_cond, ambient | area, portata, U | corr. specifiche |
| 9 | `GlycolLoop` | portata, ΔP | pompa, vaso, perdite | hydr. base |
| 10 | `StorageTank` | Q_in/Q_out, V | dimensione, sim 24h | bilancio termico |
| 11 | `ControlLogic` | setpoint, regimi | sequenze PLC, sim | state machine |
| 12 | `Economics` | BOM, tariffe, baseline | payback, NPV | discounted cash flow |
| 13 | `BOM` | tutti i moduli | bill of materials | DB prezzi |
| 14 | `Documentation` | tutti i moduli | relazione tecnica .docx | template engine |

I primi moduli prioritari (per fase 1-3) sono **#4 ThermodynamicCycle** e
**#5 CompressorSelection**, perché sono il "cuore" del progetto e quelli
con maggior contenuto AI.

---

## 5. Agenti AI

Sette agenti specialisti + un coordinatore. **Questo e' l'obiettivo di architettura: allo stato attuale e' implementato il solo agente termodinamico, gli altri sono in roadmap (F5-F6).** Ogni agente è una chiamata
all'API Claude con un **system prompt specializzato** che include:

- **Knowledge base** (PDF processati, regole estratte)
- **Range di plausibilità** (es. ΔT pinch 3-7 K, η_is 0.65-0.85)
- **Pattern di best practice** (cosa sceglie un esperto in casi standard)
- **Red flag rules** (cosa segnala come critico)

```python
# src/iazz/agents/registry.py

AGENTS = {
    "thermodynamic": {
        "name": "Termodinamico",
        "scope": "Ciclo, refrigeranti, COP, surriscaldamento, T discharge",
        "kb_files": ["L0", "L1a", "L1b", "L2", "Refrigerants", "Cavallini",
                     "Carbon dioxide *", "KTH ch.1+3"],
        "rules": "thermodynamic_rules.yaml",
    },
    "compressor": {
        "name": "Compressori",
        "scope": "Selezione modello, polinomi, range applicazione",
        "kb_files": ["L4", "L5", "L6", "L7", "L8", "L9", "manuali Bitzer/Danfoss"],
        "rules": "compressor_rules.yaml",
    },
    "heat_exchanger": {
        "name": "Scambiatori",
        "scope": "Plate HE, BPHE, finned coil, U, ΔT_lm, fouling",
        "kb_files": ["Condensers", "Evaporators", "Pressure drop",
                     "Heat Transfer Lec#1-34", "KTH ch.7+8+9"],
        "rules": "heat_exchanger_rules.yaml",
    },
    "hydraulic": {
        "name": "Idraulico",
        "scope": "Pompe, prevalenze, ΔP, dimensionamento tubazioni",
        "kb_files": ["KTH ch.10+11", "manuali Grundfos/Wilo"],
        "rules": "hydraulic_rules.yaml",
    },
    "control_safety": {
        "name": "Controllo & Sicurezza",
        "scope": "PLC, sequenze, F-Gas, IEC 60335-2-40, EN 378",
        "kb_files": ["Lorentzen 1994", "NaReCO2 handbook", "normative"],
        "rules": "control_safety_rules.yaml",
    },
    "economics": {
        "name": "Economia",
        "scope": "BOM, payback, NPV, GWP cost, baseline analysis",
        "kb_files": ["price databases", "F-Gas regulation 2024"],
        "rules": "economics_rules.yaml",
    },
    "documentation": {
        "name": "Documentazione",
        "scope": "Genera relazione tecnica, schemi P&I, BOM finale",
        "kb_files": ["template UNI", "esempi relazioni precedenti"],
        "rules": "doc_rules.yaml",
    },
    "coordinator": {
        "name": "Coordinatore",
        "scope": "Riceve query utente, decide quali agenti consultare",
        "kb_files": [],
        "rules": "coordinator_rules.yaml",
    },
}
```

**Come si attivano nella UI**: ogni pagina del tool ha 3 pulsanti AI:

- **🔍 Spiegami** — l'agente del modulo spiega in linguaggio naturale i
  numeri visualizzati (cosa significa, da dove vengono)
- **⚠ Trova problemi** — l'agente verifica se gli input/output sono fuori
  range o se ci sono inconsistenze
- **💡 Suggerisci alternative** — l'agente propone scelte alternative
  (es. "rilassa T_uscita pre-cooler a 28 °C per margine fouling")

Inoltre c'è un pulsante globale **🧠 Review progetto completo** che attiva
il Coordinatore, il quale consulta tutti gli agenti e produce un report
critico stile "code review" del progetto.

**Implementazione tecnica**: Claude API (sonnet 4.5 per agenti specialisti,
haiku 4.5 per query rapide). System prompt dinamico costruito a partire da
KB + regole + stato corrente del progetto. Le risposte sono streamate per
UX più reattiva.

---

## 6. Stack tecnico

| Layer | Tecnologia | Perché |
|---|---|---|
| Linguaggio | Python 3.11+ | ecosistema scientifico, CoolProp nativo |
| Validazione dati | pydantic v2 | tipi rigidi + JSON serialization |
| UI web | **Streamlit** | rapido prototipa, ottimo per Python data |
| Plot interattivi | plotly | p-h, T-s, sankey, charts |
| Termodinamica | CoolProp 6.6+ | NIST-quality refrig. props |
| AI | Anthropic Claude API | sonnet 4.5 + haiku 4.5 |
| Storage | JSON (locale) → SQLite (v1.5) | semplice, no DB inizialmente |
| Test | pytest + hypothesis | unit + property-based |
| Versionamento | git + GitHub | standard portfolio |
| Docs | mkdocs material | sito documentazione auto-gen |
| Deploy v0 | Streamlit Community Cloud (free) | hosting gratis |
| Deploy v1+ | Hetzner VPS / Railway (~5-10 €/mese) | full control |

**Streamlit vs FastAPI+React** — abbiamo discusso. Streamlit è il default
fino a fine estate. Se a v1.0 il tool merita una UI più professionale,
migriamo (il backend Python si ricicla 100 %, cambia solo il "guscio" UI).

---

## 7. Struttura del repo

```
iazz-hpds/
├── README.md                       # overview + quick start
├── pyproject.toml                  # dependencies + tool config
├── .gitignore                      # cosa NON mettere su git
├── .env.example                    # template variabili d'ambiente (no secret)
├── docs/
│   ├── architecture.md             # questo documento
│   ├── setup.md                    # come setuppare l'ambiente
│   ├── modules/
│   │   ├── thermodynamic_cycle.md  # spec di ogni modulo
│   │   ├── compressor.md
│   │   └── ...
│   └── agents/
│       ├── thermodynamic_kb.md     # KB dell'agente termodinamico
│       └── ...
├── src/iazz/
│   ├── __init__.py
│   ├── core/
│   │   ├── project.py              # modello Project (pydantic)
│   │   ├── refrigerants.py         # DB refrigeranti
│   │   └── units.py                # gestione unità
│   ├── compute/
│   │   ├── cycle.py                # ThermodynamicCycle (CoolProp)
│   │   ├── compressor.py           # parser polinomi + selection
│   │   ├── heat_exchanger.py       # plate HE, BPHE, finned coil
│   │   ├── hydraulic.py            # pompe, ΔP
│   │   └── ...
│   ├── data/
│   │   ├── compressors/            # JSON dei polinomi
│   │   │   ├── bitzer/
│   │   │   ├── danfoss/
│   │   │   └── frascold/
│   │   ├── refrigerants.json       # GWP, safety, range
│   │   └── prices.json             # BOM prices DB
│   ├── agents/
│   │   ├── base.py                 # classe astratta Agent
│   │   ├── thermodynamic.py
│   │   ├── compressor.py
│   │   ├── heat_exchanger.py
│   │   ├── coordinator.py
│   │   └── kb_loader.py            # carica KB da PDF/markdown
│   ├── parsers/
│   │   ├── bitzer_csv.py           # parser EN 12900 Bitzer
│   │   ├── danfoss_xls.py          # parser Danfoss extended
│   │   └── ...
│   └── ui/
│       ├── app.py                  # Streamlit main entry
│       ├── pages/                  # una pagina per modulo
│       │   ├── 01_overview.py
│       │   ├── 02_cycle.py
│       │   ├── 03_compressor.py
│       │   └── ...
│       └── components/             # widget riutilizzabili
├── tests/
│   ├── test_project.py
│   ├── test_cycle.py
│   ├── test_compressor_parsers.py
│   └── ...
├── examples/
│   ├── thomas_chiller.json         # caso fondativo (Excel HP_THOM)
│   └── thomas_chiller_demo.py      # script che ricostruisce il caso
└── scripts/
    ├── ingest_pdfs.py              # processa PDF KB → markdown
    └── build_compressor_db.py      # converte CSV/XLS polinomi → JSON
```

**Convenzioni di codice**:
- Type hints ovunque (rigorosi)
- Docstrings stile Google
- Format: `black` (auto-format al save)
- Linter: `ruff`
- Test minimi per ogni nuovo modulo

---

## 8. Roadmap di sviluppo

| Fase | Periodo | Deliverable | Ore stimate |
|:---:|---|---|---:|
| **D1** | adesso | Architecture document (questo) | 2 |
| **D2** | adesso | Setup guide step-by-step (markdown) | 2 |
| **D3** | adesso | Repo skeleton con cartelle e file vuoti | 2 |
| **D4** | adesso | Knowledge extractor v0 + primo PDF processato | 4 |
| **F1** | maggio fine | Modulo `Project` + test | 6 |
| **F2** | luglio | Modulo `ThermodynamicCycle` + UI Streamlit | 18 |
| **F3** | luglio fine | Parser polinomi (Bitzer + Danfoss) + DB JSON | 10 |
| **F4** | agosto | Modulo `CompressorSelection` + UI | 12 |
| **F5** | agosto | Agente `Termodinamico` AI integrato | 10 |
| **F6** | agosto fine | Agente `Compressori` AI integrato | 10 |
| **F7** | settembre | Caso Thomas riprodotto end-to-end (validation) | 8 |
| **F8** | settembre | Polish UI, README, deploy Streamlit Cloud | 6 |

**Totale fino a "v0 demo-ready"**: ~90 ore di lavoro tuo, distribuite
maggio-settembre 2026. Realistico con 5-15 ore/settimana di disponibilità.

**A v0.5 (fine settembre)** hai: tool web pubblico (anche con URL
pubblicabile), 2 moduli funzionanti (Cycle + Compressor), 2 agenti AI,
1 caso d'uso completo (Thomas) come demo. **Più che sufficiente per
portfolio**.

**v1.0** (post settembre, opzionale): aggiungere altri 4-5 moduli
(Heat Exchanger, Hydraulic, Storage Tank, Economics, Documentation),
rendere il tool autosufficiente per progetti reali oltre Thomas.

---

## 9. Decisioni aperte / da chiudere

1. **Stack UI**: Streamlit confermato come default. Migrazione a
   FastAPI+React valutabile a v1.0.
2. **Hosting v0**: Streamlit Community Cloud (gratis) — confermato.
3. **GitHub repo**: `iazz-hpds`, privato fino a v0.5, poi pubblico — confermato.
4. **Modello Claude per agenti**: sonnet 4.5 default, haiku per query rapide.
5. **Costo Claude API**: ~5–20 $/mese in fase di sviluppo, scalabile dopo.
6. **Licenza codice**: da decidere (MIT, Apache 2.0, o proprietario).
7. **Multilingua UI**: solo italiano per v0.5, EN aggiunto poi.

---

## 10. Glossario tecnico (per Michele)

Termini di sviluppo software che useremo spesso. Se qualcuno è ancora
oscuro, chiedi durante lo sviluppo.

- **Repo / Repository**: cartella di progetto versionata con git.
- **Branch**: ramo del codice; lavori su un branch, fai merge nel main.
- **Commit**: snapshot delle modifiche con messaggio descrittivo.
- **Pull request (PR)**: richiesta di merge di un branch nel main, con review.
- **Virtual environment (venv)**: ambiente Python isolato con sue dipendenze.
- **Package manager (pip)**: tool che installa librerie Python.
- **API**: interfaccia per chiamare un servizio remoto (es. Claude API).
- **Endpoint**: URL specifico di un'API.
- **Backend**: codice che fa i calcoli, gira sul server.
- **Frontend**: codice che genera l'interfaccia utente, gira nel browser.
- **MVC pattern**: Model-View-Controller, separazione tra dati/UI/logica.
- **Type hints**: annotazioni Python che dichiarano tipi (es. `int`, `str`).
- **Decorator**: modificatore di funzione, usa `@nome` (es. `@property`).
- **Async / await**: programmazione asincrona, utile per chiamate AI.
- **JSON**: formato di scambio dati testuale, leggibile.
- **YAML**: simile a JSON ma più human-friendly, usato per config.
- **System prompt**: istruzioni iniziali date all'AI per definirne il ruolo.
- **Knowledge base (KB)**: corpus di documenti che l'agente AI consulta.
- **RAG (Retrieval-Augmented Generation)**: pattern dove l'AI cerca nel KB
  prima di rispondere — lo useremo per gli agenti.
- **Token**: unità di testo per calcolare costi API (~0.75 parole inglese).
- **Streaming**: ricezione progressiva della risposta AI (carattere per
  carattere), per UX più reattiva.
- **CI/CD**: Continuous Integration / Deployment, automatismi di build e
  rilascio (lo aggiungiamo da F8 in poi).
- **Test unitari**: piccoli test automatici che verificano una funzione.
- **Property-based testing**: test che generano input random — usiamo
  hypothesis per i calcoli termodinamici.

---

## Prossimi step

D1 (questo) ✓ → D2 Setup guide → D3 Repo skeleton → D4 Knowledge extractor v0
