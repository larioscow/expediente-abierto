"""Persistent case store — verification work must accumulate.

Two tables in one DuckDB file (data/cases.duckdb):

  alerts — append-only history of every alert ever emitted (dedup on uuid+ts)
  cases  — one row per procedure with a human-owned verification state:
           nuevo → verificando → verificado → denunciado → publicado | descartado.
           Re-ingestion updates scores/timestamps but NEVER touches the
           estado or the analyst's nota.

CLI:
    python -m realtime.store import           # backfill from alerts.jsonl
    python -m realtime.store list [estado]
    python -m realtime.store set <uuid> <estado> [nota...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "cases.duckdb"
ALERTS_JSONL = ROOT / "findings" / "alerts.jsonl"

ESTADOS = ("nuevo", "verificando", "verificado", "denunciado",
           "publicado", "descartado")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
  ts VARCHAR, uuid VARCHAR, numero VARCHAR, score INTEGER,
  change VARCHAR, payload JSON
);
CREATE TABLE IF NOT EXISTS cases (
  uuid VARCHAR PRIMARY KEY, numero VARCHAR, nombre VARCHAR,
  dependencia VARCHAR, max_score INTEGER,
  estado VARCHAR DEFAULT 'nuevo', nota VARCHAR,
  first_seen VARCHAR, last_alert VARCHAR, updated_at VARCHAR
);
"""


class CaseStore:
    def __init__(self, path: Path = DB):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(str(path))
        self._con.execute(_SCHEMA)

    def ingest_alerts(self, alerts: list[dict]) -> int:
        """Insert unseen alerts; create/update their cases. Returns number of
        alert rows actually inserted."""
        inserted = 0
        for a in alerts:
            ts, uuid = a.get("ts"), a.get("uuid")
            dup = self._con.execute(
                "SELECT 1 FROM alerts WHERE uuid = ? AND ts = ?",
                [uuid, ts]).fetchone()
            if dup:
                continue
            self._con.execute(
                "INSERT INTO alerts VALUES (?, ?, ?, ?, ?, ?)",
                [ts, uuid, a.get("numero"), a.get("score"),
                 a.get("change"), json.dumps(a, ensure_ascii=False)])
            inserted += 1
            if self._con.execute("SELECT 1 FROM cases WHERE uuid = ?",
                                 [uuid]).fetchone():
                self._con.execute("""
                    UPDATE cases SET max_score = greatest(max_score, ?),
                                     last_alert = ?, updated_at = ?
                    WHERE uuid = ?""", [a.get("score"), ts, ts, uuid])
            else:
                self._con.execute("""
                    INSERT INTO cases (uuid, numero, nombre, dependencia,
                                       max_score, estado, first_seen,
                                       last_alert, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'nuevo', ?, ?, ?)""",
                    [uuid, a.get("numero"), a.get("nombre"),
                     a.get("dependencia"), a.get("score"), ts, ts, ts])
        return inserted

    def ensure_case(self, uuid: str, numero: str, nombre: str,
                    dependencia: str | None = None, score: int | None = None):
        """Registra un caso (estado nuevo) sin generar fila de alerta.
        No toca casos existentes."""
        if self._con.execute("SELECT 1 FROM cases WHERE uuid = ?",
                             [uuid]).fetchone():
            return
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        self._con.execute("""
            INSERT INTO cases (uuid, numero, nombre, dependencia, max_score,
                               estado, first_seen, last_alert, updated_at)
            VALUES (?, ?, ?, ?, ?, 'nuevo', ?, ?, ?)""",
            [uuid, numero, nombre, dependencia, score, now, now, now])

    def set_state(self, uuid: str, estado: str, nota: str | None = None):
        if estado not in ESTADOS:
            raise ValueError(f"estado inválido {estado!r}; usa uno de {ESTADOS}")
        if not self._con.execute("SELECT 1 FROM cases WHERE uuid = ?",
                                 [uuid]).fetchone():
            raise ValueError(f"caso desconocido: {uuid}")
        if nota is not None:
            self._con.execute(
                "UPDATE cases SET estado = ?, nota = ? WHERE uuid = ?",
                [estado, nota, uuid])
        else:
            self._con.execute("UPDATE cases SET estado = ? WHERE uuid = ?",
                              [estado, uuid])

    def cases(self, estado: str | None = None) -> pd.DataFrame:
        q = "SELECT * FROM cases"
        args = []
        if estado:
            q += " WHERE estado = ?"
            args.append(estado)
        return self._con.execute(q + " ORDER BY max_score DESC", args).fetchdf()

    def history(self, uuid: str) -> list[dict]:
        rows = self._con.execute(
            "SELECT payload FROM alerts WHERE uuid = ? ORDER BY ts",
            [uuid]).fetchall()
        return [json.loads(r[0]) for r in rows]


def main(argv: list[str]):
    cmd = argv[0] if argv else "list"
    store = CaseStore()
    if cmd == "import":
        if not ALERTS_JSONL.exists():
            print("no alerts.jsonl; nothing to import")
            return
        alerts = [json.loads(ln)
                  for ln in ALERTS_JSONL.read_text().splitlines() if ln.strip()]
        n = store.ingest_alerts(alerts)
        print(f"imported {n} new alerts ({len(alerts)} read)")
    elif cmd == "list":
        df = store.cases(argv[1] if len(argv) > 1 else None)
        cols = ["uuid", "numero", "dependencia", "max_score", "estado", "nota"]
        print(df[cols].to_string(index=False) if len(df) else "(sin casos)")
    elif cmd == "set":
        if len(argv) < 3:
            sys.exit("uso: python -m realtime.store set <uuid> <estado> [nota...]")
        store.set_state(argv[1], argv[2],
                        " ".join(argv[3:]) if len(argv) > 3 else None)
        print(f"{argv[1]} -> {argv[2]}")
    else:
        sys.exit(f"comando desconocido: {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
