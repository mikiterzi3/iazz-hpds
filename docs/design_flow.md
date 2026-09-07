# I.A.zz — Flusso di dimensionamento (sintesi guidata)

**v0.1 — 2026-07-14 — Michele Terzi + Claude**

> Documento di progetto del "motore di sintesi": come I.A.zz porta
> l'utente dal problema al progetto dimensionato. Nasce da tre fonti:
> l'Excel `HP_THOM_FINALE.xlsx` (il flusso implicito di Michele, 17
> fogli), la discussione del 2026-07-13/14 (analisi vs sintesi), e il
> feedback sul primo collaudo dell'agente.

---

## 1. Principio

I.A.zz oggi fa **analisi**: dato un ciclo configurato, lo valuta.
La modalità principale deve diventare la **sintesi**: dai bisogni al
progetto, passo per passo. Regole fondanti:

1. **Il motore matematico è sovrano sui numeri.** Ogni calcolo è
   deterministico, testato, rigoroso. L'AI non calcola mai.
2. **Le temperature sono conseguenze, non input.** T_evap e T_cond
   nascono da catene di approcci a partire dai carichi: gli assurdi
   fisici diventano impossibili per costruzione (non solo flaggati).
3. **Ogni fase distingue DECISIONI da CALCOLI.** Le decisioni le
   prende l'utente, assistito dall'agente competente che propone,
   quantifica i trade-off e mette in guardia. I calcoli li fa il
   motore, e basta.
4. **I vincoli filtrano prima dell'ottimizzazione.** Esempio Thomas:
   il latte non può toccare il refrigerante (norma alimentare) → il
   loop intermedio è OBBLIGATO, non una preferenza. I vincoli hard
   eliminano architetture prima di qualsiasi confronto di efficienza.
5. **Il flusso è iterativo e i loop sono espliciti.** L'Excel mostra
   solo l'ultima iterazione; il tool deve rendere visibile e indolore
   il tornare indietro (es. il compressore reale quantizza la
   capacità → si riaggiustano le temperature).

---

## 2. Le fasi

Ogni fase dichiara: INPUT ← fasi precedenti · DECISIONI (utente +
agente) · CALCOLI (motore) · GATE (guardrail deterministici che
bloccano il passaggio alla fase successiva) · AGENTE di riferimento.

### F0 — Requisiti e vincoli
- INPUT: descrizione del problema (cosa raffreddare/scaldare, dove,
  quanto, quando), vincoli normativi e di sito.
- DECISIONI: nessuna — è raccolta strutturata. L'agente Coordinatore
  intervista l'utente e compila il `Project`.
- CALCOLI: nessuno.
- GATE: dati minimi presenti (fluido, portata o volume/giorno, T_in,
  T_out, sorgenti/pozzi disponibili con le loro temperature).
- Vincoli tipici da catturare SUBITO: contatto alimentare (→ doppia
  parete / loop intermedio obbligato), safety class ammessa nel
  locale (A2L/A3/B2L → EN 378), limiti acustici, spazio.

### F1 — Carichi e profilo temporale
- INPUT: F0.
- DECISIONI: granularità del profilo (Thomas: mungitura 2 finestre
  da 4 h). È QUI che nasce il trade-off macchina grande senza
  accumulo vs macchina piccola + accumulo: va mostrato subito, non
  scoperto alla fase tank.
- CALCOLI: Q di picco e Q media per finestra, energia/giorno,
  simultaneità carico freddo/caldo (già in `Project.simultaneity`).
- GATE: bilancio energetico chiuso (energia rimossa = energia del
  prodotto), potenze > 0, profilo coerente col volume dichiarato.
- AGENTE: Termodinamico ("con questo profilo, un accumulo di X kWh
  taglierebbe il picco del Y%").

### F2 — Architettura
- INPUT: F0 (vincoli!), F1.
- DECISIONI: schema d'impianto. Flusso a due mosse:
  1. il motore FILTRA i preset compatibili coi vincoli hard
     (es. food-grade → niente espansione diretta sul latte);
  2. l'utente propone/sceglie, l'agente confronta le alternative
     rimaste con pro/contro quantificati dove possibile (superfici,
     ΔT persi, complessità, costo qualitativo) e può proporre
     varianti (è la "conversazione sull'architettura" chiesta da
     Michele).
- CALCOLI: per ogni candidata, stima di massima delle temperature
  intermedie e dei ΔT persi in cascata.
- GATE: architettura scelta ∈ preset validi; ogni vincolo hard di F0
  soddisfatto e tracciato ("loop intermedio: obbligato da vincolo
  alimentare").
- AGENTE: Coordinatore + Scambiatori (quando esisterà).

### F3 — Refrigerante
- INPUT: F0 (safety class ammessa), F1 (taglie), F2 (architettura),
  range di temperature attese.
- DECISIONI: il fluido. Agente Refrigeranti DEDICATO (richiesto
  esplicitamente da Michele): consulta gli altri agenti/fasi e
  propone una rosa ordinata con criteri espliciti: GWP (F-Gas),
  safety class vs locale, T critica vs T_cond attesa, capacità
  volumetrica vs taglia, DISPONIBILITÀ DI COMPRESSORI nel DB (un
  fluido senza macchine reali è una non-scelta), maturità/costo.
- CALCOLI: `compare_refrigerants` sui punti attesi + envelope check
  sul DB compressori.
- GATE: fluido ∈ DB; safety class compatibile coi vincoli F0;
  esistono compressori nel DB che coprono il punto di lavoro atteso.
- NOTA: in Thomas la scelta fu a priori di Michele; il tool deve
  rendere la decisione argomentata e riproducibile.

### F4 — Catena delle temperature (il cuore della sintesi)
- INPUT: F1 (T target dei carichi), F2 (quanti scambi in cascata).
- DECISIONI: gli APPROCCI (ΔT) di ogni anello della catena. Esempio
  Thomas: latte 4 °C → glicole (4 − ΔT₁) → evaporazione
  (T_glicole − ΔT₂) = −2 °C. Ogni ΔT è un trade-off quantificato:
  piccolo = COP alto ma area di scambio grande; grande = scambiatore
  economico ma COP giù (~2-3%/K, L1b). Il motore propone default da
  range del mestiere (`pinch_scambiatori_K: [3, 7]`), l'utente
  aggiusta VEDENDO il costo di ogni K in COP e area stimata.
- CALCOLI: catena T_evap/T_cond derivate; effetto COP per variazione
  di ogni approccio (∂COP/∂ΔT numerico).
- GATE: tutti gli approcci ≥ `approach_min_K`; catena monotona
  (mai calore in salita) — con la derivazione è garantito per
  costruzione, il gate difende dagli override manuali.
- AGENTE: Termodinamico.

### F5 — Ciclo termodinamico
- INPUT: F3 (fluido), F4 (temperature), SH/SC (default da regole).
- DECISIONI: SH/SC se si vuole deviare dai default; regimi multipli
  (A dimensionante / B alleggerito, come in Thomas foglio 3).
- CALCOLI: `compute_cycle` per ogni regime: stati, COP, portate,
  volume aspirato.
- GATE: `check_cycle` con project: zero critical per procedere
  (i warning passano ma restano visibili).
- AGENTE: Termodinamico (le tre modalità con checklist).

### F6 — Compressore (con loop di ritorno)
- INPUT: F5 (V̇ aspirato, punto di lavoro), F3 (fluido).
- DECISIONI: la macchina, dalla rosa che il motore estrae dal DB
  (envelope ok, capacità sufficiente nel punto, VSD se il profilo
  F1 lo chiede). Il compressore reale QUANTIZZA: qui si torna
  spesso a F4 per riaggiustare (in Thomas: T_evap = −2 °C nacque
  proprio così, "a occhio" — il tool renderà il giro esplicito).
- CALCOLI: valutazione polinomi per candidata (Q, P, COP reale,
  frequenza necessaria); cross-validation CoolProp vs polinomio
  (concordanza < 5%, regola già nel repo).
- GATE: punto dentro l'envelope; Q_macchina ≥ Q_richiesto al regime
  dimensionante; cross-validation passata.
- AGENTE: Compressori (KB da L4-L9, da costruire — pattern fetta
  verticale già collaudato).

### F7 — Scambiatori
- INPUT: F2 (quali scambiatori), F4 (ΔT), F5-F6 (carichi effettivi).
- v0.5: dimensionamento a margine dichiarato (l'1,2 dell'Excel,
  reso esplicito e motivato: fouling + incertezza).
- v1.0 (tema caro a Michele, da sviscerare coi 42 PDF Heat
  Transfer): U calcolato con correlazioni vere (Nusselt, regime di
  moto, fouling factor per fluido), non stimato. Il margine smette
  di essere un numero magico e diventa il risultato di un'analisi
  di incertezza.
- GATE: area finita e positiva, ΔT_lm coerente con la catena F4,
  velocità nei canali nei range (erosione/fouling).
- AGENTE: Scambiatori.

### F8 — Idraulica · F9 — Accumuli · F10 — Controllo
- Come nell'Excel (fogli 8, 12-13, 15), da formalizzare quando le
  fasi 0-7 sono implementate. Nota: F9 dipende dal trade-off deciso
  in F1 (il profilo temporale torna); F10 include la simulazione
  off-design che nell'Excel è già sopra la media.

### F11 — Economia (BOM, payback)
- FUORI dal core di dimensionamento per scelta esplicita di Michele
  (2026-07-14): l'Excel la contiene ma "campata a caso". Rientrerà
  quando il core sarà solido, con l'agente Economia.

---

## 3. Cosa cambia nella UI

- Nuovo flusso principale a fasi (wizard F0→F6 per la v0.5): ogni
  fase mostra decisioni, numeri derivati e gate; avanti solo a gate
  verdi, indietro sempre possibile e senza perdite.
- La pagina ciclo attuale RESTA come "laboratorio what-if" (gli
  slider hanno senso lì): etichettarla chiaramente come modalità
  analisi, separata dal progetto.
- I tre pulsanti agente vivono dentro ogni fase, col contesto della
  fase.

### Ispirazioni da strumenti esistenti (analisi REF.BOX, 2026-07-14)

REF.BOX (Everbyte) risolve il PUNTO DI BILANCIO: dati i componenti
scelti, un solver (Levenberg-Marquardt sui bilanci di energia/massa)
trova le temperature di saturazione REALI come incognite. Da
replicare in I.A.zz, in due mosse:

1. **F7 con modello "CDUV-like"**: prestazioni degli scambiatori in
   off-design a partire dai soli dati di targa (U corretto), senza
   geometria — sostituisce il margine cieco 1,2 in attesa delle
   correlazioni complete (campagna Heat Transfer).
2. **F6-bis — Verifica al punto di bilancio** (nuova fase, dopo la
   selezione): con compressore scelto (polinomi) + scambiatori
   (CDUV) + carico, risolvere T_evap/T_cond/Q reali del sistema.
   Chiude il cerchio: F4 decide l'INTENTO, F6-bis verifica la
   REALTÀ — il "doppio binario" applicato all'impianto intero.
   È anche il fondamento della simulazione off-design (F10).
   Dettaglio da REF.BOX: per i VSD con envelope dipendente dalla
   frequenza, rilassare il vincolo di carico per restare nel dominio.

Cosa REF.BOX non ha (nostra differenziazione confermata): agenti che
spiegano, guardrail pedagogici, intake conversazionale.

### Backlog UI (richieste registrate)

- **Schema d'impianto (P&I) auto-generato** (Michele, 2026-07-14):
  rappresentazione grafica dei componenti — compressore, evaporatore,
  condensatori, valvola, loop intermedi, accumuli — costruita
  dall'architettura del Project, nello stile degli schemi delle
  lezioni di heat pumps. Si aggiorna con le decisioni delle fasi
  (F2 architettura, F4 catena, F6 macchina scelta).

## 4. Ordine di implementazione proposto

1. **F4 + F5 + F6**: catena delle temperature → ciclo → selezione
   compressore col loop di ritorno. È la fetta minima che dimostra
   la sintesi (e riusa tutto l'esistente).
2. F1 (profilo carichi) e F2 (filtro architetture) semplificati.
3. F3 con l'agente Refrigeranti (nuovo, pattern fetta verticale).
4. F7 v0.5 (margine dichiarato), poi la campagna heat transfer.

## 5. Decisioni registrate

| Data | Decisione | Perché |
|---|---|---|
| 2026-07-13 | Fetta verticale prima dei moduli restanti | AI visibile subito |
| 2026-07-14 | Vincoli hard filtrano le architetture prima dell'efficienza | caso loop glicole/contaminazione |
| 2026-07-14 | Agente Refrigeranti dedicato in F3 | richiesta esplicita Michele |
| 2026-07-14 | Temperature derivate da catene di approcci, mai input liberi nel flusso di sintesi | assurdi impossibili per costruzione |
| 2026-07-14 | Economia fuori dal core v0.5 | dichiarata non rigorosa nell'Excel |
| 2026-07-14 | Margine scambiatori: dichiarato in v0.5, correlazioni rigorose in v1.0 | rigore prima, raffinamento poi |
