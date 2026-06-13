"""Los criterios de d02/d04 viven en funciones importables: el backtest los
importa en vez de re-implementarlos — ajustar un umbral no puede desincronizar
la tabla de precisión publicada."""
from datetime import date

import duckdb
import pytest

from detectors.common import load_views
from detectors.d02_direct_award_concentration import direct_concentration_flags
from detectors.d04_young_winners import young_winner_flags
from tests.fixtures import write_contracts_csv, write_efos_csv


def make_con(tmp_path, rows):
    contracts = write_contracts_csv(tmp_path / "contratos_2024.csv", rows)
    con = duckdb.connect()
    load_views(con, [str(contracts)],
               efos_path=write_efos_csv(tmp_path / "efos.csv", []))
    return con


def contrato(rfc, fecha, importe="1,000,000", tipo="ADJUDICACIÓN DIRECTA"):
    return {"institucion": "I", "nombre_uc": "UC", "proveedor": "P", "rfc": rfc,
            "tipo_procedimiento": tipo, "fecha_firma_contrato": fecha,
            "importe_drc": importe, "moneda_drc": "MXN"}


class TestYoungWinnerFlags:
    def test_young_and_big_is_flagged_at_first_qualifying_contract(self, tmp_path):
        rows = [contrato("AAA230507XY9", "01/03/2024", "6,000,000"),
                contrato("AAA230507XY9", "01/06/2024", "7,000,000")]
        con = make_con(tmp_path, rows)
        df = young_winner_flags(con)
        assert list(df["rfc_norm"]) == ["AAA230507XY9"]
        assert df.iloc[0]["flag_date"] == date(2024, 3, 1)

    def test_old_or_small_not_flagged(self, tmp_path):
        rows = [contrato("BBB100507XY9", "01/03/2024", "6,000,000"),   # vieja
                contrato("CCC230507XY9", "01/03/2024", "1,000,000")]   # chica
        con = make_con(tmp_path, rows)
        assert len(young_winner_flags(con)) == 0


class TestDirectConcentrationFlags:
    def test_tenth_direct_award_is_the_flag_date(self, tmp_path):
        rows = [contrato("DDD101010AB1", f"{d:02d}/01/2024", "3,000,000")
                for d in range(1, 13)]                                  # 12 directas
        con = make_con(tmp_path, rows)
        df = direct_concentration_flags(con)
        assert list(df["rfc_norm"]) == ["DDD101010AB1"]
        assert df.iloc[0]["flag_date"] == date(2024, 1, 10)             # la 10ª

    def test_below_thresholds_not_flagged(self, tmp_path):
        rows = [contrato("EEE101010AB1", f"{d:02d}/01/2024", "3,000,000")
                for d in range(1, 6)]                                   # solo 5
        con = make_con(tmp_path, rows)
        assert len(direct_concentration_flags(con)) == 0
