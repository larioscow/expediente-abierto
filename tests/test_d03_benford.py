"""d03 — Benford de primer y segundo dígito + Z de Nigrini por dígito.
Verifica las expresiones SQL de extracción de dígitos y que el detector
marca como anómalo un exceso fabricado."""
import duckdb
import pandas as pd

from detectors.common import load_views
from detectors.d03_benford import D1_SQL, D2_SQL, banda
from detectors.d03_benford import main as d03_main
from tests.fixtures import write_contracts_csv, write_efos_csv


def test_extraccion_de_digitos_sql():
    con = duckdb.connect()
    df = con.execute(f"""
      SELECT importe, {D1_SQL} AS d1, {D2_SQL} AS d2 FROM (VALUES
        (193.0), (1900.0), (905.0), (40.5), (7.0)
      ) t(importe)""").fetchdf()
    assert list(df["d1"]) == [1, 1, 9, 4, 7]
    assert list(df["d2"]) == [9, 9, 0, 0, 0]


def test_bandas_por_tope():
    bandas = ((0.006, "conforme"), (0.012, "aceptable"), (0.015, "marginal"))
    assert banda(0.003, bandas) == "conforme"
    assert banda(0.013, bandas) == "marginal"
    assert banda(0.05, bandas) == "NO CONFORME"


def test_exceso_fabricado_sale_anomalo(tmp_path, monkeypatch, capsys):
    # 400 contratos casi todos empezando en 9 (amaño bajo umbral): el primer
    # dígito jamás conforma y el dígito 9 debe marcarse anómalo (Z alto).
    filas = [{"rfc": "AAA101010AB1", "proveedor": "P",
              "fecha_firma_contrato": "15/03/2024",
              "importe_drc": f"9{i % 90:02d}000", "moneda_drc": "MXN",
              "institucion": "INST AMAÑADA"} for i in range(400)]
    contracts = write_contracts_csv(tmp_path / "contratos_2024.csv", filas)
    efos = write_efos_csv(tmp_path / "efos.csv", [])
    out = tmp_path / "findings"
    out.mkdir()
    monkeypatch.setattr("detectors.d03_benford.OUT", out)
    monkeypatch.setattr("sys.argv", ["d03", str(contracts)])
    monkeypatch.setattr("detectors.d03_benford.load_views",
                        lambda con, *a, **k: load_views(con, [str(contracts)],
                                                        efos_path=str(efos)))
    d03_main()

    inst = pd.read_csv(out / "f03_benford_instituciones.csv")
    assert {"mad", "banda_nigrini", "mad_segundo_digito",
            "banda_segundo_digito"} <= set(inst.columns)
    assert inst.iloc[0]["banda_nigrini"] == "NO CONFORME"

    dig = pd.read_csv(out / "f03_peor_institucion_digitos.csv")
    assert {"z_nigrini", "anomalo"} <= set(dig.columns)
    nueve = dig[dig["digito"] == 9].iloc[0]
    assert nueve["pct_observado"] > 90 and bool(nueve["anomalo"])
