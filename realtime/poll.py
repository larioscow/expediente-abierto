#!/usr/bin/env python
"""Realtime poll of ComprasMX: detect risky procedures/awards as they publish.

One poll:
  1. fetch most-recent procedures (list endpoint)
  2. diff against the seen-store; for new or newly-concluded ones,
  3. fetch the detail (awards), score procedure- and award-level risk,
  4. append alerts (score >= threshold) to findings/alerts.jsonl,
  5. update the seen-store.

Run on a schedule (cron / launchd). Near-real-time: the portal publishes
procedures continuously, unlike the annual bulk CSV.

Usage: python -m realtime.poll [--max-detail N] [--threshold S] [--rows R]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .comprasmx_client import ComprasMXClient
from .efos_index import EfosIndex
from .sfp_index import SfpIndex
from .risk import assess_awards, assess_procedure

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state" / "seen.json"
ALERTS = ROOT / "findings" / "alerts.jsonl"


def load_seen() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {}


def save_seen(seen: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(seen, ensure_ascii=False, indent=0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-detail", type=int, default=40,
                    help="cap detail fetches per poll (politeness)")
    ap.add_argument("--threshold", type=int, default=2, help="min score to alert")
    ap.add_argument("--rows", type=int, default=100)
    ap.add_argument("--no-headless", action="store_true")
    args = ap.parse_args()

    now = datetime.now(timezone.utc).isoformat()
    seen = load_seen()
    efos = EfosIndex()
    sfp = SfpIndex()
    new_alerts = []
    detail_budget = args.max_detail
    n_new = n_changed = 0

    with ComprasMXClient(headless=not args.no_headless) as client:
        procedures = client.fetch_recent(rows=args.rows)
        print(f"[{now}] fetched {len(procedures)} procedures")

        for p in procedures:
            prev = seen.get(p.uuid)
            is_new = prev is None
            is_changed = prev is not None and prev.get("estatus") != p.estatus
            if is_new:
                n_new += 1
            elif is_changed:
                n_changed += 1
            else:
                continue

            registro, awards = (None, [])
            concluded = any(k in p.estatus.upper() for k in ("ADJUDIC", "CONCLU", "FALLO"))
            if detail_budget > 0 and (concluded or is_new):
                registro, awards = client.fetch_detail(p.uuid)
                detail_budget -= 1

            a = assess_procedure(p, registro)
            a = assess_awards(a, awards, efos, sfp)

            seen[p.uuid] = {"estatus": p.estatus, "numero": p.numero,
                            "first_seen": (prev or {}).get("first_seen", now),
                            "last_seen": now, "score": a.score}

            if a.score >= args.threshold:
                alert = {
                    "ts": now, "uuid": p.uuid, "numero": p.numero,
                    "nombre": p.nombre, "dependencia": p.siglas,
                    "estatus": p.estatus, "tipo": p.tipo_procedimiento,
                    "entidad": p.entidad, "score": a.score,
                    "reasons": a.reasons, "awards_flagged": a.awards_flagged,
                    "url": (
                        "https://upcp-compranet.buengobierno.gob.mx/sitiopublico/#/"
                        f"sitiopublico/detalle/{p.uuid}/procedimiento"
                    ),
                    "change": "new" if is_new else "status_change",
                }
                new_alerts.append(alert)

    if new_alerts:
        ALERTS.parent.mkdir(parents=True, exist_ok=True)
        with open(ALERTS, "a", encoding="utf-8") as fh:
            for al in sorted(new_alerts, key=lambda x: -x["score"]):
                fh.write(json.dumps(al, ensure_ascii=False) + "\n")

    save_seen(seen)
    print(f"[{now}] new={n_new} changed={n_changed} alerts={len(new_alerts)} "
          f"(detail fetches used={args.max_detail - detail_budget})")
    for al in sorted(new_alerts, key=lambda x: -x["score"])[:10]:
        print(f"  score {al['score']:>2} | {al['dependencia']:<10} | {al['numero']}")
        for r in al["reasons"]:
            print(f"            - {r}")


if __name__ == "__main__":
    main()
