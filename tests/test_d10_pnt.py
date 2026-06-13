"""d10 — contratos estatales (PNT) cruzados contra 69-B y sancionados:
el cruce por RFC exige RFC válido; el respaldo por nombre va aparte."""
import json

import duckdb

from detectors.common import load_sfp_views, load_views
from detectors.d10_pnt_estatal import consultas
from detectors.pnt import load_pnt_views
from tests.fixtures import write_contracts_csv, write_efos_csv, write_pnt_csv
from tests.test_pnt_views import FECHA_H, MONTO_H, RAZON_H, RFC_H, base


def arma(tmp_path, filas_pnt):
    contracts = write_contracts_csv(tmp_path / "contratos_2025.csv", [
        {"rfc": "ZZZ900101ZZ9", "proveedor": "RELLENO FEDERAL",
         "fecha_firma_contrato": "01/01/2025", "importe_drc": "1",
         "moneda_drc": "MXN", "institucion": "X"}])
    efos = write_efos_csv(tmp_path / "sat_69b.csv", [
        {"rfc": "AAA101010AB1", "nombre": "ACME SA DE CV",
         "situacion": "Definitivo", "pub_dof_definitivos": "01/06/2023"},
        {"rfc": "FAC150612873", "nombre": "COMERCIALIZADORA PATITO SA DE CV",
         "situacion": "Definitivo", "pub_dof_definitivos": "01/06/2023"},
    ])
    sfp = tmp_path / "sfp.json"
    sfp.write_text(json.dumps([{
        "rfc": "AAA101010AB1", "nombre_razon_social": "ACME SA DE CV",
        "institucion_dependencia": "SFP",
        "plazo": {"fecha_inicial": "2024-01-01", "fecha_final": "2024-12-31",
                  "plazo_inha": "1 año"},
    }]))
    pnt = write_pnt_csv(tmp_path / "pnt_25_2024_59729.csv", filas_pnt)
    con = duckdb.connect()
    load_views(con, [str(contracts)], efos_path=efos)
    load_sfp_views(con, sfp_path=sfp)
    load_pnt_views(con, [pnt])
    return consultas(con)


def test_cruce_efos_y_ventana_de_inhabilitacion(tmp_path):
    dentro = base()  # ACME, RFC AAA..., contrato 15/03/2024: dentro de la
    fuera = base(**{FECHA_H: "15/03/2025",  # ventana 2024; este queda fuera
                    "Número de expediente, folio o nomenclatura": "EXP-9"})
    t = arma(tmp_path, [dentro, fuera])

    assert len(t["efos"]) == 2  # ambos contratos a la facturera Definitiva
    assert set(t["efos"]["firmado_despues_definitivo"]) == {True}
    inhab = t["inhabilitados"]
    assert len(inhab) == 2
    assert sorted(inhab["durante_inhabilitacion"]) == [False, True]
    assert t["cobertura"].iloc[0]["contratos"] == 2


def test_respaldo_por_nombre_solo_sin_rfc_valido(tmp_path):
    sin_rfc = base(**{RFC_H: "", RAZON_H: "Comercializadora Patito, S.A. de C.V.",
                      MONTO_H: "$500.00"})
    t = arma(tmp_path, [sin_rfc])
    assert len(t["efos"]) == 0          # sin RFC válido no entra al cruce duro
    assert len(t["por_nombre"]) == 1    # pero el nombre normalizado sí matchea
    assert t["por_nombre"].iloc[0]["rfc_69b"] == "FAC150612873"


def test_importe_implausible_queda_marcado_no_sumado(tmp_path):
    absurdo = base(**{MONTO_H: "$999,999,999,999.00"})
    t = arma(tmp_path, [absurdo])
    assert bool(t["efos"].iloc[0]["importe_plausible"]) is False
    cob = t["cobertura"].iloc[0]
    assert cob["monto_mxn_millones"] != cob["monto_mxn_millones"] or \
        cob["monto_mxn_millones"] == 0  # NaN o 0: jamás suma el absurdo
