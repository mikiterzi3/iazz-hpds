# Validazione contro il caso Thomas (HP_THOM_v2.4.xlsx)

**Data: 2026-06-11** — eseguita in autonomia da Claude su mandato di
Michele. Documento scritto per essere riletto (e corretto) da Michele
senza dover ripercorrere il codice.

## Cosa è stato fatto

Dall'Excel `HP_THOM_v2.4.xlsx` sono stati estratti i valori di
riferimento di due fogli e trasformati in test automatici:

1. **`4_CICLO_TERMO`** → 15 grandezze per regime (pressioni, entalpie,
   COP, portate, densità aspirazione) confrontate con `compute_cycle`.
2. **`5_COMPRESSORE`** → i 10 coefficienti EN 12900 del Bitzer
   4NES-14Y-40P (fit a 33 Hz, range T_ev −15..+9 °C, T_cond 12..85 °C,
   scala lineare f/33) sono diventati
   `src/iazz/data/compressors/bitzer/4nes-14y-40p_r1234ze.json`,
   valutati dal nuovo modulo `compute/compressor.py` e confrontati con
   la calcolatrice what-if del foglio.

**Risultato: tutti i confronti passano** (`pytest tests/test_validation_thomas.py`
→ 7 passed). La checklist F2 è chiusa; F3 è iniziata (formato Bitzer
fatto, mancano i parser Danfoss).

## Dove sono i numeri (e come modificarli)

| Cosa | File | Come si modifica |
|---|---|---|
| Valori attesi + tolleranze | `tests/fixtures/thomas_expected.json` | a mano: campi `value` e `tol_pct`, c'è un `_README` in testa |
| Coefficienti Bitzer | `src/iazz/data/compressors/bitzer/4nes-14y-40p_r1234ze.json` | a mano: `_README` in testa spiega formula e ordine c1..c10 |
| Logica di confronto | `tests/test_validation_thomas.py` | solo se cambia la *struttura*, non per cambiare un valore |

**Regola**: se un test di validazione fallisce e il nuovo valore è
giustificato, si aggiorna la fixture e si annota QUI il perché. Il
codice dei test non si tocca.

## Confronto in sintesi (regime A, worst case)

| Grandezza | Excel | I.A.zz | Scost. |
|---|---:|---:|---:|
| p_evap [bar] | 2,01 | 2,010 | ~0% |
| p_cond [bar] | 7,66 | 7,665 | ~0,1% |
| h1 [kJ/kg] | 387,2 | 387,21 | ~0% |
| h2 [kJ/kg] | 423,9 | 423,93 | ~0% |
| T mandata [°C] | 53,5 | 53,54 | ~0,1% |
| COP cooling | 3,7193 | 3,7193 | ~0% |
| Portata [kg/s] | 0,15940 | 0,15940 | ~0% |
| ρ aspirazione [kg/m³] | 10,66 | ~10,66 | <1% |
| V aspirato [m³/h] | 53,83 | ~53,8 | <1% |

Lo scostamento è ~nullo perché il foglio Excel era stato popolato con
`cycle_v2.py` (stesso CoolProp, stesse ipotesi SH=5K, SC=3K, η=0,70):
stiamo verificando di aver replicato correttamente quella libreria.
Il regime B è analogo (COP 4,2470, tutti i valori entro tolleranza).

## Compressore Bitzer: cosa torna e cosa no (ed è normale)

**Torna esattamente** (scostamento <0,01%): la calcolatrice what-if del
foglio. Polinomio a (−2, 40) × 56/33 → Q=21,507 kW, P=5,939 kW,
COP=3,621. Conferma che il valutatore EN 12900 e lo scaling sono
implementati come nell'Excel.

**Torna con scarto 3-6%**: le prestazioni di catalogo Bitzer a 56 Hz
(Q=22,2 kW, P=6,29 kW, COP=3,529). Il motivo è documentato anche nella
fixture: lo **scaling lineare f/33 è un'approssimazione** — il software
Bitzer usa mappe reali per frequenza, dove rendimento volumetrico e
perdite non scalano linearmente. Tolleranze impostate di conseguenza
(4-6%). Se servirà più precisione: fit multi-frequenza in F4.

**Cross-validation dei due binari** (il cuore di I.A.zz): portata del
ciclo CoolProp 573,9 kg/h vs polinomio Bitzer 567,1 kg/h → **1,2%** di
scostamento. I due calcoli sono indipendenti (NIST da una parte, banco
prova Bitzer dall'altra): che concordino entro il 5% è la conferma che
il modello è sano. Questo check è ora un test permanente
(`test_cross_validation_cycle_vs_polynomial`).

## Modifiche al codice fatte in questa sessione di validazione

1. `CycleResults` ha due campi nuovi: `rho_suction_kg_m3` e
   `V_dot_suction_m3_h` (densità e volume aspirato — servono per la
   selezione compressore in F4 ed erano validabili contro l'Excel).
2. Nuovo modulo `src/iazz/compute/compressor.py`: `CompressorMap` +
   valutatore EN 12900 + scala in frequenza + blocco delle
   estrapolazioni fuori range (ValueError parlante).
3. Nuovo dato `data/compressors/bitzer/4nes-14y-40p_r1234ze.json`.

## Note e limiti (da rivedere con Michele)

- L'Excel caricato è **v2.4**, il dossier cita v2.5: se la 2.5 ha
  numeri diversi, basta aggiornare le fixture (vedi tabella sopra).
- Lo scaling lineare in frequenza è applicato anche a portata e
  corrente (il foglio lo dichiara solo per Q e P): assunzione fisica
  ragionevole (macchina volumetrica) ma da confermare con i dati
  Bitzer multi-frequenza.
- `Q_cond` del compressore è stimato come Q+P (bilancio macchina senza
  perdite a ambiente): coerente con l'Excel, leggermente ottimista.
- I fogli scambiatori, glicole, tank, BOM e payback dell'Excel NON sono
  ancora usati: serviranno per i moduli delle fasi successive (v1.0).
