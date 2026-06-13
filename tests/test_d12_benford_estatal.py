"""d12 — Benford estatal: reusa benford_por_grupo sobre contracts_pnt,
acota plausibilidad y agrupa por sujeto obligado."""
import duckdb

from detectors.d03_benford import benford_por_grupo
from detectors.pnt import load_pnt_views
from tests.fixtures import write_pnt_csv
from tests.test_pnt_views import EXP_H, MONTO_H, base

SO_H = "Sujeto obligado"


def vista(tmp_path, filas):
    pnt = write_pnt_csv(tmp_path / "pnt_25_2024_59729.csv", filas)
    con = duckdb.connect()
    load_pnt_views(con, [pnt])
    return con


def test_benford_estatal_marca_amaño_y_acota_plausibilidad(tmp_path):
    # 250 montos casi todos empezando en 9 para UN sujeto: no conforme.
    # Más un importe absurdo que el filtro de plausibilidad debe excluir.
    filas = [base(**{SO_H: "SIN - Secretaría Amañada", EXP_H: f"E{i}",
                     MONTO_H: f"9{i % 90:02d}000"}) for i in range(250)]
    filas.append(base(**{SO_H: "SIN - Secretaría Amañada", EXP_H: "ABSURDO",
                         MONTO_H: "$999,999,999,999"}))
    con = vista(tmp_path, filas)
    df, por = benford_por_grupo(
        con, "contracts_pnt", "sujeto_obligado",
        filtro="importe BETWEEN 1 AND 5e9", min_n=200)
    fila = df[df["sujeto_obligado"] == "SIN - Secretaría Amañada"].iloc[0]
    assert fila["n_contratos"] == 250          # el absurdo quedó fuera
    assert fila["banda_nigrini"] == "NO CONFORME"
    assert bool(fila["no_conforme_fdr05"])


def test_sujeto_chico_no_se_analiza(tmp_path):
    filas = [base(**{SO_H: "SIN - Chica", EXP_H: f"E{i}"}) for i in range(50)]
    con = vista(tmp_path, filas)
    df, _ = benford_por_grupo(con, "contracts_pnt", "sujeto_obligado",
                              filtro="TRUE", min_n=200)
    assert df.empty
