#!/usr/bin/env python
"""Detector 01 — federal contracts awarded to SAT 69-B (EFOS) companies.

Joins ComprasMX contract data with the SAT Art. 69-B list on supplier RFC.
Headline = suppliers with status "Definitivo" (confirmed invoice mills).
Companies cleared by court or by rebuttal (Sentencia Favorable / Desvirtuado)
are explicitly excluded from the headline and reported only as context.

Outputs CSV tables under findings/ and prints a summary.
Usage: python detectors/d01_efos_contracts.py [contracts.csv ...]
"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "findings"
OUT.mkdir(exist_ok=True)

WORK = ROOT / "data" / "work"
WORK.mkdir(exist_ok=True)


def utf8_copy(path: Path) -> str:
    """Transcode a government CSV (cp1252/latin-1 in practice) to UTF-8 once."""
    out = WORK / (path.stem + ".utf8.csv")
    if not out.exists() or out.stat().st_mtime < path.stat().st_mtime:
        with open(path, encoding="cp1252", errors="replace") as src, \
             open(out, "w", encoding="utf-8", newline="") as dst:
            for chunk in iter(lambda: src.read(1 << 20), ""):
                dst.write(chunk)
    return str(out)


contract_files = [utf8_copy(Path(p)) for p in (sys.argv[1:] or sorted(RAW.glob("contratos_*.csv")))]
if not contract_files:
    sys.exit("no contracts CSVs found in data/raw/")
efos_file = utf8_copy(RAW / "sat_69b_completo.csv")

CONTRACT_COLS = [
    "orden_gobierno", "clave_ramo", "ramo", "tipo_institucion", "clave_institucion",
    "siglas_institucion", "institucion", "clave_uc", "nombre_uc", "codigo_expediente",
    "referencia_expediente", "titulo_expediente", "partida_especifica", "ley",
    "tipo_procedimiento", "articulo_excepcion", "descripcion_excepcion", "contrato_marco",
    "compra_consolidada", "num_proc_consolidacion", "nombre_proc_consolidacion",
    "tipo_proc_consolidacion", "art_exc_proc_consolidacion", "numero_procedimiento",
    "tipo_contratacion", "caracter_procedimiento", "forma_participacion",
    "caso_fortuito", "credito_externo", "organismo_financiero", "clave_programa_federal",
    "clave_cartera_shcp", "fecha_publicacion", "fecha_apertura", "fecha_fallo",
    "codigo_contrato", "num_contrato", "titulo_contrato", "descripcion_contrato",
    "contrato_plurianual", "estatus_drc", "fecha_inicio_contrato", "fecha_fin_contrato",
    "fecha_firma_contrato", "importe_drc", "moneda_drc", "convenio_modificatorio_drc",
    "codigo_ref_contrato", "estatus_contrato", "fecha_firma2", "tipo_contrato",
    "monto_sin_imp_min", "monto_min_con_imp", "monto_sin_imp_max", "monto_max_con_imp",
    "moneda", "convenio_modificatorio", "codigo_ref_ultimo_conv", "fecha_fin_ultimo_conv",
    "monto_sin_imp_min_uc", "monto_min_con_imp_uc", "monto_sin_imp_max_uc",
    "monto_max_con_imp_uc", "fecha_firma_ultimo_conv", "rfc", "proveedor",
    "folio_rupc", "pais_empresa", "nacionalidad_proveedor", "auto_registro",
    "estratificacion", "origen", "direccion_anuncio",
]

EFOS_COLS = [
    "no", "rfc", "nombre", "situacion",
    "oficio_presuncion_sat", "pub_sat_presuntos", "oficio_presuncion_dof", "pub_dof_presuntos",
    "oficio_desvirtuaron_sat", "pub_sat_desvirtuados", "oficio_desvirtuaron_dof", "pub_dof_desvirtuados",
    "oficio_definitivos_sat", "pub_sat_definitivos", "oficio_definitivos_dof", "pub_dof_definitivos",
    "oficio_sentencia_sat", "pub_sat_sentencia", "oficio_sentencia_dof", "pub_dof_sentencia",
]

con = duckdb.connect()

def csv_reader(files, cols, skip):
    names = ", ".join(f"'{c}'" for c in cols)
    flist = ", ".join(f"'{f}'" for f in files)
    return f"""read_csv([{flist}], header=false, skip={skip}, names=[{names}],
                all_varchar=true, strict_mode=false,
                null_padding=true, parallel=false, filename=true)"""

con.execute(f"""
CREATE VIEW contracts AS
SELECT *,
  regexp_extract(filename, '(\\d{{4}})\\.utf8\\.csv$', 1) AS file_year,
  COALESCE(TRY_STRPTIME(fecha_firma_contrato, '%d/%m/%Y'), TRY_STRPTIME(fecha_firma_contrato, '%Y-%m-%d'),
           TRY_STRPTIME(fecha_firma2,         '%d/%m/%Y'), TRY_STRPTIME(fecha_firma2,         '%Y-%m-%d'),
           TRY_STRPTIME(fecha_inicio_contrato,'%d/%m/%Y'), TRY_STRPTIME(fecha_inicio_contrato,'%Y-%m-%d'),
           TRY_STRPTIME(fecha_fallo,          '%d/%m/%Y'), TRY_STRPTIME(fecha_fallo,          '%Y-%m-%d')
  ) AS fecha_efectiva,
  COALESCE(TRY_CAST(replace(importe_drc, ',', '') AS DOUBLE),
           TRY_CAST(replace(monto_max_con_imp, ',', '') AS DOUBLE),
           TRY_CAST(replace(monto_max_con_imp_uc, ',', '') AS DOUBLE)) AS importe,
  upper(trim(rfc)) AS rfc_norm
FROM {csv_reader(contract_files, CONTRACT_COLS, 1)}
""")

con.execute(f"""
CREATE VIEW efos AS
SELECT upper(trim(rfc)) AS rfc_norm, nombre, situacion,
  COALESCE(TRY_STRPTIME(pub_dof_definitivos, '%d/%m/%Y'), TRY_STRPTIME(pub_sat_definitivos, '%d/%m/%Y')) AS fecha_definitivo,
  COALESCE(TRY_STRPTIME(pub_dof_presuntos,  '%d/%m/%Y'), TRY_STRPTIME(pub_sat_presuntos,  '%d/%m/%Y')) AS fecha_presunto
FROM {csv_reader([efos_file], EFOS_COLS, 3)}
WHERE rfc IS NOT NULL AND length(trim(rfc)) >= 12
QUALIFY row_number() OVER (PARTITION BY upper(trim(rfc)) ORDER BY fecha_definitivo DESC NULLS LAST) = 1
""")

con.execute("""
CREATE VIEW hits AS
SELECT c.*, e.situacion, e.fecha_definitivo, e.fecha_presunto, e.nombre AS nombre_69b,
  c.fecha_efectiva IS NOT NULL AND e.fecha_definitivo IS NOT NULL
    AND c.fecha_efectiva > e.fecha_definitivo AS firmado_despues_definitivo
FROM contracts c JOIN efos e USING (rfc_norm)
""")

def q(sql):
    return con.execute(sql).fetchdf()

sanity = q("""
SELECT file_year, count(*) AS contratos, count(rfc_norm) AS con_rfc,
       count(fecha_efectiva) AS con_fecha, count(importe) AS con_importe
FROM contracts GROUP BY 1 ORDER BY 1""")
print("== sanity ==\n", sanity.to_string(index=False))

resumen = q("""
SELECT situacion, file_year,
       count(*) AS contratos,
       count(DISTINCT rfc_norm) AS empresas,
       round(sum(importe) FILTER (moneda_drc = 'MXN' OR moneda_drc IS NULL) / 1e6, 1) AS monto_mxn_millones
FROM hits GROUP BY 1, 2 ORDER BY 1, 2""")
print("\n== contratos a empresas 69-B por situación ==\n", resumen.to_string(index=False))
resumen.to_csv(OUT / "f01_resumen_por_situacion.csv", index=False)

despues = q("""
SELECT file_year, count(*) AS contratos, count(DISTINCT rfc_norm) AS empresas,
       round(sum(importe) FILTER (moneda_drc = 'MXN' OR moneda_drc IS NULL) / 1e6, 1) AS monto_mxn_millones
FROM hits WHERE situacion = 'Definitivo' AND firmado_despues_definitivo
GROUP BY 1 ORDER BY 1""")
print("\n== DEFINITIVO: contratos firmados DESPUÉS de publicación DOF como definitivo ==\n", despues.to_string(index=False))
despues.to_csv(OUT / "f01_despues_de_definitivo.csv", index=False)

top = q("""
SELECT proveedor, rfc_norm AS rfc, situacion,
       strftime(fecha_definitivo, '%Y-%m-%d') AS definitivo_dof,
       strftime(fecha_efectiva, '%Y-%m-%d') AS fecha_contrato,
       firmado_despues_definitivo AS post_definitivo,
       institucion, tipo_procedimiento, round(importe / 1e6, 2) AS monto_mxn_millones, moneda_drc
FROM hits WHERE situacion = 'Definitivo' AND importe IS NOT NULL AND (moneda_drc = 'MXN' OR moneda_drc IS NULL)
ORDER BY importe DESC LIMIT 25""")
print("\n== top 25 contratos a Definitivos (MXN) ==\n", top.to_string(index=False, max_colwidth=42))
top.to_csv(OUT / "f01_top25_definitivos.csv", index=False)

por_proc = q("""
SELECT tipo_procedimiento, count(*) AS contratos,
       round(sum(importe) FILTER (moneda_drc = 'MXN' OR moneda_drc IS NULL) / 1e6, 1) AS monto_mxn_millones
FROM hits WHERE situacion = 'Definitivo'
GROUP BY 1 ORDER BY 2 DESC""")
print("\n== Definitivos por tipo de procedimiento ==\n", por_proc.to_string(index=False, max_colwidth=60))
por_proc.to_csv(OUT / "f01_definitivos_por_procedimiento.csv", index=False)

detalle = q("""
SELECT file_year, codigo_contrato, num_contrato, titulo_contrato, proveedor, rfc_norm AS rfc,
       situacion, strftime(fecha_definitivo, '%Y-%m-%d') AS definitivo_dof,
       strftime(fecha_efectiva, '%Y-%m-%d') AS fecha_contrato, firmado_despues_definitivo,
       institucion, nombre_uc, tipo_procedimiento, importe, moneda_drc, direccion_anuncio
FROM hits WHERE situacion IN ('Definitivo', 'Presunto')
ORDER BY situacion, importe DESC NULLS LAST""")
detalle.to_csv(OUT / "f01_detalle_completo.csv", index=False)
print(f"\nwrote {len(detalle)} detail rows -> findings/f01_detalle_completo.csv")
