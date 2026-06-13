"""Correctitud de la vista contracts_pnt (detectors/pnt.py): resolución de
columnas por fragmento, normalización y dedupe entre formatos/trimestres."""
import duckdb

from detectors.pnt import columna, load_pnt_views
from tests.fixtures import PNT_HEADERS, write_pnt_csv

RFC_H = next(h for h in PNT_HEADERS if h.startswith("Registro Federal"))
RAZON_H = "Denominación o razón social"
MONTO_H = "Monto total del contrato con impuestos incluidos (MXN)"
FECHA_H = "Fecha del contrato expresada con el formato día/mes/año"
ACT_H = "Fecha de actualización"
EXP_H = "Número de expediente, folio o nomenclatura"
FALLO_H = next(h for h in PNT_HEADERS if "acta de fallo" in h)
CONTRATO_H = next(h for h in PNT_HEADERS if "documento del contrato" in h)


def base(**kw):
    fila = {
        "Entidad federativa": "Sinaloa", "Id entidad federativa": "25",
        "Id sujeto obligado": "4001", "Sujeto obligado": "SIN - Secretaría X",
        "Ejercicio": "2024", "Tipo de procedimiento (catálogo)":
        "Adjudicación directa", EXP_H: "EXP-1",
        RAZON_H: "ACME SA DE CV", RFC_H: "AAA101010AB1",
        MONTO_H: "$1,234,567.89", FECHA_H: "15/03/2024",
        ACT_H: "01/04/2024", FALLO_H: "https://x/fallo.pdf",
    }
    fila.update(kw)
    return fila


def vista(tmp_path, archivos: dict[str, list[dict]]):
    rutas = [write_pnt_csv(tmp_path / nombre, filas)
             for nombre, filas in archivos.items()]
    con = duckdb.connect()
    load_pnt_views(con, rutas)
    return con


def test_columna_prefiere_igualdad_exacta():
    assert columna(PNT_HEADERS, "sujeto obligado") == "Sujeto obligado"
    assert columna(PNT_HEADERS, "id sujeto") == "Id sujeto obligado"
    assert columna(PNT_HEADERS, "no existe") is None


def test_normalizacion_y_atribucion(tmp_path):
    con = vista(tmp_path, {"pnt_25_2024_59729.csv": [base()]})
    fila = con.execute("""
      SELECT estado_comprador, sujeto_obligado, proveedor, rfc_norm,
             rfc_valido, importe, strftime(fecha_efectiva, '%Y-%m-%d'),
             direccion_anuncio, tipo_monto, formato
      FROM contracts_pnt""").fetchone()
    assert fila == ("SINALOA", "SIN - Secretaría X", "ACME SA DE CV",
                    "AAA101010AB1", True, 1234567.89, "2024-03-15",
                    "https://x/fallo.pdf", "con_impuestos", "59729")


def test_persona_fisica_y_rfc_sucio(tmp_path):
    pf = base(**{
        RAZON_H: "", RFC_H: " hebj 901114-8la ",
        "Nombre(s) de la persona física ganadora, asignada o adjudicada": "Juan",
        "Primer apellido de la persona física ganadora, asignada o adjudicada": "Hernández",
        "Segundo apellido de la persona física ganadora, asignada o adjudicada": "Bogarin",
    })
    basura = base(**{EXP_H: "EXP-2", RFC_H: "NA"})
    vacia = base(**{EXP_H: "EXP-3", RAZON_H: "", RFC_H: ""})
    con = vista(tmp_path, {"pnt_25_2024_59729.csv": [pf, basura, vacia]})
    filas = con.execute("""
      SELECT proveedor, rfc_norm, rfc_valido FROM contracts_pnt
      ORDER BY expediente""").fetchall()
    assert filas == [
        ("Juan Hernández Bogarin", "HEBJ9011148LA", True),
        ("ACME SA DE CV", "NA", False),  # basura: queda marcada, no se cae
    ]  # la fila sin proveedor ni RFC se filtra


def test_dedupe_gana_la_actualizacion_mas_reciente(tmp_path):
    viejo = base(**{MONTO_H: "$1,234,567.89", ACT_H: "01/04/2024",
                    CONTRATO_H: ""})
    nuevo = base(**{MONTO_H: "$1,234,567.89", ACT_H: "01/07/2024",
                    CONTRATO_H: "https://x/contrato.pdf"})
    con = vista(tmp_path, {
        "pnt_25_2024_59729.csv": [viejo, nuevo],   # re-reporte trimestral
        "pnt_25_2024_59730.csv": [viejo],          # formato espejo
    })
    filas = con.execute("""
      SELECT direccion_anuncio, formato FROM contracts_pnt""").fetchall()
    assert filas == [("https://x/contrato.pdf", "59729")]


def test_importes_distintos_no_se_colapsan(tmp_path):
    a = base()
    b = base(**{MONTO_H: "$999.00"})
    con = vista(tmp_path, {"pnt_25_2024_59729.csv": [a, b]})
    assert con.execute("SELECT count(*) FROM contracts_pnt").fetchone()[0] == 2


def test_sin_id_contratos_distintos_no_se_funden(tmp_path):
    """Dos contratos SIN número ni expediente, mismo SO/RFC/monto/fecha pero
    distinto objeto, no deben colapsar (los NULL se agrupan en PARTITION BY:
    el bug del review). Con descripción/objeto distintos sobreviven ambos."""
    OBJ_H = "Objeto del contrato"
    a = base(**{EXP_H: "", RAZON_H: "ACME SA DE CV", OBJ_H: "papelería"})
    b = base(**{EXP_H: "", RAZON_H: "ACME SA DE CV", OBJ_H: "mobiliario"})
    con = vista(tmp_path, {"pnt_25_2024_59729.csv": [a, b]})
    assert con.execute("SELECT count(*) FROM contracts_pnt").fetchone()[0] == 2


def test_sin_id_mismo_contrato_reportado_dos_veces_se_funde(tmp_path):
    """El MISMO contrato sin id, re-reportado (mismo objeto), sí se funde."""
    OBJ_H = "Objeto del contrato"
    a = base(**{EXP_H: "", OBJ_H: "papelería", ACT_H: "01/04/2024"})
    b = base(**{EXP_H: "", OBJ_H: "papelería", ACT_H: "01/07/2024"})
    con = vista(tmp_path, {"pnt_25_2024_59729.csv": [a, b]})
    assert con.execute("SELECT count(*) FROM contracts_pnt").fetchone()[0] == 1


def test_ejercicio_corrupto_se_descarta(tmp_path):
    bueno = base()
    corrupto = base(**{"Ejercicio": "2525", EXP_H: "EXP-X"})
    viejo = base(**{"Ejercicio": "2014", EXP_H: "EXP-Y"})
    con = vista(tmp_path, {"pnt_25_2024_59729.csv": [bueno, corrupto, viejo]})
    ejercicios = [r[0] for r in con.execute(
        "SELECT ejercicio FROM contracts_pnt").fetchall()]
    assert ejercicios == ["2024"]  # 2525 y 2014 fuera de rango


def test_tope_de_ejercicio_sigue_el_reloj(tmp_path):
    """El tope superior es año-en-curso+1: en 2028 un ejercicio 2028 es
    válido (antes lo rechazaba el literal 2027). Regresión de bomba de tiempo."""
    from datetime import date
    import duckdb
    from detectors.pnt import load_pnt_views
    filas = [base(**{"Ejercicio": "2028", EXP_H: "E1"}),
             base(**{"Ejercicio": "2030", EXP_H: "E2"})]  # 2030 > 2028+1
    pnt = write_pnt_csv(tmp_path / "pnt_25_2024_59729.csv", filas)
    con = duckdb.connect()
    load_pnt_views(con, [pnt], today=date(2028, 6, 1))
    ej = [r[0] for r in con.execute(
        "SELECT ejercicio FROM contracts_pnt").fetchall()]
    assert ej == ["2028"]  # 2028 aceptado, 2030 (futuro lejano) descartado
