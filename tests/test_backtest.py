"""Backtest harness: a signal's precision is the rate at which flagged
suppliers are sanctioned AFTER the flag date, compared against all suppliers.
A sanction that predates the flag must never count as a prediction."""
from datetime import date

import duckdb
import pandas as pd
import pytest

from detectors.backtest import evaluate, sanction_dates
from detectors.common import load_views
from tests.fixtures import write_contracts_csv, write_efos_csv


def test_evaluate_counts_only_post_flag_sanctions():
    flags = pd.DataFrame({
        "rfc_norm": ["HIT1", "MISS", "LEAK"],
        "flag_date": [date(2023, 5, 1)] * 3,
    })
    universe = pd.DataFrame({
        "rfc_norm": ["HIT1", "MISS", "LEAK"] + [f"B{i}" for i in range(7)],
        "t0": [date(2023, 1, 1)] * 10,
    })
    sanctions = pd.DataFrame({
        "rfc_norm": ["HIT1", "LEAK", "B0"],
        "fecha_sancion": [date(2024, 2, 1),   # after flag -> predicted
                          date(2022, 12, 1),  # BEFORE flag -> leakage, excluded
                          date(2024, 6, 1)],  # baseline hit
    })
    r = evaluate("test_signal", flags, universe, sanctions)
    assert r["empresas_flag"] == 3
    assert r["sancionadas_despues"] == 1          # only HIT1
    # base = NO marcadas (universo − marcadas): 7 empresas, 1 sancionada (B0)
    assert r["base_empresas"] == 7
    assert r["base_sancionadas"] == 1
    assert r["lift"] == pytest.approx((1 / 3) / (1 / 7))
    assert r["mediana_dias_a_sancion"] == (date(2024, 2, 1) - date(2023, 5, 1)).days


def test_evaluate_reports_ci_and_fisher_against_nonflagged():
    """El 2×2 compara marcadas vs NO marcadas (universo − marcadas), no vs el
    universo completo, y trae CI de Wilson + Fisher exacto."""
    flags = pd.DataFrame({"rfc_norm": [f"F{i}" for i in range(10)],
                          "flag_date": [date(2023, 1, 1)] * 10})
    universe = pd.DataFrame({
        "rfc_norm": [f"F{i}" for i in range(10)] + [f"B{i}" for i in range(90)],
        "t0": [date(2023, 1, 1)] * 100})
    # 8 de 10 marcadas sancionadas después; 9 de 90 no marcadas
    sanc = ([f"F{i}" for i in range(8)] + [f"B{i}" for i in range(9)])
    sanctions = pd.DataFrame({"rfc_norm": sanc,
                              "fecha_sancion": [date(2024, 1, 1)] * len(sanc)})
    r = evaluate("fuerte", flags, universe, sanctions)
    assert r["sancionadas_despues"] == 8
    # base = no marcadas: 9/90, no 17/100
    assert r["lift"] == pytest.approx((8 / 10) / (9 / 90))
    assert r["p_fisher"] < 0.001            # enriquecimiento real
    assert "–" in r["tasa_flag_ic95"] and "–" in r["lift_ic95"]
    lift_lo = float(r["lift_ic95"].split("–")[0])
    assert lift_lo > 1                       # el IC del lift no toca la base


def test_base_excluye_marcadas_por_rfc_no_por_resta():
    """Una marcada sancionada ENTRE su primer contrato y su flag_date cuenta
    en el universo (post-t0) pero no en las marcadas (post-flag). Restar
    conteos la dejaría en la base; excluir por RFC no. Regresión del bug."""
    flags = pd.DataFrame({"rfc_norm": ["FUGA"],
                          "flag_date": [date(2023, 6, 1)]})
    universe = pd.DataFrame({
        "rfc_norm": ["FUGA"] + [f"B{i}" for i in range(9)],
        "t0": [date(2023, 1, 1)] * 10})
    # FUGA sancionada 2023-03 (después de t0, ANTES de flag): 0 aciertos marcados
    sanctions = pd.DataFrame({"rfc_norm": ["FUGA"],
                              "fecha_sancion": [date(2023, 3, 1)]})
    r = evaluate("fuga", flags, universe, sanctions)
    assert r["sancionadas_despues"] == 0     # FUGA no es acierto marcado
    assert r["base_empresas"] == 9           # universo SIN FUGA
    assert r["base_sancionadas"] == 0        # FUGA no contamina la base
    # con la resta vieja: base_sancionadas habría sido n_uhit-n_hit = 1-0 = 1


def test_evaluate_handles_no_flags():
    r = evaluate("empty", pd.DataFrame(columns=["rfc_norm", "flag_date"]),
                 pd.DataFrame({"rfc_norm": ["A"], "t0": [date(2023, 1, 1)]}),
                 pd.DataFrame(columns=["rfc_norm", "fecha_sancion"]))
    assert r["empresas_flag"] == 0 and r["lift"] is None
    assert r["p_fisher"] is None and r["lift_ic95"] is None


def test_sanction_dates_takes_earliest_source(tmp_path):
    contracts = write_contracts_csv(tmp_path / "contratos_2024.csv", [
        {"rfc": "AAA101010AB1", "proveedor": "ACME CONSULTORES",
         "fecha_firma_contrato": "15/03/2024", "importe_drc": "1,000,000",
         "moneda_drc": "MXN"},
    ])
    efos = write_efos_csv(tmp_path / "efos.csv", [
        {"rfc": "AAA101010AB1", "nombre": "ACME CONSULTORES SA DE CV",
         "situacion": "Definitivo", "pub_dof_presuntos": "01/06/2024",
         "pub_dof_definitivos": "01/06/2025"},
    ])
    con = duckdb.connect()
    load_views(con, [str(contracts)], efos_path=efos)
    s = sanction_dates(con)
    # presunto publication is the earliest signal the state itself emitted
    assert s.set_index("rfc_norm").loc["AAA101010AB1", "fecha_sancion"] == date(2024, 6, 1)
