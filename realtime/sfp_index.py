"""Index of the SFP debarred-supplier directory for RFC and name lookup.

Unlike 69-B (tax invoice mills), SFP lists suppliers debarred by internal
control organs — with a debarment period (plazo). Enables a strong signal:
a contract awarded WHILE the supplier was debarred.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from .efos_index import normalize

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "sfp_sancionados.json"


def _d(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


class SfpIndex:
    def __init__(self, path: Path = RAW):
        self.by_rfc: dict[str, dict] = {}
        self.by_name: dict[str, dict] = {}
        self.records: list[dict] = []
        if not path.exists():
            return
        for r in json.loads(path.read_text()):
            plazo = r.get("plazo") or {}
            rec = {
                "rfc": (r.get("rfc") or "").strip().upper(),
                "nombre": (r.get("nombre_razon_social") or "").strip(),
                "multa": r.get("multa"),
                "leyes": r.get("leyes_infringidas"),
                "institucion": r.get("institucion_dependencia"),
                "inicio": _d(plazo.get("fecha_inicial")),
                "fin": _d(plazo.get("fecha_final") or plazo.get("fecha_fin")),
                "plazo_txt": plazo.get("plazo_inha"),
            }
            self.records.append(rec)
            if rec["rfc"]:
                self.by_rfc[rec["rfc"]] = rec
            key = normalize(rec["nombre"])
            if len(key) >= 8:
                self.by_name.setdefault(key, rec)

    def match_rfc(self, rfc: str) -> dict | None:
        return self.by_rfc.get((rfc or "").strip().upper())

    def match_name(self, name: str) -> dict | None:
        return self.by_name.get(normalize(name))

    @staticmethod
    def debarred_on(rec: dict, when: date | None) -> bool:
        """True if `when` falls inside the debarment window."""
        if not when or not rec.get("inicio"):
            return False
        if when < rec["inicio"]:
            return False
        return rec["fin"] is None or when <= rec["fin"]
