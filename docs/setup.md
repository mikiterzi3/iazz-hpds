# D2 — Setup guide: da zero all'ambiente di sviluppo I.A.zz

> Guida per Michele e co-sviluppatore. Scritta per chi **non ha mai
> programmato**: ogni passo spiega *cosa* fare, *come* e *perché*.
> Tempo stimato: 60-90 minuti la prima volta. Sistema: Windows
> (con note per Mac/Linux dove serve).

---

## 0. La mappa: cosa stiamo installando e perché

| Strumento | Cos'è | Perché ci serve |
|---|---|---|
| **Python 3.11+** | il linguaggio | tutto I.A.zz è Python |
| **VS Code** | l'editor | scrivere codice con aiuti (colori, errori, autocompletamento) |
| **Git** | il versionatore | ogni modifica è uno "snapshot" recuperabile; lavoro in 2 senza pestarsi |
| **GitHub** | il cloud di git | backup + collaborazione + portfolio pubblico |
| **venv** | ambiente isolato | le librerie di I.A.zz non sporcano il resto del PC |

Analogia: Python è la lingua, VS Code è il quaderno, git è la macchina
fotografica che fotografa ogni pagina, GitHub è l'album condiviso online.

---

## 1. Installare Python 3.11+

1. Vai su <https://www.python.org/downloads/> e scarica l'ultima
   versione stabile (3.12 o 3.13 vanno benissimo).
2. Avvia l'installer. **FONDAMENTALE**: spunta la casella
   **"Add python.exe to PATH"** nella prima schermata. Se la salti,
   il comando `python` non funzionerà dal terminale.
3. Clicca "Install Now".

**Verifica.** Apri il *Prompt dei comandi* (tasto Windows → scrivi
`cmd` → Invio) e digita:

```bat
python --version
```

Deve rispondere qualcosa come `Python 3.12.4`. Se dice "comando non
riconosciuto", il PATH non è stato impostato: reinstalla con la spunta.

> **Perché 3.11+?** Usiamo sintassi moderna dei type hints
> (`list[Regime]`, `str | Path`) introdotta nelle versioni recenti.

---

## 2. Installare VS Code

1. Scarica da <https://code.visualstudio.com/> e installa (le opzioni
   di default vanno bene; utile spuntare "Aggiungi al menu contestuale").
2. Apri VS Code → icona **Estensioni** (quadratini, barra a sinistra) →
   installa:
   - **Python** (di Microsoft) — esecuzione, debug, IntelliSense
   - **Pylance** (di solito arriva insieme) — analisi dei tipi
   - **Ruff** (di Astral) — il linter che useremo
   - **Black Formatter** (di Microsoft) — formattazione automatica
3. Imposta il format-on-save: `File → Preferences → Settings`, cerca
   "format on save" e spunta la casella. Da ora ogni salvataggio
   riordina il codice secondo lo standard `black` — mai più discussioni
   sullo stile.

---

## 3. Installare Git e configurarlo

1. Scarica da <https://git-scm.com/download/win> e installa. Le
   decine di schermate dell'installer si possono lasciare ai default
   (una sola attenzione: come editor di default scegli VS Code se
   proposto, non Vim).
2. Apri un **nuovo** terminale (le modifiche al PATH valgono solo per
   i terminali aperti dopo) e presentati a git:

```bat
git config --global user.name "Michele Terzi"
git config --global user.email "terzimichele17@gmail.com"
```

> **Perché serve?** Ogni commit (snapshot) registra chi l'ha fatto.
> Con due sviluppatori è la differenza tra "chi ha cambiato questo?"
> e saperlo subito.

**Verifica:** `git --version` → deve rispondere `git version 2.x`.

---

## 4. Creare l'account GitHub e il repo

1. Account su <https://github.com> (se non l'hai già). Username
   professionale: finirà sul CV.
2. ~~In alto a destra: + → New repository~~ **GIÀ FATTO** (2026-06-11, creato via Claude in Chrome): repo privato `mikiterzi3/iazz-hpds`. Schermate originali per riferimento:
   - Repository name: `iazz-hpds`
   - Visibilità: **Private** (lo apriremo a v0.5)
   - NON spuntare "Add a README" (lo abbiamo già nello skeleton)
3. Lascia aperta la pagina: GitHub ti mostra i comandi per il primo
   push, li useremo al §7.

**Autenticazione.** GitHub non accetta più la password da terminale.
La via più semplice: installa **GitHub Desktop**
(<https://desktop.github.com/>) e fai login lì una volta sola — gestirà
le credenziali anche per il terminale. (Alternativa da grandi: token
PAT o chiavi SSH, lo vediamo quando serve.)

---

## 5. Portare lo skeleton sul tuo PC e creare il venv

Lo skeleton `iazz-hpds/` è già nella cartella di progetto Cowork
(`...\Claude\Projects\IAZZ\iazz-hpds`). Copialo dove tieni i progetti,
ad esempio `C:\dev\iazz-hpds` (un percorso corto senza spazi evita
grattacapi).

Poi, nel terminale:

```bat
cd C:\dev\iazz-hpds

REM 1. crea l'ambiente virtuale (cartella .venv)
python -m venv .venv

REM 2. attivalo — il prompt mostrerà (.venv) davanti
.venv\Scripts\activate

REM 3. installa I.A.zz in modalità sviluppo + strumenti dev
pip install -e ".[dev]"
```

Su Mac/Linux il punto 2 diventa `source .venv/bin/activate`.

> **Cosa significa `-e .`?** "Editable install": pip collega il
> pacchetto direttamente alla cartella `src/iazz`, così ogni modifica
> al codice è subito attiva senza reinstallare. `[dev]` aggiunge
> pytest, black, ruff, hypothesis (vedi `pyproject.toml`).

> **Regola d'oro:** ogni volta che apri un terminale per lavorare a
> I.A.zz, prima cosa: `cd` nella cartella e `.venv\Scripts\activate`.
> Se il prompt non mostra `(.venv)`, stai usando il Python sbagliato.

In VS Code: `File → Open Folder → C:\dev\iazz-hpds`, poi in basso a
destra clicca sulla versione di Python e scegli quella dentro `.venv`.

---

## 6. Hello world: verifica CoolProp e lancia tutto

### 6a. CoolProp risponde?

```bat
python -c "from CoolProp.CoolProp import PropsSI; print(PropsSI('P','T',271.15,'Q',1,'R1234ze(E)')/1e5, 'bar')"
```

Atteso: `~2.01 bar` — è la pressione di saturazione di R1234ze(E) a
−2 °C, cioè la pressione di evaporazione del regime A di Thomas.
Se la vedi, hai un motore termodinamico NIST-quality sul tuo PC.

### 6b. I test passano?

```bat
pytest
```

Attesi: **19 passed**. I test verificano fisica (bilancio energetico,
COP < Carnot) e il caso Thomas. Se passano, l'ambiente è perfetto.

### 6c. La demo Thomas

```bat
python examples\thomas_chiller_demo.py
```

Stampa i 2 regimi con stati, COP (≈3,7 e ≈4,3) e potenze.

### 6d. La web app

```bat
streamlit run src\iazz\ui\app.py
```

Si apre il browser su `localhost:8501`: pagina Ciclo con slider e
diagramma p-h interattivo. Ctrl+C nel terminale per fermarla.

---

## 7. Primo push su GitHub

Dalla cartella del repo (con venv attivo o no, è uguale):

```bat
git init
git add .
git status
```

`git status` mostra cosa sta per essere fotografato. Controlla che NON
compaiano `.venv/` né `.env` (il `.gitignore` li esclude). Poi:

```bat
git commit -m "Skeleton iniziale: Project, refrigeranti, ciclo CoolProp, UI, test"
git branch -M main
git remote add origin https://github.com/mikiterzi3/iazz-hpds.git
git push -u origin main
```

Ricarica la pagina GitHub: il codice è online. 🎉

---

## 8. I 6 comandi git del quotidiano

| Comando | Cosa fa | Quando |
|---|---|---|
| `git status` | cosa è cambiato | sempre, prima di tutto |
| `git add .` | prepara le modifiche per lo snapshot | prima del commit |
| `git commit -m "messaggio"` | fotografa | a ogni passo compiuto |
| `git push` | manda su GitHub | a fine sessione |
| `git pull` | scarica le modifiche dell'altro | a inizio sessione |
| `git log --oneline` | storia del progetto | quando vuoi orientarti |

**Workflow in 2 persone (semplice, per ora):** lavorate su file
diversi, `git pull` a inizio sessione, `git push` a fine sessione.
I branch e le pull request arrivano nella roadmap (fase F3), quando
avremo preso confidenza.

**Messaggi di commit:** descrivi *cosa* e *perché* in una riga.
Bene: `Aggiunto parser polinomi Danfoss (formato Extended 30 coeff)`.
Male: `fix`, `cose`, `aggiornamento`.

---

## 9. Problemi tipici e soluzioni

| Sintomo | Causa probabile | Rimedio |
|---|---|---|
| `python non riconosciuto` | PATH mancante | reinstalla Python con la spunta "Add to PATH" |
| `pip install` fallisce su CoolProp | Python troppo nuovo/vecchio | usa 3.11-3.13; aggiorna pip: `python -m pip install -U pip` |
| `ModuleNotFoundError: iazz` | venv non attivo o `-e .` non fatto | attiva venv, poi `pip install -e ".[dev]"` |
| pytest non trovato | `[dev]` non installato | `pip install -e ".[dev]"` |
| push rifiutato da GitHub | autenticazione | fai login con GitHub Desktop una volta |
| Streamlit pagina bianca | firewall/antivirus | prova `streamlit run ... --server.port 8502` |

---

## 10. Checklist finale

- [ ] `python --version` → 3.11+
- [ ] VS Code con estensioni Python, Pylance, Ruff, Black
- [ ] `git --version` ok e nome/email configurati
- [ ] Repo `iazz-hpds` privato creato su GitHub
- [ ] venv creato e attivo, `pip install -e ".[dev]"` riuscito
- [ ] CoolProp risponde ~2.01 bar
- [ ] `pytest` → 19 passed
- [ ] Demo Thomas stampa COP ≈ 3,7 / 4,3
- [ ] Streamlit si apre nel browser
- [ ] Primo commit + push su GitHub

Quando tutte le caselle sono spuntate, sei pronto per la **Fase F1**
della roadmap. Benvenuto nello sviluppo software. ⚙️
