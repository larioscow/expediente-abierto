"""contracts_pnt deriva fecha de constitución del RFC y d10 marca empresas
jóvenes con contrato grande estatal (mismo criterio que d04 federal)."""
from datetime import date

import duckdb

from detectors.common import load_sfp_views, load_views
from detectors.d10_pnt_estatal import consultas
from detectors.pnt import load_pnt_views
from tests.fixtures import write_contracts_csv, write_efos_csv, write_pnt_csv
from tests.test_pnt_views import FECHA_H, MONTO_H, RAZON_H, RFC_H, base


def test_vista_deriva_constitucion_y_persona_moral(tmp_path):
    # RFC de persona moral constituida 2024-01-15
    pm = base(**{RFC_H: "ABC240115AA1", RAZON_H: "NUEVA SA DE CV"})
    # persona física (13): no es persona moral, sin fecha de constitución
    pf = base(**{RFC_H: "AECM800101AA1", RAZON_H: "",
                 "Nombre(s) de la persona física ganadora, asignada o adjudicada": "Ana",
                 "Primer apellido de la persona física ganadora, asignada o adjudicada": "Cruz",
                 "Número de expediente, folio o nomenclatura": "E2"})
    con = duckdb.connect()
    pnt = write_pnt_csv(tmp_path / "pnt_25_2024_59729.csv", [pm, pf])
    load_pnt_views(con, [pnt], today=date(2026, 6, 1))
    filas = {r[0]: r[1:] for r in con.execute(
        "SELECT proveedor, es_persona_moral, "
        "strftime(fecha_constitucion_rfc, '%Y-%m-%d') FROM contracts_pnt"
    ).fetchall()}
    assert filas["NUEVA SA DE CV"] == (True, "2024-01-15")
    assert filas["Ana Cruz"] == (False, None)


def test_d10_marca_joven_y_grande(tmp_path):
    contracts = write_contracts_csv(tmp_path / "contratos_2025.csv", [
        {"rfc": "ZZZ900101ZZ9", "proveedor": "REL", "moneda_drc": "MXN",
         "fecha_firma_contrato": "01/01/2025", "importe_drc": "1",
         "institucion": "X"}])
    efos = write_efos_csv(tmp_path / "efos.csv", [])
    sfp = tmp_path / "sfp.json"
    sfp.write_text("[]")
    # constituida 2024-09-01, contrato 2024-12-01 (92 días), $30M: joven+grande
    joven = base(**{RFC_H: "JOV240901AA1", RAZON_H: "RECIÉN NACIDA SA DE CV",
                    FECHA_H: "01/12/2024", MONTO_H: "$30,000,000"})
    # vieja: constituida 2010, mismo contrato grande -> NO joven
    vieja = base(**{RFC_H: "VIE100101AA1", RAZON_H: "VETERANA SA DE CV",
                    FECHA_H: "01/12/2024", MONTO_H: "$30,000,000",
                    "Número de expediente, folio o nomenclatura": "E2"})
    # joven pero contrato chico -> NO entra
    chico = base(**{RFC_H: "JOV240901BB2", RAZON_H: "JOVEN CHICA SA DE CV",
                    FECHA_H: "01/12/2024", MONTO_H: "$100,000",
                    "Número de expediente, folio o nomenclatura": "E3"})
    pnt = write_pnt_csv(tmp_path / "pnt_25_2024_59729.csv",
                        [joven, vieja, chico])
    con = duckdb.connect()
    load_views(con, [str(contracts)], efos_path=efos, today=date(2026, 6, 1))
    load_sfp_views(con, sfp_path=sfp)
    load_pnt_views(con, [pnt], today=date(2026, 6, 1))
    jov = consultas(con)["jovenes"]
    assert list(jov["proveedor"]) == ["RECIÉN NACIDA SA DE CV"]
    assert int(jov.iloc[0]["edad_dias"]) == 91


def test_d10_concentracion_de_directas(tmp_path):
    from detectors.d10_pnt_estatal import CONC_MIN_DIRECTAS
    from tests.test_pnt_views import EXP_H

    contracts = write_contracts_csv(tmp_path / "contratos_2025.csv", [
        {"rfc": "ZZZ900101ZZ9", "proveedor": "REL", "moneda_drc": "MXN",
         "fecha_firma_contrato": "01/01/2025", "importe_drc": "1",
         "institucion": "X"}])
    efos = write_efos_csv(tmp_path / "efos.csv", [])
    sfp = tmp_path / "sfp.json"
    sfp.write_text("[]")
    SO = "SIN - Municipio Capturado"
    DIR = "Adjudicación directa"
    tp = "Tipo de procedimiento (catálogo)"
    filas = []
    # DOMINANTE: 16 directas de $1M cada una = $16M en este sujeto obligado
    for i in range(CONC_MIN_DIRECTAS + 1):
        filas.append(base(**{RAZON_H: "DOMINANTE SA DE CV",
                             RFC_H: "DOM200101AA1", "Sujeto obligado": SO,
                             EXP_H: f"E{i}", MONTO_H: "$1,000,000", tp: DIR}))
    # otro proveedor con una directa chica de $200k (no concentra)
    filas.append(base(**{RAZON_H: "MENOR SA DE CV", RFC_H: "MEN200101AA1",
                         "Sujeto obligado": SO, EXP_H: "E99",
                         MONTO_H: "$200,000", tp: DIR}))
    pnt = write_pnt_csv(tmp_path / "pnt_25_2024_59729.csv", filas)
    con = duckdb.connect()
    load_views(con, [str(contracts)], efos_path=efos, today=date(2026, 6, 1))
    load_sfp_views(con, sfp_path=sfp)
    load_pnt_views(con, [pnt], today=date(2026, 6, 1))
    conc = consultas(con)["concentracion"]
    assert list(conc["proveedor"]) == ["DOMINANTE SA DE CV"]
    fila = conc.iloc[0]
    assert fila["contratos"] == CONC_MIN_DIRECTAS + 1
    assert fila["pct_del_gasto_directo"] > 95  # 16M de 16.2M


def test_d10_anillo_de_constitucion(tmp_path):
    """3 empresas 'competidoras' en un mismo sujeto obligado constituidas con
    días de diferencia = anillo; una constituida años después no entra."""
    from tests.test_pnt_views import EXP_H

    contracts = write_contracts_csv(tmp_path / "contratos_2025.csv", [
        {"rfc": "ZZZ900101ZZ9", "proveedor": "REL", "moneda_drc": "MXN",
         "fecha_firma_contrato": "01/01/2025", "importe_drc": "1",
         "institucion": "X"}])
    efos = write_efos_csv(tmp_path / "efos.csv", [])
    sfp = tmp_path / "sfp.json"
    sfp.write_text("[]")
    SO = "SIN - Municipio Anillo"
    # tres RFC constituidos en enero 2024 con pocos días de diferencia
    filas = [
        base(**{RFC_H: "AAA240105AA1", RAZON_H: "ALFA SA DE CV",
                "Sujeto obligado": SO, EXP_H: "E1", MONTO_H: "$3,000,000"}),
        base(**{RFC_H: "BBB240112AA1", RAZON_H: "BETA SA DE CV",
                "Sujeto obligado": SO, EXP_H: "E2", MONTO_H: "$2,000,000"}),
        base(**{RFC_H: "CCC240120AA1", RAZON_H: "GAMA SA DE CV",
                "Sujeto obligado": SO, EXP_H: "E3", MONTO_H: "$1,000,000"}),
        # forastera: constituida en 2019, no pertenece al anillo
        base(**{RFC_H: "DDD190101AA1", RAZON_H: "VIEJA SA DE CV",
                "Sujeto obligado": SO, EXP_H: "E4", MONTO_H: "$5,000,000"}),
    ]
    pnt = write_pnt_csv(tmp_path / "pnt_25_2024_59729.csv", filas)
    con = duckdb.connect()
    load_views(con, [str(contracts)], efos_path=efos, today=date(2026, 6, 1))
    load_sfp_views(con, sfp_path=sfp)
    load_pnt_views(con, [pnt], today=date(2026, 6, 1))
    anillos = consultas(con)["anillos"]
    assert len(anillos) == 1
    fila = anillos.iloc[0]
    assert fila["empresas"] == 3                       # VIEJA excluida
    assert fila["dias_entre_constituciones"] == 15     # 05 ene -> 20 ene
    assert "VIEJA" not in fila["proveedores"]
    # 3 del anillo de 4 proveedores persona-moral = 75% (>= piso de 25%)
    assert fila["proveedores_del_sujeto"] == 4
    assert fila["pct_del_sujeto"] == 75.0


def test_d10_anillo_ignora_compradores_enormes(tmp_path):
    """Un anillo de 3 dentro de un sujeto con MUCHOS proveedores (clustering
    por azar) no debe dispararse: piso de proporción ANILLO_MIN_SHARE."""
    from tests.test_pnt_views import EXP_H

    contracts = write_contracts_csv(tmp_path / "contratos_2025.csv", [
        {"rfc": "ZZZ900101ZZ9", "proveedor": "REL", "moneda_drc": "MXN",
         "fecha_firma_contrato": "01/01/2025", "importe_drc": "1",
         "institucion": "X"}])
    efos = write_efos_csv(tmp_path / "efos.csv", [])
    sfp = tmp_path / "sfp.json"
    sfp.write_text("[]")
    SO = "SIN - Comprador Enorme"
    filas = [base(**{RFC_H: f"AA{i:02d}40105AA1" if i < 3 else f"BB{i:02d}{2000+i:04d}AA1",
                     RAZON_H: f"EMP{i} SA DE CV", "Sujeto obligado": SO,
                     EXP_H: f"E{i}", MONTO_H: "$1,000,000"}) for i in range(20)]
    pnt = write_pnt_csv(tmp_path / "pnt_25_2024_59729.csv", filas)
    con = duckdb.connect()
    load_views(con, [str(contracts)], efos_path=efos, today=date(2026, 6, 1))
    load_sfp_views(con, sfp_path=sfp)
    load_pnt_views(con, [pnt], today=date(2026, 6, 1))
    # 3 co-constituidas de 20 proveedores = 15% < 25%: no es anillo
    assert consultas(con)["anillos"].empty


def test_concentracion_ignora_proveedores_basura(tmp_path):
    """'Hombre', 'PERSONA FISICA', URLs y boilerplate en el campo proveedor
    (corrimiento de columnas / redacción) no deben producir hallazgos."""
    from detectors.d10_pnt_estatal import CONC_MIN_DIRECTAS
    from tests.test_pnt_views import EXP_H

    efos = write_efos_csv(tmp_path / "efos.csv", [])
    sfp = tmp_path / "sfp.json"
    sfp.write_text("[]")
    SO = "SIN - Municipio Basura"
    tp = "Tipo de procedimiento (catálogo)"
    filas = []
    for i, basura in enumerate(["Hombre", "PERSONA FISICA",
                                "http://transparencia.x/doc", "PAREDES Hombre"]):
        for k in range(CONC_MIN_DIRECTAS + 1):
            filas.append(base(**{RAZON_H: basura, RFC_H: "", "Sujeto obligado": SO,
                                 EXP_H: f"E{i}_{k}", MONTO_H: "$1,000,000",
                                 tp: "Adjudicación directa"}))
    contracts = write_contracts_csv(tmp_path / "contratos_2025.csv", [
        {"rfc": "ZZZ900101ZZ9", "proveedor": "REL", "moneda_drc": "MXN",
         "fecha_firma_contrato": "01/01/2025", "importe_drc": "1",
         "institucion": "X"}])
    pnt = write_pnt_csv(tmp_path / "pnt_25_2024_59729.csv", filas)
    con = duckdb.connect()
    load_views(con, [str(contracts)], efos_path=efos, today=date(2026, 6, 1))
    load_sfp_views(con, sfp_path=sfp)
    load_pnt_views(con, [pnt], today=date(2026, 6, 1))
    assert consultas(con)["concentracion"].empty
