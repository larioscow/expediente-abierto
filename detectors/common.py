"""Shared loading layer for all detectors.

Creates DuckDB views over the raw government CSVs:
  contracts — ComprasMX yearly files (2023+), normalized dates/amounts/RFC
  efos      — SAT Art. 69-B list, one row per RFC with stage dates
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
WORK = ROOT / "data" / "work"
OUT = ROOT / "findings"

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


def utf8_copy(path: Path) -> str:
    """Transcode a government CSV (cp1252/latin-1 in practice) to UTF-8 once."""
    WORK.mkdir(exist_ok=True)
    out = WORK / (path.stem + ".utf8.csv")
    if not out.exists() or out.stat().st_mtime < path.stat().st_mtime:
        with open(path, encoding="cp1252", errors="replace") as src, \
             open(out, "w", encoding="utf-8", newline="") as dst:
            for chunk in iter(lambda: src.read(1 << 20), ""):
                dst.write(chunk)
    return str(out)


def csv_reader(files, cols, skip):
    names = ", ".join(f"'{c}'" for c in cols)
    flist = ", ".join(f"'{f}'" for f in files)
    return f"""read_csv([{flist}], header=false, skip={skip}, names=[{names}],
                all_varchar=true, strict_mode=false,
                null_padding=true, parallel=false, filename=true)"""


def load_views(con, contract_args=None):
    """Create `contracts` and `efos` views. contract_args: optional file list."""
    OUT.mkdir(exist_ok=True)
    files = [utf8_copy(Path(p)) for p in (contract_args or sorted(RAW.glob("contratos_*.csv")))]
    if not files:
        sys.exit("no contracts CSVs found in data/raw/")
    efos_file = utf8_copy(RAW / "sat_69b_completo.csv")

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
      CASE WHEN TRY_CAST(replace(importe_drc, ',', '') AS DOUBLE) IS NOT NULL
           THEN 'ejercido' ELSE 'techo_maximo' END AS tipo_monto,
      upper(trim(rfc)) AS rfc_norm,
      length(trim(rfc)) = 12 AS es_persona_moral,
      CASE WHEN length(trim(rfc)) = 12 THEN
        TRY_STRPTIME(
          CASE WHEN TRY_CAST(substr(trim(rfc), 4, 2) AS INT) <= 26
               THEN '20' ELSE '19' END || substr(trim(rfc), 4, 6), '%Y%m%d')
      END AS fecha_constitucion_rfc
    FROM {csv_reader(files, CONTRACT_COLS, 1)}
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
    return files
