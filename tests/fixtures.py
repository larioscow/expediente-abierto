"""Builders for miniature government CSVs matching the real layouts."""
import csv

from detectors.common import CONTRACT_COLS, EFOS_COLS


def write_contracts_csv(path, rows: list[dict]):
    """rows: dicts keyed by CONTRACT_COLS names; missing keys become ''.
    Real files have 1 header row (skip=1)."""
    with open(path, "w", encoding="cp1252", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CONTRACT_COLS)  # header (skipped by the reader)
        for r in rows:
            w.writerow([r.get(c, "") for c in CONTRACT_COLS])
    return path


def write_efos_csv(path, rows: list[dict]):
    """rows: dicts keyed by EFOS_COLS names. Real files have a 3-row preamble."""
    with open(path, "w", encoding="cp1252", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["preamble"] + [""] * (len(EFOS_COLS) - 1))
        w.writerow([""] * len(EFOS_COLS))
        w.writerow(EFOS_COLS)
        for r in rows:
            w.writerow([r.get(c, "") for c in EFOS_COLS])
    return path


# Encabezados reales de un export PNT fr. XXVIII (Sinaloa 2024, formato
# 59729) con las 4 columnas de atribución que inyecta scripts/pnt_contratos.
# Solo los que usan las pruebas van completos; el resto se abrevia con el
# mismo texto inicial real para que la resolución por fragmentos trabaje
# sobre nombres verídicos.
PNT_HEADERS = [
    "Entidad federativa", "Id entidad federativa", "Id sujeto obligado",
    "Sujeto obligado", "Ejercicio",
    "Fecha de inicio del periodo que se informa",
    "Fecha de término del periodo que se informa",
    "Tipo de procedimiento (catálogo)",
    "Materia o tipo de contratación (catálogo)",
    "Carácter del procedimiento (catálogo)",
    "Número de expediente, folio o nomenclatura",
    "Descripción de las obras públicas, los bienes o los servicios "
    "contratados o arrendados",
    "Hipervínculo al acta de fallo adjudicatorio y a la resolución de "
    "asignación del contrato u oficio de notificación de adjudicación.",
    "Nombre(s) de la persona física ganadora, asignada o adjudicada",
    "Primer apellido de la persona física ganadora, asignada o adjudicada",
    "Segundo apellido de la persona física ganadora, asignada o adjudicada",
    "Denominación o razón social",
    "Registro Federal de Contribuyentes (RFC) de la persona física o moral "
    "contratista o proveedora ganadora, asignada o adjudicada",
    "Domicilio fiscal de la empresa, persona contratista o proveedora. "
    "Nombre del municipio o delegación",
    "Domicilio fiscal de la empresa, persona contratista o proveedora. "
    "Código postal",
    "Número que identifique al contrato ",
    "Fecha del contrato expresada con el formato día/mes/año",
    "Fecha de inicio de la vigencia del contrato (día/mes/año)",
    "Monto del contrato sin impuestos (en MXN)",
    "Monto total del contrato con impuestos incluidos (MXN)",
    "Monto máximo, con impuestos incluidos, en su caso",
    "Tipo de moneda",
    "Objeto del contrato",
    "Hipervínculo al documento del contrato y sus anexos, en versión "
    "pública si así corresponde.",
    "Origen de los recursos públicos (catálogo)",
    "Se realizaron convenios y/o contratos modificatorios (catálogo):",
    "Fecha de actualización", "Nota",
]


def write_pnt_csv(path, rows: list[dict]):
    """rows: dicts keyed por encabezado EXACTO de PNT_HEADERS; lo demás ''."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(PNT_HEADERS)
        for r in rows:
            w.writerow([r.get(c, "") for c in PNT_HEADERS])
    return path
