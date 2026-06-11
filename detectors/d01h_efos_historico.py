#!/usr/bin/env python
"""Detector 01h — historical CompraNet (2010–2023) × SAT 69-B, by normalized name.

The consolidated historical archive publishes no supplier RFC, so this tier
matches on strictly normalized company names (uppercase, accent-stripped,
punctuation removed, legal-form suffixes dropped). Every output row is labeled
match_method=name_match and requires manual verification before publication —
homonyms are possible, unlike the RFC tier (d01).

Key question this tier CAN answer that 2023+ cannot: were contracts started
AFTER the supplier was already published as a definitive shell (the smoking gun)?

Usage: python detectors/d01h_efos_historico.py
"""
import duckdb

from common import OUT, RAW, csv_reader, utf8_copy, EFOS_COLS

con = duckdb.connect()

NORM = """upper(strip_accents({c}))"""
CLEAN = (
    "trim(regexp_replace(regexp_replace(regexp_replace({n}, "
    "'[^A-Z0-9 ]', ' ', 'g'), "
    "' (SA DE CV|S DE RL DE CV|SAPI DE CV|S A P I DE C V|SA DE C V|S A DE C V|SC|S C|AC|A C|SAB DE CV|SAS|S A S|SRL|S DE RL)$', '', 'g'), "
    "' +', ' ', 'g'))"
)

def name_norm(col):
    return CLEAN.format(n=NORM.format(c=col))

con.execute(f"""
CREATE VIEW hist AS
SELECT *,
  TRY_CAST(importe AS DOUBLE) AS importe_num,
  COALESCE(TRY_CAST(ff_fecha_inicio AS DATE), TRY_CAST(substr(fecha_inicio, 1, 10) AS DATE)) AS fecha,
  {name_norm('proveedor')} AS nombre_norm
FROM read_csv('data/raw/compranet_historico.csv', header=true, all_varchar=true, strict_mode=false)
QUALIFY row_number() OVER (PARTITION BY codigo_contrato ORDER BY TRY_CAST(importe AS DOUBLE) DESC NULLS LAST) = 1
""")

efos_file = utf8_copy(RAW / "sat_69b_completo.csv")
con.execute(f"""
CREATE VIEW efos_n AS
SELECT {name_norm('nombre')} AS nombre_norm, nombre, rfc, situacion,
  COALESCE(TRY_STRPTIME(pub_dof_definitivos, '%d/%m/%Y'), TRY_STRPTIME(pub_sat_definitivos, '%d/%m/%Y')) AS fecha_definitivo
FROM {csv_reader([efos_file], EFOS_COLS, 3)}
WHERE rfc IS NOT NULL AND length(trim(rfc)) >= 12
QUALIFY row_number() OVER (PARTITION BY nombre_norm ORDER BY fecha_definitivo DESC NULLS LAST) = 1
""")

con.execute("""
CREATE VIEW hits AS
SELECT h.*, e.situacion, e.fecha_definitivo, e.rfc AS rfc_69b, e.nombre AS nombre_69b,
  h.fecha IS NOT NULL AND e.fecha_definitivo IS NOT NULL AND h.fecha > e.fecha_definitivo AS iniciado_despues_definitivo
FROM hist h JOIN efos_n e USING (nombre_norm)
WHERE length(h.nombre_norm) >= 8
""")

def q(sql):
    return con.execute(sql).fetchdf()

print("== universo histórico ==")
print(q("SELECT count(*) AS contratos, min(fecha) AS desde, max(fecha) AS hasta, round(sum(importe_num) FILTER (moneda='MXN')/1e9,1) AS total_mxn_mmd FROM hist").to_string(index=False))

resumen = q("""
SELECT situacion, count(*) AS contratos, count(DISTINCT nombre_norm) AS empresas,
  round(sum(importe_num) FILTER (moneda = 'MXN') / 1e6, 1) AS monto_mxn_millones
FROM hits GROUP BY 1 ORDER BY 4 DESC NULLS LAST""")
print("\n== contratos históricos a empresas 69-B (match por nombre) ==\n", resumen.to_string(index=False))
resumen.to_csv(OUT / "f01h_resumen_por_situacion.csv", index=False)

gun = q("""
SELECT year(fecha) AS anio, count(*) AS contratos, count(DISTINCT nombre_norm) AS empresas,
  round(sum(importe_num) FILTER (moneda = 'MXN') / 1e6, 1) AS monto_mxn_millones
FROM hits WHERE situacion = 'Definitivo' AND iniciado_despues_definitivo
GROUP BY 1 ORDER BY 1""")
print("\n== SMOKING GUN: contratos INICIADOS DESPUÉS de publicación definitiva (por nombre) ==\n", gun.to_string(index=False))
gun.to_csv(OUT / "f01h_despues_de_definitivo_por_anio.csv", index=False)

top_gun = q("""
SELECT proveedor, rfc_69b, strftime(fecha_definitivo, '%Y-%m-%d') AS definitivo_dof,
  strftime(fecha, '%Y-%m-%d') AS inicio_contrato, titulo_contrato,
  round(importe_num / 1e6, 2) AS monto_mxn_millones, codigo_contrato
FROM hits WHERE situacion = 'Definitivo' AND iniciado_despues_definitivo AND moneda = 'MXN'
ORDER BY importe_num DESC LIMIT 25""")
print("\n== top 25 post-definitivo (MXN, verificar manualmente) ==\n",
      top_gun.to_string(index=False, max_colwidth=38))
top_gun.to_csv(OUT / "f01h_top25_post_definitivo.csv", index=False)

todo = q("""
SELECT 'name_match' AS match_method, proveedor, nombre_69b, rfc_69b, situacion,
  strftime(fecha_definitivo, '%Y-%m-%d') AS definitivo_dof,
  strftime(fecha, '%Y-%m-%d') AS inicio_contrato, iniciado_despues_definitivo,
  titulo_contrato, descripcion_contrato, importe_num, moneda, codigo_contrato, codigo_expediente
FROM hits WHERE situacion IN ('Definitivo','Presunto')
ORDER BY iniciado_despues_definitivo DESC, importe_num DESC NULLS LAST""")
todo.to_csv(OUT / "f01h_detalle_completo.csv", index=False)
print(f"\nwrote {len(todo)} detail rows -> findings/f01h_detalle_completo.csv")
