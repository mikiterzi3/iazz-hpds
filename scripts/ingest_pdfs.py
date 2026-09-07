"""Knowledge extractor v0: PDF didattico → markdown strutturato (D4).

PROBLEMA
    Gli agenti AI previsti dall'architettura (7, oggi implementato il solo termodinamico) hanno bisogno di una knowledge base testuale. Servono
    79 PDF didattici, ma un PDF non si può "dare in pasto" comodamente
    a un LLM: serve testo pulito, diviso per pagina, con metadati.

CONCETTO
    Pipeline minima: PDF → estrazione testo (pypdf) → pulizia → markdown
    con intestazione YAML (frontmatter) che dice da dove viene il
    contenuto. Il markdown finisce in `knowledge/<agente>/<nome>.md`
    e diventa il mattone della KB (in F5 ci costruiremo sopra il RAG).

USO
    python scripts/ingest_pdfs.py percorso/al/file.pdf --agent thermodynamic
    python scripts/ingest_pdfs.py cartella_pdf/ --agent heat_exchanger

SCELTE
    - pypdf e non OCR: i nostri PDF sono "nativi" (testo selezionabile).
      Se un PDF è una scansione, lo segnaliamo e si valuterà OCR a parte.
    - Un file markdown per PDF, una sezione per pagina: così in fase RAG
      potremo citare "L1b, pagina 12" nelle risposte degli agenti.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from pypdf import PdfReader

# Radice del repo = cartella sopra a scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"

AGENTS = [
    "thermodynamic", "compressor", "heat_exchanger", "hydraulic",
    "control_safety", "economics", "documentation",
]


def clean_text(raw: str) -> str:
    """Pulizia leggera del testo estratto.

    I PDF accademici producono artefatti tipici: spazi multipli,
    trattini di sillabazione a fine riga, righe vuote ripetute.
    NON aggressiva: meglio un po' di rumore che perdere contenuto.
    """
    text = raw.replace("\r\n", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)   # sillabazione: "com-\npressore"
    text = re.sub(r"[ \t]+", " ", text)            # spazi multipli
    text = re.sub(r"\n{3,}", "\n\n", text)         # max 1 riga vuota
    return text.strip()


def slugify(name: str) -> str:
    """Nome file sicuro: 'L1b basic cycle.pdf' → 'l1b_basic_cycle'."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower())
    return slug.strip("_")


def ingest_pdf(pdf_path: Path, agent: str) -> Path:
    """Estrae un PDF e scrive il markdown nella KB dell'agente.

    Args:
        pdf_path: percorso del PDF da processare.
        agent: nome dell'agente destinatario (cartella in knowledge/).

    Returns:
        Percorso del file markdown prodotto.
    """
    reader = PdfReader(pdf_path)
    out_dir = KNOWLEDGE_DIR / agent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slugify(pdf_path.stem)}.md"

    lines = [
        "---",
        f"source: {pdf_path.name}",
        f"agent: {agent}",
        f"pages: {len(reader.pages)}",
        f"ingested: {date.today().isoformat()}",
        "extractor: ingest_pdfs.py v0",
        "---",
        "",
        f"# {pdf_path.stem}",
        "",
    ]

    empty_pages = 0
    for i, page in enumerate(reader.pages, start=1):
        text = clean_text(page.extract_text() or "")
        if not text:
            empty_pages += 1
            text = "*(pagina senza testo estraibile — figura o scansione?)*"
        lines += [f"## Pagina {i}", "", text, ""]

    out_path.write_text("\n".join(lines), encoding="utf-8")

    if empty_pages > len(reader.pages) / 2:
        print(f"  ⚠ {pdf_path.name}: {empty_pages}/{len(reader.pages)} "
              "pagine vuote — probabile scansione, servirà OCR.")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estrae testo da PDF didattici verso la knowledge base."
    )
    parser.add_argument("path", type=Path,
                        help="File PDF singolo o cartella di PDF")
    parser.add_argument("--agent", choices=AGENTS, required=True,
                        help="Agente destinatario (cartella knowledge/)")
    args = parser.parse_args()

    if args.path.is_dir():
        pdfs = sorted(args.path.glob("*.pdf"))
    elif args.path.suffix.lower() == ".pdf":
        pdfs = [args.path]
    else:
        sys.exit(f"Errore: {args.path} non è un PDF né una cartella.")

    if not pdfs:
        sys.exit(f"Nessun PDF trovato in {args.path}.")

    print(f"Processo {len(pdfs)} PDF → knowledge/{args.agent}/")
    for pdf in pdfs:
        out = ingest_pdf(pdf, args.agent)
        print(f"  ✓ {pdf.name} → {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
