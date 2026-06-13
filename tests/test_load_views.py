"""Correctness of the shared contracts/efos views in detectors/common.py."""
from datetime import date
from pathlib import Path

import duckdb
import pytest

from detectors.common import load_views, utf8_copy
from tests.fixtures import write_contracts_csv, write_efos_csv


def test_utf8_copy_distinguishes_same_stem_sources(tmp_path):
    """Two different source files with the same filename must never share a
    cache entry — a test fixture named contratos_2024.csv must not shadow
    data/raw/contratos_2024.csv (this corrupted real findings once)."""
    a = tmp_path / "a" / "contratos_2024.csv"
    b = tmp_path / "b" / "contratos_2024.csv"
    for p, content in ((a, "AAA"), (b, "BBB")):
        p.parent.mkdir()
        p.write_text(content)
    out_a, out_b = utf8_copy(a), utf8_copy(b)
    assert out_a != out_b
    assert Path(out_a).read_text() == "AAA"
    assert Path(out_b).read_text() == "BBB"
    # the file_year regex still finds the year at the end of the name
    assert out_a.endswith("contratos_2024.utf8.csv")


def make_con(tmp_path, contract_rows, today=None):
    contracts = write_contracts_csv(tmp_path / "contratos_2025.csv", contract_rows)
    efos = write_efos_csv(tmp_path / "sat_69b.csv", [
        {"rfc": "AAA101010AB1", "nombre": "ACME SA DE CV", "situacion": "Definitivo",
         "pub_dof_definitivos": "01/06/2015"},
    ])
    con = duckdb.connect()
    load_views(con, [str(contracts)], efos_path=efos, today=today)
    return con


def row(**kw):
    base = {"rfc": "AAA101010AB1", "proveedor": "ACME",
            "fecha_firma_contrato": "15/03/2025", "importe_drc": "1,000,000",
            "moneda_drc": "MXN", "institucion": "IMSS"}
    base.update(kw)
    return base


def fetch(con, cols):
    return con.execute(f"SELECT {cols} FROM contracts").fetchall()


class TestRfcCentury:
    def test_two_digit_years_in_the_past_are_2000s(self, tmp_path):
        con = make_con(tmp_path, [row(rfc="ABC100507XY9")])
        assert fetch(con, "fecha_constitucion_rfc")[0][0].date() == date(2010, 5, 7)

    def test_1990s_rfc(self, tmp_path):
        con = make_con(tmp_path, [row(rfc="ABC990507XY9")])
        assert fetch(con, "fecha_constitucion_rfc")[0][0].date() == date(1999, 5, 7)

    def test_incorporation_date_is_never_in_the_future(self, tmp_path):
        """An RFC year just past the current year must resolve to 19xx, not
        a future 20xx date (the old hardcoded <=26 cutoff broke in 2027)."""
        yy = (date.today().year + 1) % 100
        con = make_con(tmp_path, [row(rfc=f"ABC{yy:02d}0507XY9")])
        got = fetch(con, "fecha_constitucion_rfc")[0][0]
        assert got is not None and got.date() <= date.today()
        assert got.year == 1900 + yy

    def test_current_year_rfc_is_2000s(self, tmp_path):
        yy = date.today().year % 100
        con = make_con(tmp_path, [row(rfc=f"ABC{yy:02d}0101XY9")])
        assert fetch(con, "fecha_constitucion_rfc")[0][0].year == 2000 + yy

    def test_cutoff_tracks_the_clock(self, tmp_path):
        """In 2027, RFC year 27 is a 2027 incorporation (the old hardcoded
        <=26 cutoff would call it 1927), and 28 is still 1928."""
        con = make_con(tmp_path, [row(rfc="ABC270507XY9"), row(rfc="ABC280507XY9")],
                       today=date(2027, 6, 1))
        years = sorted(r[0].year for r in fetch(con, "fecha_constitucion_rfc"))
        assert years == [1928, 2027]


class TestMonedaEfectiva:
    def test_drc_amount_uses_drc_currency(self, tmp_path):
        con = make_con(tmp_path, [row(importe_drc="500,000", moneda_drc="MXN")])
        assert fetch(con, "importe, moneda_efectiva")[0] == (500000.0, "MXN")

    def test_fallback_amount_uses_moneda_column(self, tmp_path):
        """When importe falls back to monto_max_con_imp, the currency must
        come from `moneda`, not the empty moneda_drc — a USD techo contract
        must not be summable as MXN."""
        con = make_con(tmp_path, [row(importe_drc="", moneda_drc="",
                                      monto_max_con_imp="2,000,000", moneda="USD")])
        assert fetch(con, "importe, moneda_efectiva")[0] == (2000000.0, "USD")

    def test_uc_fallback_uses_moneda_column(self, tmp_path):
        con = make_con(tmp_path, [row(importe_drc="", moneda_drc="", monto_max_con_imp="",
                                      monto_max_con_imp_uc="3,000,000", moneda="MXN")])
        assert fetch(con, "importe, moneda_efectiva")[0] == (3000000.0, "MXN")
