"""In-memory index of the SAT 69-B list for fast name-based lookup.

Realtime awards expose supplier names only (no RFC), so matching is by strictly
normalized name. Every hit is a SCREEN requiring manual verification — homonyms
are possible. Definitivo = confirmed invoice mill; other statuses are context.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from shared.esquemas import EFOS_COLS
from shared.fechas import parse_fecha
from shared.normalizacion import normalize

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "sat_69b_completo.csv"




def _rank(rec: dict) -> tuple[bool, date]:
    """Homonym preference: Definitivo first, then most recent definitivo date."""
    return (rec["situacion"] == "Definitivo",
            rec["fecha_definitivo"] or date.min)


class EfosIndex:
    def __init__(self, path: Path = RAW):
        self.by_name: dict[str, dict] = {}
        with open(path, encoding="cp1252", errors="replace") as fh:
            reader = csv.reader(fh)
            for _ in range(3):  # skip preamble + headers
                next(reader, None)
            for row in reader:
                if len(row) < len(EFOS_COLS):
                    continue
                r = dict(zip(EFOS_COLS, (v.strip() for v in row)))
                if len(r["rfc"]) < 12:
                    continue
                key = normalize(r["nombre"])
                if len(key) < 8:
                    continue
                rec = {
                    "rfc": r["rfc"],
                    "nombre": r["nombre"],
                    "situacion": r["situacion"],
                    "fecha_definitivo": parse_fecha(r["pub_dof_definitivos"])
                    or parse_fecha(r["pub_sat_definitivos"]),
                }
                prev = self.by_name.get(key)
                if prev is None or _rank(rec) > _rank(prev):
                    self.by_name[key] = rec

    def match_name(self, supplier_name: str) -> dict | None:
        return self.by_name.get(normalize(supplier_name))

    match = match_name  # alias de compatibilidad
