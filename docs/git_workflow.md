# Git in 5 minuti — la liturgia di fine sessione (per Michele)

## Il modello mentale (una volta per tutte)

Il tuo lavoro vive in TRE posti, in fila:

```
[file sul PC]  --commit-->  [album locale (.git)]  --push-->  [GitHub]
  modifichi                   foto permanente           copia nel cloud
```

- **Commit** = scattare una FOTO di tutto il progetto com'è adesso,
  con una didascalia. La foto resta sul TUO pc, per sempre, e puoi
  sempre tornarci. Senza commit, git non sa niente delle modifiche.
- **Push** = spedire le foto nuove su GitHub. Backup + condivisione.
- Regola d'oro: **commit spesso, push a fine sessione**. Un commit
  è gratis e reversibile; una modifica senza commit è a rischio.

## La liturgia con GitHub Desktop (3 click)

1. Apri **GitHub Desktop**. Controlla in alto a sinistra che
   "Current repository" sia **iazz-hpds** (se no: clic e selezionalo).
2. Tab **Changes** (a sinistra): vedi la lista dei file modificati.
   Cliccane uno per vedere le righe cambiate (verde = aggiunto,
   rosso = tolto). Dai un'occhiata: è l'ultimo controllo prima
   della foto — se vedi file inattesi, chiediti perché.
3. In basso a sinistra: scrivi il **messaggio** nel campo "Summary"
   (obbligatorio, breve, descrittivo: cosa e perché — es.
   "F0 intake + Frascold nel DB"). Poi bottone blu
   **Commit to main**. → Foto scattata.
4. In alto compare **Push origin** (con una freccietta ↑ e un
   numero = commit da spedire). Cliccalo. → Spedito.
5. Verifica (facoltativa): tab **History** = l'elenco delle tue
   foto; su github.com vedi gli stessi commit.

Fine. Tutta la liturgia sono i punti 1-4: seleziona repo → guarda
le modifiche → commit con messaggio → push.

## Gli intoppi classici

- **"Non vedo le mie modifiche in Changes"** → repo sbagliato
  selezionato in alto a sinistra, oppure OneDrive non ha finito di
  sincronizzare (aspetta la spunta verde sui file).
- **Il bottone dice "Fetch origin" invece di Push** → normale:
  clicca Fetch (controlla se sul cloud c'è roba nuova), poi
  comparirà Push se hai commit da spedire, o Pull se c'è da
  scaricare (succederà quando lavorerà anche il tuo amico).
- **Messaggio di conflitto** → per ora impossibile (lavori da solo
  su main). Quando sarete in due: chiedere a Claude, è il momento
  di imparare i branch.
- **Ho committato una cosa sbagliata** → niente panico: le foto non
  si perdono. Menu History → tasto destro sul commit → "Revert
  changes in commit" crea una foto che annulla quella. Mai
  cancellare a mano, sempre annullare con un nuovo commit.

## L'equivalente da terminale (per quando ti sentirai pro)

```
git status                      # cosa è cambiato?
git add .                       # metti tutto in posa
git commit -m "messaggio"       # scatta la foto
git push                        # spedisci
git log --oneline               # l'album
```

Identico a GitHub Desktop, senza mouse. Usa quello che preferisci:
sono due facce dello stesso motore.
