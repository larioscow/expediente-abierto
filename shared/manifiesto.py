"""Cadena de evidencia (MANIFEST.tsv) y nombres de archivo seguros —
utilidades de procedencia usadas por realtime, casework y scripts."""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "raw" / "MANIFEST.tsv"


def safe_filename(s: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", (s or "sin_numero").strip())


def read_manifest(path: Path = MANIFEST) -> dict:
    out = {}
    if not Path(path).exists():
        return out
    with open(path) as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            out[row["file"]] = {"retrieved_at": row["retrieved_at"][:10],
                                "sha256": row["sha256"]}
    return out
