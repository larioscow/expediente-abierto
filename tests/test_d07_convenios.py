"""d07 — contract inflation via convenios modificatorios.

LAASSP art. 52 caps modifications at +20% of the original amount; LOPSRM
art. 59 allows up to +25% for public works. An último-convenio amount above
the applicable cap is a legally anchored screen."""
import duckdb
import pytest

from detectors.common import load_views
from detectors.d07_convenios import inflated_modifications
from tests.fixtures import write_contracts_csv, write_efos_csv

LAASSP = "LEY DE ADQUISICIONES, ARRENDAMIENTOS Y SERVICIOS DEL SECTOR PÚBLICO"
LOPSRM = "LEY DE OBRAS PÚBLICAS Y SERVICIOS RELACIONADOS CON LAS MISMAS"


def contract(prov, orig, ultimo, ley=LAASSP):
    return {"institucion": "INST X", "nombre_uc": "UC X", "proveedor": prov,
            "rfc": "AAA101010AB1", "ley": ley, "convenio_modificatorio": "SI",
            "tipo_procedimiento": "LICITACIÓN PÚBLICA",
            "fecha_firma_contrato": "10/05/2024", "moneda_drc": "MXN",
            "monto_max_con_imp": orig, "monto_max_con_imp_uc": ultimo}


@pytest.fixture
def con(tmp_path):
    rows = [
        contract("ADQ_INFLADO_30", "1,000,000", "1,300,000"),            # +30% > 20%
        contract("ADQ_DENTRO_15", "1,000,000", "1,150,000"),             # +15% ok
        contract("OBRA_22", "1,000,000", "1,220,000", ley=LOPSRM),       # +22% < 25%
        contract("OBRA_40", "1,000,000", "1,400,000", ley=LOPSRM),       # +40% > 25%
        {"proveedor": "SIN_CONVENIO", "rfc": "BBB101010AB1",
         "institucion": "INST X", "fecha_firma_contrato": "10/05/2024",
         "importe_drc": "2,000,000", "moneda_drc": "MXN"},
    ]
    contracts = write_contracts_csv(tmp_path / "contratos_2024.csv", rows)
    c = duckdb.connect()
    load_views(c, [str(contracts)],
               efos_path=write_efos_csv(tmp_path / "efos.csv", []))
    return c


def test_flags_only_above_the_applicable_legal_cap(con):
    df = inflated_modifications(con)
    assert set(df["proveedor"]) == {"ADQ_INFLADO_30", "OBRA_40"}


def test_exactly_at_cap_is_legal_not_flagged(tmp_path):
    """LAASSP art. 52 permite crecer HASTA 20%: un convenio exactamente en el
    tope es legal. El float binario de 1.2 queda apenas debajo de 1.2 exacto,
    así que el `>` estricto marcaba estos contratos como violación (50 de 109
    falsos positivos en la corrida 2026-06-11)."""
    rows = [
        contract("EXACTO_20", "33,502,120.08", "40,202,544.10"),       # +20.000%
        contract("EXACTO_20_REDONDO", "900,000", "1,080,000"),         # +20% exacto
        contract("OBRA_EXACTO_25", "1,000,000", "1,250,000", ley=LOPSRM),
        contract("APENAS_ARRIBA_21", "1,000,000", "1,210,000"),        # +21%
    ]
    contracts = write_contracts_csv(tmp_path / "contratos_2024.csv", rows)
    c = duckdb.connect()
    load_views(c, [str(contracts)],
               efos_path=write_efos_csv(tmp_path / "efos.csv", []))
    df = inflated_modifications(c)
    assert set(df["proveedor"]) == {"APENAS_ARRIBA_21"}


def test_reports_increment_and_cap(con):
    df = inflated_modifications(con).set_index("proveedor")
    assert df.loc["ADQ_INFLADO_30", "pct_incremento"] == 30.0
    assert df.loc["ADQ_INFLADO_30", "tope_legal_pct"] == 20.0
    assert df.loc["OBRA_40", "tope_legal_pct"] == 25.0
