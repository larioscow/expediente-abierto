"""A supplier can be debarred more than once. Both tiers must check a contract
date against ALL debarment windows, not just the most recent one."""
import json
from datetime import date

import duckdb

from detectors.common import load_sfp_views, load_views
from realtime.sfp_index import SfpIndex
from tests.fixtures import write_contracts_csv, write_efos_csv

TWO_WINDOWS = [
    {"rfc": "AAA101010AB1", "nombre_razon_social": "CONSTRUCTORA FENIX SA DE CV",
     "plazo": {"fecha_inicial": "2015-01-01", "fecha_final": "2016-01-01"}},
    {"rfc": "AAA101010AB1", "nombre_razon_social": "CONSTRUCTORA FENIX SA DE CV",
     "plazo": {"fecha_inicial": "2020-01-01", "fecha_final": "2022-01-01"}},
]


def write_sfp(tmp_path, records=TWO_WINDOWS):
    p = tmp_path / "sfp.json"
    p.write_text(json.dumps(records))
    return p


class TestSfpIndex:
    def test_match_returns_all_windows(self, tmp_path):
        idx = SfpIndex(write_sfp(tmp_path))
        assert len(idx.match_rfc("AAA101010AB1")) == 2
        assert len(idx.match_name("Constructora Fénix, S.A. de C.V.")) == 2
        assert idx.match_rfc("ZZZ000000XX0") == []

    def test_pick_finds_the_earlier_window(self, tmp_path):
        """Contract signed during the FIRST debarment must flag durante,
        even though a later window exists."""
        idx = SfpIndex(write_sfp(tmp_path))
        rec, durante = SfpIndex.pick(idx.match_rfc("AAA101010AB1"), date(2015, 6, 15))
        assert durante and rec["inicio"] == date(2015, 1, 1)

    def test_pick_outside_all_windows(self, tmp_path):
        idx = SfpIndex(write_sfp(tmp_path))
        rec, durante = SfpIndex.pick(idx.match_rfc("AAA101010AB1"), date(2018, 6, 15))
        assert not durante and rec is not None

    def test_multa_only_record_is_never_durante(self, tmp_path):
        """Un registro con fecha_inicial pero sin fecha_final ni plazo es una
        sanción sin ventana de inhabilitación (p. ej. solo multa, caso Médica
        Sur MSU820125T58): jamás debe contar como 'durante'."""
        idx = SfpIndex(write_sfp(tmp_path, [
            {"rfc": "AAA101010AB1", "nombre_razon_social": "CONSTRUCTORA FENIX SA",
             "multa": {"monto": "210300"},
             "plazo": {"fecha_inicial": "2021-01-01"}},
        ]))
        rec, durante = SfpIndex.pick(idx.match_rfc("AAA101010AB1"), date(2025, 1, 1))
        assert not durante and rec is not None
        _, antes = SfpIndex.pick(idx.match_rfc("AAA101010AB1"), date(2020, 1, 1))
        assert not antes


class TestBatchSfpView:
    def make_con(self, tmp_path, contract_rows):
        contracts = write_contracts_csv(tmp_path / "contratos_2025.csv", contract_rows)
        efos = write_efos_csv(tmp_path / "sat_69b.csv", [])
        con = duckdb.connect()
        load_views(con, [str(contracts)], efos_path=efos)
        load_sfp_views(con, sfp_path=write_sfp(tmp_path))
        return con

    def contract(self, fecha):
        return {"rfc": "AAA101010AB1", "proveedor": "CONSTRUCTORA FENIX",
                "fecha_firma_contrato": fecha, "importe_drc": "1,000,000",
                "moneda_drc": "MXN"}

    def test_contract_in_earlier_window_is_durante(self, tmp_path):
        con = self.make_con(tmp_path, [self.contract("15/06/2015")])
        rows = con.execute(
            "SELECT durante_inhabilitacion, inicio FROM sfp_hits").fetchall()
        assert rows == [(True, date(2015, 1, 1))]

    def test_contract_outside_windows_yields_one_row_not_durante(self, tmp_path):
        con = self.make_con(tmp_path, [self.contract("15/06/2018")])
        rows = con.execute("SELECT durante_inhabilitacion FROM sfp_hits").fetchall()
        assert rows == [(False,)]

    def test_multa_only_record_is_never_durante_in_batch(self, tmp_path):
        """Mismo criterio que SfpIndex: sin fecha_final no hay ventana de
        inhabilitación, aunque el contrato sea posterior al inicio."""
        contracts = write_contracts_csv(
            tmp_path / "contratos_2025.csv", [self.contract("15/06/2025")])
        efos = write_efos_csv(tmp_path / "sat_69b.csv", [])
        con = duckdb.connect()
        load_views(con, [str(contracts)], efos_path=efos)
        load_sfp_views(con, sfp_path=write_sfp(tmp_path, [
            {"rfc": "AAA101010AB1", "nombre_razon_social": "CONSTRUCTORA FENIX SA",
             "multa": {"monto": "210300"},
             "plazo": {"fecha_inicial": "2021-01-01"}},
        ]))
        rows = con.execute("SELECT durante_inhabilitacion FROM sfp_hits").fetchall()
        assert rows == [(False,)]


def test_python_and_sql_sfp_parsers_agree(tmp_path):
    """common.load_sfp_views (SQL) y SfpIndex (Python) parsean sfp_sancionados
    por separado: deben producir exactamente las mismas ventanas, incluida la
    variante fecha_fin/fecha_final y registros sin fin."""
    records = [
        {"rfc": "AAA101010AB1", "nombre_razon_social": "UNO SA DE CV",
         "plazo": {"fecha_inicial": "2023-01-05", "fecha_final": "2024-01-05"}},
        {"rfc": "AAA101010AB1", "nombre_razon_social": "UNO SA DE CV",
         "plazo": {"fecha_inicial": "2020-03-01", "fecha_fin": "2021-03-01"}},  # variante
        {"rfc": "BBB101010AB1", "nombre_razon_social": "DOS SA DE CV",
         "plazo": {"fecha_inicial": "2022-07-07"}},                              # sin fin
        {"rfc": "CORTO", "nombre_razon_social": "RFC INVALIDO", "plazo": {}},   # excluido
    ]
    path = write_sfp(tmp_path, records)

    idx = SfpIndex(path)
    py = sorted((r["rfc"], r["inicio"], r["fin"])
                for recs in idx.by_rfc.values() for r in recs
                if len(r["rfc"]) >= 12)

    con = duckdb.connect()
    load_views(con, [str(write_contracts_csv(tmp_path / "contratos_2024.csv", []))],
               efos_path=write_efos_csv(tmp_path / "efos.csv", []))
    load_sfp_views(con, sfp_path=path)
    sql = sorted((r[0], r[1], r[2]) for r in
                 con.execute("SELECT rfc_norm, inicio, fin FROM sfp").fetchall())

    assert py == sql and len(py) == 3
