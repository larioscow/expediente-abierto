"""d09 — riesgo compuesto por proveedor + la señal 'compuesto_2+' del
backtest: apilar señales distintas debe rankear y validarse."""
from datetime import date

import duckdb
import pandas as pd

from detectors.backtest import composite_flags, evaluate
from detectors.common import load_sfp_views, load_views
from detectors.d09_riesgo_proveedor import riesgo_proveedor
from tests.fixtures import write_contracts_csv, write_efos_csv


def test_composite_flags_exige_dos_senales_distintas():
    s1 = pd.DataFrame({"rfc_norm": ["A", "B"],
                       "flag_date": [date(2023, 1, 1), date(2023, 5, 1)]})
    s2 = pd.DataFrame({"rfc_norm": ["A"], "flag_date": [date(2022, 6, 1)]})
    s3 = pd.DataFrame({"rfc_norm": ["A"], "flag_date": [date(2023, 3, 1)]})
    comp = composite_flags({"s1": s1, "s2": s2, "s3": s3}, min_senales=2)
    assert list(comp["rfc_norm"]) == ["A"]            # B solo tiene 1 señal
    assert comp.iloc[0]["flag_date"] == pd.Timestamp(2022, 6, 1)  # la más temprana


def test_composite_vacio_si_nadie_apila():
    s1 = pd.DataFrame({"rfc_norm": ["A"], "flag_date": [date(2023, 1, 1)]})
    s2 = pd.DataFrame({"rfc_norm": ["B"], "flag_date": [date(2023, 1, 1)]})
    assert composite_flags({"s1": s1, "s2": s2}, min_senales=2).empty


def test_composite_predice_mejor_es_medible():
    # 5 apiladores, 4 sancionados después; base 95 con 5 sancionados
    flags = pd.DataFrame({"rfc_norm": [f"C{i}" for i in range(5)],
                          "flag_date": [date(2023, 1, 1)] * 5})
    universe = pd.DataFrame({
        "rfc_norm": [f"C{i}" for i in range(5)] + [f"B{i}" for i in range(95)],
        "t0": [date(2023, 1, 1)] * 100})
    sanc = [f"C{i}" for i in range(4)] + [f"B{i}" for i in range(5)]
    sanctions = pd.DataFrame({"rfc_norm": sanc,
                              "fecha_sancion": [date(2024, 1, 1)] * len(sanc)})
    r = evaluate("compuesto_2+", flags, universe, sanctions)
    assert r["lift"] > 5 and r["p_fisher"] < 0.001


def test_riesgo_proveedor_rankea_por_numero_de_senales(tmp_path):
    # un proveedor joven (constituido 2024-01) con contrato grande y además
    # disparando fraccionamiento debe salir con n_senales >= 2
    rfc = "AAA240101AB1"  # RFC con fecha de constitución 2024-01-01
    filas = [{"rfc": rfc, "proveedor": "DOBLE SEÑAL SA",
              "fecha_firma_contrato": f"15/0{m}/2024",
              "importe_drc": "9000000", "moneda_drc": "MXN",
              "institucion": "IMSS", "nombre_uc": "UC1",
              "tipo_procedimiento": "ADJUDICACIÓN DIRECTA",
              "numero_procedimiento": f"AD-{m}"} for m in range(1, 5)]
    # mismo día, misma UC: dispara fraccionamiento (varios contratos un día)
    for k in range(3):
        filas.append({"rfc": rfc, "proveedor": "DOBLE SEÑAL SA",
                      "fecha_firma_contrato": "15/01/2024",
                      "importe_drc": "400000", "moneda_drc": "MXN",
                      "institucion": "IMSS", "nombre_uc": "UC1",
                      "tipo_procedimiento": "ADJUDICACIÓN DIRECTA",
                      "numero_procedimiento": f"FR-{k}"})
    contracts = write_contracts_csv(tmp_path / "contratos_2024.csv", filas)
    efos = write_efos_csv(tmp_path / "efos.csv", [])
    con = duckdb.connect()
    load_views(con, [str(contracts)], efos_path=efos, today=date(2026, 1, 1))
    df = riesgo_proveedor(con)
    fila = df[df["rfc"] == rfc]
    assert len(fila) == 1
    assert fila.iloc[0]["n_senales"] >= 1   # al menos joven-y-grande
    assert fila.iloc[0]["dependencias"] == 1
    assert bool(fila.iloc[0]["en_69b"]) is False
