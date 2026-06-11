"""In-memory index of the SAT 69-B list for fast name-based lookup.

Realtime awards expose supplier names only (no RFC), so matching is by strictly
normalized name. Every hit is a SCREEN requiring manual verification — homonyms
are possible. Definitivo = confirmed invoice mill; other statuses are context.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from datetime import datetime
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "sat_69b_completo.csv"

_SUFFIXES = re.compile(
    r"\b(S\.?A\.? DE C\.?V\.?|S DE RL DE CV|SAPI DE CV|S A P I DE C V|SC|S C|"
    r"AC|A C|SAB DE CV|SAS|SRL|S DE RL|SOFOM ENR?)\b",
    re.I,
)


def normalize(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = s.upper()
    s = _SUFFIXES.sub(" ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_date(s):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


class EfosIndex:
    def __init__(self, path: Path = RAW):
        self.by_name: dict[str, dict] = {}
        with open(path, encoding="cp1252", errors="replace") as fh:
            reader = csv.reader(fh)
            for _ in range(3):  # skip preamble + headers
                next(reader, None)
            for row in reader:
                if len(row) < 16 or len(row[1].strip()) < 12:
                    continue
                key = normalize(row[2])
                if len(key) < 8:
                    continue
                rec = {
                    "rfc": row[1].strip(),
                    "nombre": row[2].strip(),
                    "situacion": row[3].strip(),
                    "fecha_definitivo": _parse_date(row[15]) or _parse_date(row[13]),
                }
                prev = self.by_name.get(key)
                # prefer Definitivo, then most recent
                if prev is None or (rec["situacion"] == "Definitivo" and prev["situacion"] != "Definitivo"):
                    self.by_name[key] = rec

    def match(self, supplier_name: str) -> dict | None:
        return self.by_name.get(normalize(supplier_name))
