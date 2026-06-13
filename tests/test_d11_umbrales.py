"""d11 — bunching bajo umbrales: la prueba de signo local detecta el exceso
fabricado, ignora la densidad suave y excluye el monto exacto."""
import duckdb
import pytest

from detectors.common import load_views
from detectors.d11_umbrales import bunching_table
from shared.estadistica import binomial_sf_half
from tests.fixtures import write_contracts_csv, write_efos_csv


def test_binomial_sf_half_valores_conocidos():
    assert binomial_sf_half(6, 10) == pytest.approx(0.376953125)
    assert binomial_sf_half(8, 10) == pytest.approx(0.0546875)
    assert binomial_sf_half(0, 10) == 1.0
    assert binomial_sf_half(11, 10) == 0.0
    with pytest.raises(ValueError):
        binomial_sf_half(-1, 5)


def fila(importe, inst="SECRETARIA X", tipo="ADJUDICACIÓN DIRECTA", i=[0]):
    i[0] += 1
    return {"rfc": "AAA101010AB1", "proveedor": f"P{i[0]}",
            "fecha_firma_contrato": "15/03/2024",
            "importe_drc": f"{importe}", "moneda_drc": "MXN",
            "institucion": inst, "tipo_procedimiento": tipo}


def carga(tmp_path, filas):
    contracts = write_contracts_csv(tmp_path / "contratos_2024.csv", filas)
    efos = write_efos_csv(tmp_path / "efos.csv", [])
    con = duckdb.connect()
    load_views(con, [str(contracts)], efos_path=efos)
    return con


def test_exceso_fabricado_sale_significativo(tmp_path):
    # 60 contratos apenas bajo 1,000,000 y 5 apenas arriba: bunching claro
    filas = ([fila(985_000 + 100 * k) for k in range(60)]
             + [fila(1_020_000 + 100 * k) for k in range(5)])
    df = bunching_table(carga(tmp_path, filas))
    caso = df[df["umbral"] == 1_000_000].iloc[0]
    assert caso["bajo"] == 60 and caso["sobre"] == 5
    assert caso["p_binomial"] < 1e-6
    assert bool(caso["q_fdr05"])


def test_densidad_suave_no_alarma(tmp_path):
    # mitad y mitad alrededor del corte: razón ~1, sin señal
    filas = ([fila(980_000 + 500 * k) for k in range(30)]
             + [fila(1_005_000 + 500 * k) for k in range(30)])
    df = bunching_table(carga(tmp_path, filas))
    caso = df[df["umbral"] == 1_000_000].iloc[0]
    assert not bool(caso["q_fdr05"])
    assert caso["p_binomial"] > 0.3


def test_excluye_exacto_y_licitaciones(tmp_path):
    exactos = [fila(1_000_000) for _ in range(40)]
    licitados = [fila(990_000, tipo="LICITACIÓN PÚBLICA") for _ in range(50)]
    abajo = [fila(990_000 + 10 * k) for k in range(31)]
    df = bunching_table(carga(tmp_path, exactos + licitados + abajo))
    caso = df[df["umbral"] == 1_000_000].iloc[0]
    # los 40 exactos no entran a bajo/sobre; las licitaciones no cuentan
    assert caso["bajo"] == 31 and caso["sobre"] == 0
    assert caso["exacto"] == 40
    assert caso["pct_exacto"] == pytest.approx(100 * 40 / 71, abs=0.1)


def test_ventana_chica_no_se_prueba(tmp_path):
    df = bunching_table(carga(tmp_path, [fila(995_000) for _ in range(10)]))
    assert df.empty
