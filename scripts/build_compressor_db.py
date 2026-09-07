"""Converte gli export polinomi Danfoss (.xlsx) nel DB JSON interno.

Uso:
    python scripts/build_compressor_db.py [--src DIR] [--out DIR]

PROBLEMA
    I polinomi arrivano come file Excel eterogenei per vendor. Il tool
    deve leggerli da un formato UNICO, controllato da noi.

CONCETTO
    Questo script è "usa e getta ripetibile": prende una cartella di
    .xlsx Danfoss, li parsa con iazz.parsers.danfoss_xls e scrive un
    JSON per macchina in data/compressors/danfoss/. Se un domani Danfoss
    cambia layout, si aggiorna il parser e si rigenera tutto.

SCELTE
    - I range di validità Te/Tc NON sono negli export Danfoss: qui sono
      impostati a un envelope PROVVISORIO conservativo, uguale per
      tutte le macchine, e marcati nel _README del JSON. Da sostituire
      coi valori letti in Coolselector2 (scheda "Operating envelope").
    - Nome file output: <modello>_<refrigerante>.json, minuscolo.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from iazz.parsers.danfoss_xls import parse_workbook, to_map_dict

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = REPO_ROOT / "tests" / "fixtures" / "danfoss"
DEFAULT_OUT = REPO_ROOT / "src" / "iazz" / "data" / "compressors" / "danfoss"

# Envelope PROVVISORIO (vedi SCELTE nel docstring).
T_EVAP_RANGE_C = (-15.0, 10.0)
T_COND_RANGE_C = (30.0, 60.0)


def slug(text: str) -> str:
    """Nome file sicuro: minuscole, alfanumerici e trattini."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    files = sorted(args.src.glob("*.xlsx"))
    if not files:
        raise SystemExit(f"Nessun .xlsx in {args.src} — convertire prima "
                         "gli .xls con: soffice --headless --convert-to "
                         "xlsx *.xls")
    args.out.mkdir(parents=True, exist_ok=True)

    for f in files:
        dwb = parse_workbook(f)
        data = to_map_dict(
            dwb, T_EVAP_RANGE_C, T_COND_RANGE_C,
            source=f"{f.name} (export Coolselector2), "
                   f"convertito e parsato da build_compressor_db.py",
        )
        out = args.out / f"{slug(dwb.model)}_{slug(dwb.refrigerant)}.json"
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        kind = "VSD ext30" if dwb.is_vsd else "50 Hz fisso"
        print(f"  {f.name}  →  {out.name}  [{kind}]")


if __name__ == "__main__":
    main()
