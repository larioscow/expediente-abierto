#!/usr/bin/env python
"""Refresh the SFP debarred-supplier directory (RFC + name + debarment period).

The directoriosancionados portal is an SPA whose API serves 0 bytes to plain
HTTP; we capture its own signed XHR via scrapling (same technique as ComprasMX).
Saves data/raw/sfp_sancionados.json and appends provenance to MANIFEST.tsv.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from scrapling.fetchers import DynamicSession

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "sfp_sancionados.json"
MANIFEST = ROOT / "data" / "raw" / "MANIFEST.tsv"
PORTAL = "https://directoriosancionados.buengobierno.gob.mx/"


def _trigger_search(page):
    page.wait_for_timeout(3000)
    for sel in ["button:has-text('Buscar')", "button:has-text('Consultar')",
                "button[type=submit]"]:
        try:
            page.click(sel, timeout=2000)
            page.wait_for_timeout(4000)
            break
        except Exception:
            continue
    return page


def fetch() -> list[dict]:
    best = None
    with DynamicSession(headless=True, network_idle=True,
                        capture_xhr=r"particularesSancionadosPro") as s:
        page = s.fetch(PORTAL, load_dom=True, wait=6000, page_action=_trigger_search)
        for x in getattr(page, "captured_xhr", []) or []:
            try:
                res = json.loads(x.body).get("data", {}).get("results")
            except Exception:
                continue
            if res and (best is None or len(res) > len(best)):
                best = res
    return best or []


def main():
    records = fetch()
    if not records:
        raise SystemExit("SFP: captured no records")
    payload = json.dumps(records, ensure_ascii=False)
    OUT.write_text(payload, encoding="utf-8")
    sha = hashlib.sha256(payload.encode()).hexdigest()
    ts = datetime.now(timezone.utc).isoformat()
    with open(MANIFEST, "a") as fh:
        fh.write(f"{ts}\t{sha}\t{len(payload)}\tsfp_sancionados.json\t{PORTAL} (API capture)\n")
    print(f"SFP: saved {len(records)} sanctioned suppliers")


if __name__ == "__main__":
    main()
