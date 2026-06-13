"""Index of the SFP debarred-supplier directory for RFC and name lookup.

Unlike 69-B (tax invoice mills), SFP lists suppliers debarred by internal
control organs — with a debarment period (plazo). Enables a strong signal:
a contract awarded WHILE the supplier was debarred.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from shared.fechas import parse_fecha
from shared.normalizacion import normalize

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "sfp_sancionados.json"


class SfpIndex:
    """Keeps EVERY debarment record per supplier — one company can be
    debarred more than once, and a contract must be checked against all
    of its windows."""

    def __init__(self, path: Path = RAW):
        self.by_rfc: dict[str, list[dict]] = {}
        self.by_name: dict[str, list[dict]] = {}
        self.records: list[dict] = []
        if not path.exists():
            print(f"WARN: {path} no existe — índice SFP vacío; "
                  "las señales SFP quedan desactivadas (corre scripts/fetch_sfp.py)")
            return
        for r in json.loads(path.read_text()):
            plazo = r.get("plazo") or {}
            rec = {
                "rfc": (r.get("rfc") or "").strip().upper(),
                "nombre": (r.get("nombre_razon_social") or "").strip(),
                "multa": r.get("multa"),
                "leyes": r.get("leyes_infringidas"),
                "institucion": r.get("institucion_dependencia"),
                "inicio": parse_fecha(plazo.get("fecha_inicial")),
                "fin": parse_fecha(plazo.get("fecha_final") or plazo.get("fecha_fin")),
                "plazo_txt": plazo.get("plazo_inha"),
            }
            self.records.append(rec)
            if rec["rfc"]:
                self.by_rfc.setdefault(rec["rfc"], []).append(rec)
            key = normalize(rec["nombre"])
            if len(key) >= 8:
                self.by_name.setdefault(key, []).append(rec)

    def match_rfc(self, rfc: str) -> list[dict]:
        return self.by_rfc.get((rfc or "").strip().upper(), [])

    def match_name(self, name: str) -> list[dict]:
        return self.by_name.get(normalize(name), [])

    @staticmethod
    def debarred_on(rec: dict, when: date | None) -> bool:
        """True if `when` falls inside this record's debarment window.

        A record without `fin` is a sanction with no debarment window (e.g.
        a fine-only record): it never counts as debarred.
        """
        if not when or not rec.get("inicio") or not rec.get("fin"):
            return False
        return rec["inicio"] <= when <= rec["fin"]

    @staticmethod
    def pick(records: list[dict], when: date | None) -> tuple[dict | None, bool]:
        """(record, durante): the window containing `when` if any window does,
        otherwise the most recent window with durante=False."""
        for rec in records:
            if SfpIndex.debarred_on(rec, when):
                return rec, True
        if not records:
            return None, False
        return max(records, key=lambda r: r["inicio"] or date.min), False
