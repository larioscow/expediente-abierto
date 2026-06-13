"""Mapa ramo→estado (shared/ramos.py) y su columna derivada en la vista
contracts: el etiquetado GEM es lo que permite afirmar cobertura estatal."""
import duckdb

from detectors.common import load_views
from shared.ramos import RAMO_ESTADO, estado_de_numero, estado_de_ramo
from tests.fixtures import write_contracts_csv, write_efos_csv


def test_cubre_los_32_estados_en_ramos_60_a_91():
    assert sorted(RAMO_ESTADO) == list(range(60, 92))
    assert len(set(RAMO_ESTADO.values())) == 32


def test_estado_de_ramo():
    assert estado_de_ramo(66) == "CHIAPAS"
    assert estado_de_ramo("66") == "CHIAPAS"  # las claves del CSV son texto
    assert estado_de_ramo(7) is None          # federal
    assert estado_de_ramo("X1") is None
    assert estado_de_ramo(None) is None


def test_estado_de_numero_con_formatos_reales():
    # números reales observados en los CSV 2023 y en el listado en vivo
    assert estado_de_numero("AA-60-N68-901024986-N-32-2023") == "AGUASCALIENTES"
    assert estado_de_numero("IO-89-Y24-930007995-N-42-2023") == (
        "VERACRUZ DE IGNACIO DE LA LLAVE")
    assert estado_de_numero("LA-07-110-007000999-N-504-2026") is None  # SEDENA
    assert estado_de_numero("sin-formato") is None
    assert estado_de_numero("") is None
    assert estado_de_numero(None) is None


def test_vista_contracts_etiqueta_estado_comprador(tmp_path):
    contracts = write_contracts_csv(tmp_path / "contratos_2025.csv", [
        {"orden_gobierno": "GEM", "clave_ramo": "66", "rfc": "AAA101010AB1",
         "proveedor": "ACME", "fecha_firma_contrato": "15/03/2025",
         "importe_drc": "1,000,000", "moneda_drc": "MXN",
         "institucion": "SECRETARIA ESTATAL"},
        {"orden_gobierno": "APF", "clave_ramo": "7", "rfc": "BBB101010AB1",
         "proveedor": "OTRA", "fecha_firma_contrato": "15/03/2025",
         "importe_drc": "1,000,000", "moneda_drc": "MXN",
         "institucion": "SEDENA"},
    ])
    efos = write_efos_csv(tmp_path / "sat_69b.csv", [])
    con = duckdb.connect()
    load_views(con, [str(contracts)], efos_path=efos)
    filas = dict(con.execute(
        "SELECT proveedor, estado_comprador FROM contracts").fetchall())
    assert filas == {"ACME": "CHIAPAS", "OTRA": None}
