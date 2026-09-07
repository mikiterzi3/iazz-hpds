# Knowledge base degli agenti AI

Una cartella per agente. I file `.md` qui dentro sono generati da
`scripts/ingest_pdfs.py` a partire dai PDF che **ogni utente fornisce**.

> ⚠️ **Il contenuto della knowledge base non fa parte del repository.**
> Né i PDF sorgente né il markdown estratto vengono versionati: sono
> materiale didattico e scientifico di terzi, coperto dal diritto d'autore
> dei rispettivi autori ed editori. `.gitignore` esclude entrambi.
> Chi usa il progetto costruisce la propria KB con le proprie fonti.

Esempio:

    python scripts/ingest_pdfs.py pdf/L1b_basic_cycle.pdf --agent thermodynamic

Cartelle previste: thermodynamic, compressor, heat_exchanger, hydraulic,
control_safety, economics, documentation.
