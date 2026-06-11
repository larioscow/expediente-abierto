#!/usr/bin/env python
"""Detector 05 — federal contracts to SFP-debarred suppliers (exact RFC join).

Headline signal: a contract whose effective date falls INSIDE the supplier's
debarment window — i.e. awarded while the company was legally barred from
receiving government contracts. Also reports all-time contracts to ever-debarred
suppliers as context.

Usage: python detectors/d05_sfp_sancionados.py [contracts.csv ...]
"""
import json
import sys
from pathlib import Path

import duckdb

from common import OUT, RAW, load_views

con = duckdb.connect()
load_views(con, sys.argv[1:] or None)

sfp_path = RAW / "sfp_sancionados.json"
if not sfp_path.exists():
    sys.exit("missing data/raw/sfp_sancionados.json — run scripts/fetch_sfp.py")

records = json.loads(sfp_path.read_text())
rows = []
for r in records:
    plazo = r.get("plazo") or {}
    rows.append({
        "rfc": (r.get("rfc") or "").strip().upper(),
        "nombre": (r.get("nombre_razon_social") or "").strip(),
        "multa": r.get("multa"),
        "institucion_sancionadora": r.get("institucion_dependencia"),
        "inicio": (plazo.get("fecha_inicial") or "")[:10],
        "fin": (plazo.get("fecha_final") or plazo.get("fecha_fin") or "")[:10],
        "plazo_txt": plazo.get("plazo_inha"),
    })
con.register("sfp_raw", __import__("pandas").DataFrame(rows))

con.execute("""
CREATE VIEW sfp AS
SELECT rfc AS rfc_norm, nombre, multa, institucion_sancionadora, plazo_txt,
       TRY_CAST(inicio AS DATE) AS inicio, TRY_CAST(fin AS DATE) AS fin
FROM sfp_raw WHERE length(rfc) >= 12
QUALIFY row_number() OVER (PARTITION BY rfc ORDER BY TRY_CAST(inicio AS DATE) DESC NULLS LAST) = 1
""")

con.execute("""
CREATE VIEW hits AS
SELECT c.*, s.nombre AS nombre_sfp, s.multa, s.institucion_sancionadora,
       s.inicio, s.fin, s.plazo_txt,
       c.fecha_efectiva IS NOT NULL AND s.inicio IS NOT NULL
         AND c.fecha_efectiva >= s.inicio
         AND (s.fin IS NULL OR c.fecha_efectiva <= s.fin) AS durante_inhabilitacion
FROM contracts c JOIN sfp s USING (rfc_norm)
""")

def q(sql):
    return con.execute(sql).fetchdf()

print("== SFP universo ==")
print(q("SELECT count(*) sancionados, count(*) FILTER (fin IS NULL OR fin >= current_date) AS vigentes_aprox FROM sfp").to_string(index=False))

resumen = q("""
SELECT file_year, count(*) AS contratos, count(DISTINCT rfc_norm) AS empresas,
  round(sum(importe) FILTER (moneda_drc='MXN' OR moneda_drc IS NULL)/1e6, 1) AS monto_mxn_millones
FROM hits GROUP BY 1 ORDER BY 1""")
print("\n== contratos a proveedores sancionados por la SFP (cruce por RFC) ==\n", resumen.to_string(index=False))
resumen.to_csv(OUT / "f05_resumen.csv", index=False)

gun = q("""
SELECT proveedor, rfc_norm AS rfc,
  strftime(inicio,'%Y-%m-%d') AS inhabilitado_desde, strftime(fin,'%Y-%m-%d') AS hasta,
  strftime(fecha_efectiva,'%Y-%m-%d') AS fecha_contrato,
  institucion, tipo_procedimiento,
  round(importe/1e6,2) AS monto_mxn_millones, direccion_anuncio
FROM hits WHERE durante_inhabilitacion AND (moneda_drc='MXN' OR moneda_drc IS NULL)
ORDER BY importe DESC NULLS LAST""")
print(f"\n== SMOKING GUN: contratos firmados DURANTE la inhabilitación: {len(gun)} ==")
print(gun.drop(columns=["direccion_anuncio"]).head(20).to_string(index=False, max_colwidth=40))
gun.to_csv(OUT / "f05_durante_inhabilitacion.csv", index=False)

detalle = q("""
SELECT file_year, codigo_contrato, proveedor, rfc_norm AS rfc, nombre_sfp,
  strftime(inicio,'%Y-%m-%d') AS inhab_desde, strftime(fin,'%Y-%m-%d') AS inhab_hasta,
  strftime(fecha_efectiva,'%Y-%m-%d') AS fecha_contrato, durante_inhabilitacion,
  institucion, tipo_procedimiento, importe, moneda_drc, multa,
  institucion_sancionadora, direccion_anuncio
FROM hits ORDER BY durante_inhabilitacion DESC, importe DESC NULLS LAST""")
detalle.to_csv(OUT / "f05_detalle_completo.csv", index=False)
print(f"\nwrote {len(detalle)} detail rows -> findings/f05_detalle_completo.csv")
