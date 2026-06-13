"""Capa de carga de los contratos estatales de la PNT (fr. XXVIII).

Crea la vista `contracts_pnt` sobre los CSV de data/raw/pnt/ con el mismo
vocabulario que `contracts` (proveedor, rfc_norm, fecha_efectiva, importe,
estado_comprador, direccion_anuncio). Las columnas se resuelven POR ARCHIVO
buscando el encabezado por fragmentos: los formatos varían entre órganos
garantes (80-82 columnas nativas) y jamás se asumen posiciones.

El dedupe es obligatorio: los sujetos obligados re-reportan el mismo
contrato por trimestre y algunos estados publican dos formatos casi
idénticos (en Sonora ~95% de traslape); gana la fecha de actualización
más reciente dentro de cada llave natural.
"""
import csv
import hashlib
import re
import sys
from datetime import date
from pathlib import Path

from detectors.common import RAW, WORK, constitucion_rfc_sql

PNT_DIR = RAW / "pnt"

# algunos sujetos suben filas con campos enormes; subimos el tope del módulo
csv.field_size_limit(16_000_000)

# RFC con homoclave: el mismo criterio que valida el sondeo de la PNT
RFC_REGEX = "[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}"

# ejercicio plausible: la descarga ya filtra por año, así que un valor fuera
# de rango (vimos "2525", "2014" sueltos) es captura corrupta del sujeto. El
# tope superior se deriva de la fecha (año en curso + 1, para datos del
# próximo ejercicio publicados por adelantado) — nunca un literal que en un
# año futuro rechace datos válidos.
EJERCICIO_MIN = 2015

# Nombre de proveedor utilizable: la PNT mete en ese campo placeholders de
# redacción ("PERSONA FISICA", "DATOS PERSONALES"), el sexo del adjudicado por
# corrimiento de columnas ("HOMBRE"/"MUJER", o un nombre con sufijo " Hombre"),
# URLs y boilerplate de transparencia. Cualquier hallazgo que NOMBRE a un
# proveedor debe filtrarlos: publicar "Hombre concentra el 78%" es basura.
PROVEEDOR_PLAUSIBLE = (
    "proveedor IS NOT NULL AND length(trim(proveedor)) >= 5 "
    "AND upper(trim(proveedor)) NOT IN ("
    "'HOMBRE','MUJER','PERSONA FISICA','PERSONA MORAL','DATOS PERSONALES',"
    "'NO APLICA','N/A','NA','NINGUNO','SIN DATO','SIN DATOS','DESIERTA',"
    "'NO SE CUENTA CON LA INFORMACION') "
    "AND proveedor NOT ILIKE 'http%' "
    "AND proveedor NOT ILIKE 'ley %' "  # títulos de ley en el campo proveedor
    "AND proveedor NOT ILIKE '%PERSONA FISICA%' "
    "AND proveedor NOT ILIKE '%DATOS PERSONALES%' "
    # "transparencia" (con o sin la S, hay typos en la fuente) = boilerplate
    "AND proveedor NOT ILIKE '%TRAN%PARENCIA%' "
    "AND proveedor NOT ILIKE '%NO SE REALIZ%' "
    "AND proveedor NOT ILIKE '% HOMBRE' AND proveedor NOT ILIKE '% MUJER'")

# fragmentos (todos deben aparecer) -> columna lógica; la igualdad exacta
# gana antes que la búsqueda por fragmentos ("Sujeto obligado" vs
# "Id sujeto obligado")
CAMPOS = {
    "estado": ("entidad federativa",),
    "id_entidad": ("id entidad",),
    "id_sujeto": ("id sujeto",),
    "sujeto_obligado": ("sujeto obligado",),
    "ejercicio": ("ejercicio",),
    "tipo_procedimiento": ("tipo de procedimiento",),
    "materia": ("materia o tipo",),
    "caracter": ("carácter del procedimiento",),
    "expediente": ("número de expediente",),
    "descripcion": ("descripción de las obras",),
    "nombre_pf": ("nombre(s) de la persona física",),
    "ap1_pf": ("primer apellido",),
    "ap2_pf": ("segundo apellido",),
    "razon_social": ("denominación o razón social",),
    "rfc": ("registro federal de contribuyentes",),
    "municipio_proveedor": ("nombre del municipio",),
    "cp_proveedor": ("código postal",),
    "num_contrato": ("número que identifique al contrato",),
    "fecha_contrato": ("fecha del contrato expresada",),
    "inicio_vigencia": ("inicio de la vigencia",),
    "monto_sin_imp": ("monto del contrato sin impuestos",),
    "monto_con_imp": ("monto total del contrato con impuestos",),
    "monto_max": ("monto máximo",),
    "moneda": ("tipo de moneda",),
    "objeto": ("objeto del contrato",),
    "url_fallo": ("acta de fallo",),
    "url_contrato": ("documento del contrato",),
    "origen_recursos": ("origen de los recursos",),
    "convenio_modif": ("contratos modificatorios",),
    "fecha_actualizacion": ("fecha de actualización",),
}
# sin estos campos un archivo no es utilizable como evidencia
REQUERIDOS = {"estado", "id_entidad", "id_sujeto", "sujeto_obligado",
              "ejercicio", "rfc", "fecha_actualizacion"}


def sanea(path: Path) -> str:
    """Reescribe el CSV con el módulo csv de Python (tolerante) normalizando
    cada fila al ancho del encabezado: el lector veloz de DuckDB se cae con
    filas malformadas de la PNT (campos gigantes, conteo de columnas roto).
    Cacheado por ruta+mtime en data/work/, igual que utf8_copy."""
    WORK.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:10]
    out = WORK / f"pnt_{key}_{path.stem}.clean.csv"
    if out.exists() and out.stat().st_mtime >= path.stat().st_mtime:
        return str(out)
    with open(path, encoding="utf-8", newline="") as src, \
         open(out, "w", encoding="utf-8", newline="") as dst:
        r = csv.reader(src)
        w = csv.writer(dst)
        try:
            encabezado = next(r)
        except StopIteration:
            return str(out)
        ancho = len(encabezado)
        w.writerow(encabezado)
        for fila in r:
            if len(fila) < ancho:
                fila = fila + [""] * (ancho - len(fila))
            elif len(fila) > ancho:
                # junta el sobrante en la última columna (Nota) sin perderlo
                fila = fila[:ancho - 1] + [" ".join(fila[ancho - 1:])]
            w.writerow(fila)
    return str(out)


def columna(encabezados: list[str], *fragmentos: str) -> str | None:
    """Encabezado exacto primero; si no, el primero que contenga todos los
    fragmentos."""
    objetivo = [f.casefold() for f in fragmentos]
    if len(objetivo) == 1:
        for h in encabezados:
            if h.casefold().strip() == objetivo[0]:
                return h
    for h in encabezados:
        hl = h.casefold()
        if all(f in hl for f in objetivo):
            return h
    return None


def _limpia(col: str) -> str:
    """Monto del formato ('$1,234.56', espacios) -> DOUBLE o NULL."""
    return ("TRY_CAST(replace(replace(replace(trim(" + col +
            "), '$', ''), ',', ''), ' ', '') AS DOUBLE)")


def _select_archivo(path: Path, formato: str) -> str:
    limpio = sanea(path)
    with open(limpio, encoding="utf-8") as fh:
        encabezados = next(csv.reader(fh))
    partes = []
    for logico, fragmentos in CAMPOS.items():
        col = columna(encabezados, *fragmentos)
        if col is None:
            if logico in REQUERIDOS:
                sys.exit(f"{path.name}: sin columna para {logico!r} "
                         f"(fragmentos {fragmentos})")
            partes.append(f"NULL AS {logico}")
        else:
            # read_csv recorta espacios en los nombres de columna
            partes.append('"' + col.strip().replace('"', '""')
                          + f'" AS {logico}')
    partes.append(f"'{formato}' AS formato")
    # ya saneado a ancho fijo: el lector veloz de DuckDB no se cae
    return (f"SELECT {', '.join(partes)} FROM read_csv('{limpio}', "
            "header=true, all_varchar=true, strict_mode=false, "
            "null_padding=true, parallel=false, "
            "delim=',', quote='\"', escape='\"')")


def load_pnt_views(con, files: list | None = None,
                   today: date | None = None) -> list[str]:
    """Crea la vista `contracts_pnt`. files: lista opcional de CSV; por
    defecto, todo data/raw/pnt/pnt_*.csv. today: reloj para el corte de
    siglo del RFC (tests). Sale del proceso si no hay archivos — los
    detectores son scripts y ese es su modo de fallo."""
    anio = (today or date.today()).year
    century_cutoff = anio % 100
    ejercicio_max = anio + 1  # admite el próximo ejercicio publicado por adelantado
    rutas = [Path(f) for f in (files or sorted(PNT_DIR.glob("pnt_*.csv")))]
    if not rutas:
        sys.exit("no hay CSVs en data/raw/pnt/ — corre scripts/pnt_contratos.py")
    selects = []
    for ruta in rutas:
        m = re.match(r"pnt_\d+_\d+_(\d+)\.csv$", ruta.name)
        selects.append(_select_archivo(ruta, m.group(1) if m else ""))
    union = " UNION ALL ".join(selects)

    con.execute(f"""
    CREATE VIEW contracts_pnt AS
    WITH tipado AS (
      SELECT
        upper(trim(estado)) AS estado_comprador,
        TRY_CAST(id_entidad AS INT) AS id_entidad,
        trim(id_sujeto) AS id_sujeto, trim(sujeto_obligado) AS sujeto_obligado,
        NULLIF(trim(ejercicio), '') AS ejercicio,
        tipo_procedimiento, materia, caracter,
        NULLIF(trim(expediente), '') AS expediente,
        NULLIF(trim(num_contrato), '') AS num_contrato,
        COALESCE(NULLIF(trim(razon_social), ''),
                 NULLIF(trim(concat_ws(' ', nombre_pf, ap1_pf, ap2_pf)), '')
        ) AS proveedor,
        NULLIF(upper(replace(replace(trim(rfc), ' ', ''), '-', '')), '')
          AS rfc_norm,
        COALESCE(TRY_STRPTIME(trim(fecha_contrato), '%d/%m/%Y'),
                 TRY_STRPTIME(trim(fecha_contrato), '%Y-%m-%d'),
                 TRY_STRPTIME(trim(inicio_vigencia), '%d/%m/%Y'),
                 TRY_STRPTIME(trim(inicio_vigencia), '%Y-%m-%d')
        ) AS fecha_efectiva,
        COALESCE({_limpia('monto_con_imp')}, {_limpia('monto_sin_imp')},
                 {_limpia('monto_max')}) AS importe,
        CASE WHEN {_limpia('monto_con_imp')} IS NOT NULL THEN 'con_impuestos'
             WHEN {_limpia('monto_sin_imp')} IS NOT NULL THEN 'sin_impuestos'
             ELSE 'techo_maximo' END AS tipo_monto,
        NULLIF(trim(moneda), '') AS moneda,
        COALESCE(NULLIF(trim(url_contrato), ''), NULLIF(trim(url_fallo), ''))
          AS direccion_anuncio,
        NULLIF(trim(url_fallo), '') AS url_fallo,
        municipio_proveedor, cp_proveedor, origen_recursos, convenio_modif,
        descripcion, objeto,
        COALESCE(TRY_STRPTIME(trim(fecha_actualizacion), '%d/%m/%Y'),
                 TRY_STRPTIME(trim(fecha_actualizacion), '%Y-%m-%d')
        ) AS fecha_actualizacion,
        formato
      FROM ({union})
    )
    SELECT * EXCLUDE (_rn) FROM (
      SELECT *,
        regexp_full_match(COALESCE(rfc_norm, ''), '{RFC_REGEX}') AS rfc_valido,
        length(COALESCE(rfc_norm, '')) = 12 AS es_persona_moral,
        {constitucion_rfc_sql("COALESCE(rfc_norm, '')", century_cutoff)}
          AS fecha_constitucion_rfc,
        row_number() OVER (
          -- identidad del contrato: número o expediente cuando existen (así
          -- el MISMO contrato re-reportado por trimestre o en dos formatos se
          -- funde); si AMBOS faltan, hash de descripción+objeto para no
          -- colapsar contratos DISTINTOS que comparten monto y fecha (los
          -- NULL se agrupan como uno solo en PARTITION BY — ese era el bug).
          PARTITION BY id_entidad, ejercicio, id_sujeto,
                       COALESCE(num_contrato, expediente,
                                md5(COALESCE(descripcion, '') || '|'
                                    || COALESCE(objeto, ''))),
                       rfc_norm, importe, fecha_efectiva
          ORDER BY fecha_actualizacion DESC NULLS LAST, formato DESC) AS _rn
      FROM tipado
      WHERE (proveedor IS NOT NULL OR rfc_norm IS NOT NULL)
        AND TRY_CAST(ejercicio AS INT)
            BETWEEN {EJERCICIO_MIN} AND {ejercicio_max}
        -- contracts_pnt es la capa ESTATAL: el catálogo de la PNT trae
        -- también entidades federales ("Federación", "Federación
        -- (Histórica)") que duplican lo que ya cubre ComprasMX y se
        -- contarían doble; fuera de aquí.
        AND estado_comprador NOT ILIKE 'FEDERACI%'
    ) WHERE _rn = 1
    """)
    return [str(r) for r in rutas]
