"""Shared loading layer for all detectors.

Creates DuckDB views over the raw government CSVs:
  contracts — ComprasMX yearly files (2023+), normalized dates/amounts/RFC
  efos      — SAT Art. 69-B list, one row per RFC with stage dates
"""
import hashlib
import os
import sys
from datetime import date
from pathlib import Path

from shared.esquemas import EFOS_COLS  # noqa: F401  (re-export)
from shared.fechas import parse_fecha  # noqa: F401  (re-export de compatibilidad)
from shared.normalizacion import (LEGAL_SUFFIXES, normalize,  # noqa: F401
                                  sql_name_norm)
from shared.ramos import RAMO_ESTADO

# Filtro estándar de moneda para sumas en MXN (las fuentes dejan NULL cuando
# es MXN implícito). Único punto de verdad para todos los detectores.
MXN_OK = "(moneda_efectiva = 'MXN' OR moneda_efectiva IS NULL)"

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
# MX_WORK_DIR: los tests redirigen la caché de transcodificación a un tmp
WORK = Path(os.environ.get("MX_WORK_DIR") or ROOT / "data" / "work")
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



def utf8_copy(path: Path) -> str:
    """Transcode a government CSV (cp1252/latin-1 in practice) to UTF-8 once.
    The cache key includes the full source path — two files sharing a name
    (e.g. a test fixture vs data/raw) must never share a cache entry."""
    WORK.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:10]
    out = WORK / f"{key}_{path.stem}.utf8.csv"
    if not out.exists() or out.stat().st_mtime < path.stat().st_mtime:
        with open(path, encoding="cp1252", errors="replace") as src, \
             open(out, "w", encoding="utf-8", newline="") as dst:
            for chunk in iter(lambda: src.read(1 << 20), ""):
                dst.write(chunk)
    return str(out)


# Comprador estatal/municipal (GEM): el ramo 60-91 identifica la entidad
# federativa; los ramos federales caen en NULL.
ESTADO_COMPRADOR_SQL = ("CASE TRY_CAST(clave_ramo AS INT) " + " ".join(
    f"WHEN {clave} THEN '{estado}'" for clave, estado in RAMO_ESTADO.items())
    + " END")


def constitucion_rfc_sql(rfc_expr: str, century_cutoff: int) -> str:
    """SQL para la fecha de constitución de una persona moral derivada de su
    RFC (posiciones 4-9 = AAMMDD). Único lugar con esta lógica — lo usan la
    vista federal `contracts` y la estatal `contracts_pnt`."""
    return (f"CASE WHEN length({rfc_expr}) = 12 THEN TRY_STRPTIME("
            f"CASE WHEN TRY_CAST(substr({rfc_expr}, 4, 2) AS INT) "
            f"<= {century_cutoff} THEN '20' ELSE '19' END "
            f"|| substr({rfc_expr}, 4, 6), '%Y%m%d') END")


def csv_reader(files: list, cols: list[str], skip: int) -> str:
    names = ", ".join(f"'{c}'" for c in cols)
    flist = ", ".join(f"'{f}'" for f in files)
    return f"""read_csv([{flist}], header=false, skip={skip}, names=[{names}],
                all_varchar=true, strict_mode=false,
                null_padding=true, parallel=false, filename=true)"""


def load_views(con, contract_args: list | None = None,
               efos_path=None, today: date | None = None) -> list[str]:
    """Create `contracts` and `efos` views. contract_args: optional file list.
    today: clock override for the RFC century cutoff (tests).
    CONTRATO: termina el proceso (sys.exit) si no hay CSVs de contratos —
    los detectores son scripts y ese es su modo de fallo deliberado."""
    OUT.mkdir(exist_ok=True)
    files = [utf8_copy(Path(p)) for p in (contract_args or sorted(RAW.glob("contratos_*.csv")))]
    if not files:
        sys.exit("no contracts CSVs found in data/raw/")
    efos_file = utf8_copy(Path(efos_path) if efos_path else RAW / "sat_69b_completo.csv")
    # Two-digit RFC year: 20xx if not in the future, else 19xx.
    century_cutoff = (today or date.today()).year % 100

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
      CASE WHEN TRY_CAST(replace(importe_drc, ',', '') AS DOUBLE) IS NOT NULL
           THEN moneda_drc ELSE moneda END AS moneda_efectiva,
      {ESTADO_COMPRADOR_SQL} AS estado_comprador,
      upper(trim(rfc)) AS rfc_norm,
      length(trim(rfc)) = 12 AS es_persona_moral,
      {constitucion_rfc_sql('trim(rfc)', century_cutoff)} AS fecha_constitucion_rfc
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


SFP_COLS = ["rfc", "nombre", "multa", "institucion_sancionadora",
            "inicio", "fin", "plazo_txt"]


def load_sfp_views(con, sfp_path=None) -> None:
    """Create `sfp` (ALL debarment windows — a supplier can be debarred more
    than once) and `sfp_hits` (one row per contract to an ever-debarred
    supplier, showing the window that contains the contract date if any,
    else the most recent). Requires load_views() to have run first."""
    import json

    import pandas as pd

    path = Path(sfp_path) if sfp_path else RAW / "sfp_sancionados.json"
    if not path.exists():
        sys.exit(f"missing {path} — run scripts/fetch_sfp.py")
    rows = []
    for r in json.loads(path.read_text()):
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
    con.register("sfp_raw", pd.DataFrame(rows, columns=SFP_COLS))

    con.execute("""
    CREATE VIEW sfp AS
    SELECT rfc AS rfc_norm, nombre, multa, institucion_sancionadora, plazo_txt,
           TRY_CAST(inicio AS DATE) AS inicio, TRY_CAST(fin AS DATE) AS fin
    FROM sfp_raw WHERE length(rfc) >= 12
    """)

    con.execute("""
    CREATE VIEW sfp_hits AS
    SELECT * EXCLUDE (_cid, _rn) FROM (
      SELECT c.*, s.nombre AS nombre_sfp, s.multa, s.institucion_sancionadora,
        s.inicio, s.fin, s.plazo_txt,
        -- sin `fin` no hay ventana de inhabilitación (p. ej. solo multa):
        -- jamás cuenta como durante.
        c.fecha_efectiva IS NOT NULL AND s.inicio IS NOT NULL
          AND c.fecha_efectiva >= s.inicio
          AND s.fin IS NOT NULL AND c.fecha_efectiva <= s.fin AS durante_inhabilitacion,
        row_number() OVER (
          PARTITION BY c._cid
          ORDER BY (c.fecha_efectiva IS NOT NULL AND s.inicio IS NOT NULL
                    AND c.fecha_efectiva >= s.inicio
                    AND s.fin IS NOT NULL AND c.fecha_efectiva <= s.fin) DESC,
                   s.inicio DESC NULLS LAST) AS _rn
      FROM (SELECT *, row_number() OVER () AS _cid FROM contracts) c
      JOIN sfp s USING (rfc_norm)
    ) WHERE _rn = 1
    """)
