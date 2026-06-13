#!/usr/bin/env python
"""Realtime poll of ComprasMX: detect risky procedures/awards as they publish.

One poll:
  1. fetch most-recent procedures (list endpoint)
  2. diff against the seen-store; for new or newly-concluded ones,
  3. fetch the detail (awards), score procedure- and award-level risk,
  4. append alerts (score >= threshold) to findings/alerts.jsonl,
  5. update the seen-store (pruning entries not seen for 90 days).

A failed detail fetch is logged and skipped — it never aborts the poll or
loses the seen-state of the other procedures.

Run on a schedule (cron / launchd). Near-real-time: the portal publishes
procedures continuously, unlike the annual bulk CSV.

Usage: python -m realtime.poll [--max-detail N] [--threshold S]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shared.ramos import estado_de_numero

from .comprasmx_client import DETAIL_SPA, ComprasMXClient
from .dof_index import DofIndex
from .efos_index import EfosIndex
from .packets import write_packets
from .sfp_index import SfpIndex
from .store import CaseStore
from .risk import assess_awards, assess_procedure

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state" / "seen.json"
ALERTS = ROOT / "findings" / "alerts.jsonl"
SEEN_MAX_AGE_DAYS = 90


def load_seen() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARN: {STATE} ilegible ({e}); empezando con estado vacío")
        return {}


def save_seen(seen: dict):
    """Escritura atómica (tmp + rename): un crash a mitad de escritura no
    debe corromper el estado y matar todos los polls futuros."""
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(seen, ensure_ascii=False, indent=0))
    tmp.replace(STATE)


def prune_seen(seen: dict, now: str, max_age_days: int = SEEN_MAX_AGE_DAYS) -> dict:
    """Drop entries not seen for `max_age_days` (entries without a timestamp
    are kept — they'll get one on their next appearance)."""
    cutoff = datetime.fromisoformat(now) - timedelta(days=max_age_days)
    out = {}
    for uuid, rec in seen.items():
        ts = rec.get("last_seen")
        try:
            stale = ts is not None and datetime.fromisoformat(ts) < cutoff
        except ValueError:
            stale = False
        if not stale:
            out[uuid] = rec
    return out


def poll_once(client, efos: EfosIndex, sfp: SfpIndex, seen: dict, now: str,
              *, dof: DofIndex | None = None, max_detail: int = 40,
              threshold: int = 2, pages: int = 1) -> tuple[list[dict], dict]:
    """Process one poll against `client`, mutating `seen` in place.
    Returns (alerts, stats)."""
    procedures = client.fetch_recent(pages=pages)
    alerts: list[dict] = []
    stats = {"fetched": len(procedures), "new": 0, "changed": 0,
             "errors": 0, "detail_used": 0}
    budget = max_detail

    for p in procedures:
        prev = seen.get(p.uuid)
        is_new = prev is None
        is_changed = prev is not None and prev.get("estatus") != p.estatus
        if not (is_new or is_changed):
            continue
        stats["new" if is_new else "changed"] += 1

        registro, awards = None, []
        concluded = any(k in p.estatus.upper() for k in ("ADJUDIC", "CONCLU", "FALLO"))
        if budget > 0 and (concluded or is_new):
            try:
                registro, awards = client.fetch_detail(p.uuid)
                budget -= 1
            except Exception as e:  # one bad fetch must not kill the poll
                stats["errors"] += 1
                print(f"WARN: detail fetch failed for {p.uuid}: {e}")

        a = assess_procedure(p, registro)
        a = assess_awards(a, awards, efos, sfp, dof)

        seen[p.uuid] = {"estatus": p.estatus, "numero": p.numero,
                        "first_seen": (prev or {}).get("first_seen", now),
                        "last_seen": now, "score": a.score}

        if a.score >= threshold:
            alert = {
                "ts": now, "uuid": p.uuid, "numero": p.numero,
                "nombre": p.nombre, "dependencia": p.siglas,
                "estatus": p.estatus, "tipo": p.tipo_procedimiento,
                "entidad": p.entidad, "score": a.score,
                "reasons": a.reasons, "awards_flagged": a.awards_flagged,
                "url": DETAIL_SPA.format(uuid=p.uuid),
                "change": "new" if is_new else "status_change",
            }
            # compra estatal/municipal con recursos federales (ramo 60-91)
            estado = estado_de_numero(p.numero)
            if estado:
                alert["orden_gobierno"] = "GEM"
                alert["estado_comprador"] = estado
            alerts.append(alert)

    stats["detail_used"] = max_detail - budget
    return alerts, stats


def write_alerts(alerts: list[dict]):
    if not alerts:
        return
    ALERTS.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERTS, "a", encoding="utf-8") as fh:
        for al in sorted(alerts, key=lambda x: -x["score"]):
            fh.write(json.dumps(al, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-detail", type=int, default=40,
                    help="cap detail fetches per poll (politeness)")
    ap.add_argument("--threshold", type=int, default=2, help="min score to alert")
    ap.add_argument("--pages", type=int, default=3,
                    help="páginas del listado por poll (100 filas c/u); >1 "
                         "evita perder ráfagas de publicación entre polls")
    ap.add_argument("--no-headless", action="store_true")
    args = ap.parse_args()

    now = datetime.now(timezone.utc).isoformat()
    seen = prune_seen(load_seen(), now)
    efos = EfosIndex()
    sfp = SfpIndex()
    dof = DofIndex()

    with ComprasMXClient(headless=not args.no_headless) as client:
        try:
            alerts, stats = poll_once(client, efos, sfp, seen, now, dof=dof,
                                      max_detail=args.max_detail,
                                      threshold=args.threshold,
                                      pages=args.pages)
        finally:
            save_seen(seen)  # keep whatever progress was made

    write_alerts(alerts)
    if alerts:
        packets = write_packets(alerts)
        print(f"  verification packets: {len(packets)} -> findings/packets/")
        CaseStore().ingest_alerts(alerts)
    print(f"[{now}] fetched={stats['fetched']} new={stats['new']} "
          f"changed={stats['changed']} alerts={len(alerts)} "
          f"errors={stats['errors']} detail_fetches={stats['detail_used']}")
    for al in sorted(alerts, key=lambda x: -x["score"])[:10]:
        print(f"  score {al['score']:>2} | {al['dependencia']:<10} | {al['numero']}")
        for r in al["reasons"]:
            print(f"            - {r}")


if __name__ == "__main__":
    main()
