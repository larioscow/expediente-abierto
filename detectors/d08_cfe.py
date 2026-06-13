#!/usr/bin/env python
"""Detector 08 — CFE awarded contracts crossed against 69-B and SFP.

CFE (like Pemex) is OUTSIDE ComprasMX — its own procurement regime. This
ingests CFE's official open dataset of awarded contracts (datos.gob.mx →
repodatos.atdt.gob.mx, fetched by scripts/download_data.sh with provenance)
and screens every awarded supplier against the 69-B and SFP lists.

The dataset exposes supplier NAME only (no RFC), so every hit is a
name-based SCREEN requiring verification — same status as the realtime tier.
Coverage note: the published file is a fraction of CFE's real volume; the
full history lives behind msc.cfe.mx (future work, documented in README).

Usage: python detectors/d08_cfe.py [cfe_contratos.csv]
"""
import csv
import sys
from pathlib import Path

import pandas as pd

from detectors.common import OUT, RAW, parse_fecha  # noqa: F401  (re-export)
from realtime.efos_index import EfosIndex
from realtime.sfp_index import SfpIndex

CFE_CSV = RAW / "cfe_contratos_adjudicados.csv"


def cfe_risk(cfe_csv, efos: EfosIndex, sfp: SfpIndex) -> pd.DataFrame:
    rows = []
    with open(cfe_csv, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            prov = (r.get("nomb_proveedor_adjudicado") or "").strip()
            if not prov:
                continue
            when = parse_fecha(r.get("fecha_fallo")) or parse_fecha(r.get("fecha_publicacion"))
            base = {
                "numero": r.get("numero"), "proveedor": prov,
                "tipo_procedimiento": r.get("tipo_procedimiento"),
                "monto": r.get("monto"), "fecha": str(when or ""),
                "area_contratante": r.get("area_contratante"),
                "needs_verification": True, "match_method": "name",
            }
            hit = efos.match_name(prov)
            if hit:
                rows.append({**base, "lista": "69-B", "rfc": hit["rfc"],
                             "detalle": hit["situacion"],
                             "durante_inhabilitacion": None})
            s, durante = SfpIndex.pick(sfp.match_name(prov), when)
            if s:
                rows.append({**base, "lista": "SFP", "rfc": s["rfc"],
                             "detalle": f"inhabilitada {s.get('inicio')} → {s.get('fin')}",
                             "durante_inhabilitacion": durante})
    cols = ["numero", "proveedor", "lista", "rfc", "detalle",
            "durante_inhabilitacion", "tipo_procedimiento", "monto", "fecha",
            "area_contratante", "match_method", "needs_verification"]
    return pd.DataFrame(rows, columns=cols)


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else CFE_CSV
    if not src.exists():
        sys.exit(f"missing {src} — run scripts/download_data.sh")
    df = cfe_risk(src, EfosIndex(), SfpIndex())
    df.to_csv(OUT / "f09_cfe_riesgo.csv", index=False)
    total = sum(1 for _ in open(src, encoding="utf-8")) - 1
    print(f"== CFE: {total} contratos publicados; coincidencias 69-B/SFP "
          f"(por nombre, verificar): {len(df)} ==")
    if len(df):
        print(df.drop(columns=["match_method", "needs_verification"])
                .to_string(index=False, max_colwidth=44))


if __name__ == "__main__":
    main()
