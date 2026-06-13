#!/usr/bin/env python
"""Alarma de frescura: ¿qué tan viejos son los datos fuente?

Lee data/raw/MANIFEST.tsv (cadena de evidencia: cada descarga registra URL,
timestamp y sha256), calcula la edad de la última descarga real (>0 bytes) de
cada fuente y la compara contra su umbral. Escribe findings/freshness.json
(rastreado en git: el sitio y CI construyen con la cifra) e imprime una tabla.

Sale con código 1 si alguna fuente esperada está atrasada o ausente — para
que un cron lo registre como fallo visible, nunca silencio.

Uso: python scripts/check_freshness.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "raw" / "MANIFEST.tsv"
MANIFIESTO_PNT = ROOT / "data" / "raw" / "pnt" / "manifiesto.json"
DOF_CIRCULARES = ROOT / "data" / "raw" / "dof_circulares.json"
OUT = ROOT / "findings" / "freshness.json"


class Retrieval(NamedTuple):
    retrieved_at: datetime
    sha: str


def thresholds(now: datetime) -> dict[str, int]:
    """Umbral de edad (días) por fuente. Solo fuentes vivas: los CSV anuales
    de años cerrados se congelan en el portal y no caducan."""
    return {
        f"contratos_{now.year}.csv": 7,    # ComprasMX publica con rezago; ausente = alarma, no error
        "sat_69b_completo.csv": 35,        # SAT actualiza el 69-B mensualmente
        "sfp_sancionados.json": 7,         # directorio de inhabilitados: ventanas activas
        "cfe_contratos_adjudicados.csv": 120,  # ATDT lo refresca esporádicamente
        "pnt/manifiesto.json": 7,          # refresh incremental diario en el batch
        "dof_circulares.json": 7,          # alerta temprana: refresh diario
    }


def parse_manifest(text: str) -> dict[str, Retrieval]:
    """Última descarga real (>0 bytes) por archivo."""
    latest: dict[str, Retrieval] = {}
    for line in text.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        ts_raw, sha, nbytes, fname = parts[0], parts[1], parts[2], parts[3]
        try:
            ts = datetime.fromisoformat(ts_raw)
            if int(nbytes) <= 0:
                continue
        except ValueError:
            continue
        if fname not in latest or ts > latest[fname].retrieved_at:
            latest[fname] = Retrieval(ts, sha)
    return latest


def pnt_retrieval(path: Path = MANIFIESTO_PNT) -> Retrieval | None:
    """El refresh PNT más reciente según su manifiesto (entrega más nueva)."""
    if not path.exists():
        return None
    try:
        entregas = json.loads(path.read_text()).values()
        ts = max(datetime.fromisoformat(v["ts"]) for v in entregas)
    except (json.JSONDecodeError, KeyError, ValueError):
        return None
    return Retrieval(ts, "")


def dof_retrieval(path: Path = DOF_CIRCULARES) -> Retrieval | None:
    """El último refresh del índice DOF (campo `generado`)."""
    if not path.exists():
        return None
    try:
        ts = datetime.fromisoformat(json.loads(path.read_text())["generado"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return None
    return Retrieval(ts, "")


def evaluate(latest: dict[str, Retrieval], now: datetime) -> list[dict]:
    """Una fila por fuente conocida + fuentes esperadas ausentes."""
    limites = thresholds(now)
    rows = []
    for fname in sorted(set(latest) | set(limites)):
        rec = latest.get(fname)
        limite = limites.get(fname)
        if rec is None:
            rows.append({"archivo": fname, "descargado": None,
                         "edad_dias": None, "limite_dias": limite,
                         "vigente": False,
                         "nota": "fuente esperada sin descarga registrada"})
            continue
        edad = (now - rec.retrieved_at).days
        rows.append({
            "archivo": fname,
            "descargado": rec.retrieved_at.isoformat(),
            "edad_dias": edad,
            "limite_dias": limite,
            "vigente": limite is None or edad <= limite,
        })
    return rows


def main() -> int:
    now = datetime.now(timezone.utc)
    latest = parse_manifest(MANIFEST.read_text(encoding="utf-8"))
    for nombre, rec in (("pnt/manifiesto.json", pnt_retrieval()),
                        ("dof_circulares.json", dof_retrieval())):
        if rec is not None:
            latest[nombre] = rec
    rows = evaluate(latest, now)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generado": now.isoformat(), "fuentes": rows},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    atrasadas = [r for r in rows if not r["vigente"]]
    for r in rows:
        marca = "OK " if r["vigente"] else "!! "
        edad = "ausente" if r["edad_dias"] is None else f"{r['edad_dias']}d"
        limite = "-" if r["limite_dias"] is None else f"{r['limite_dias']}d"
        print(f"{marca}{r['archivo']:<35} edad={edad:<9} limite={limite}")
    if atrasadas:
        print(f"ALERTA: {len(atrasadas)} fuente(s) atrasadas o ausentes")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
