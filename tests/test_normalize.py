"""One normalization for company names, shared by the realtime (Python) and
historical (DuckDB SQL) tiers. A name must produce the same key in both.
Plus the single shared date parser that replaces the four ad-hoc ones."""
from datetime import date

import duckdb
import pytest

from detectors.common import normalize, parse_fecha, sql_name_norm


@pytest.mark.parametrize("raw,expected", [
    ("2025-01-14", date(2025, 1, 14)),                  # ISO
    ("15/01/2025", date(2025, 1, 15)),                  # gobierno dd/mm/yyyy
    ("15/01/2025 10:30", date(2025, 1, 15)),            # CFE fecha_fallo
    ("2026-06-11T15:02:07.512Z", date(2026, 6, 11)),    # ISO timestamp
    ("2023-02-17T00:00:00", date(2023, 2, 17)),         # portal fecha_inicio
    ("", None), (None, None), ("no es fecha", None), (12345, None),
])
def test_parse_fecha_covers_all_government_formats(raw, expected):
    assert parse_fecha(raw) == expected

CASES = [
    ("Comercializadora Áurea, S.A. de C.V.", "COMERCIALIZADORA AUREA"),
    ("ACME S DE RL DE CV", "ACME"),
    ("ACME, S.A.P.I. DE C.V.", "ACME"),
    ("CONSTRUCTORA DEL NORTE SA DE CV", "CONSTRUCTORA DEL NORTE"),
    ("GRUPO  FÉNIX,   S.C.", "GRUPO FENIX"),
    # suffix tokens are only stripped at the END of the name
    ("SC CONSTRUCCIONES", "SC CONSTRUCCIONES"),
    ("AC INGENIERIA SA DE CV", "AC INGENIERIA"),
    ("", ""),
    (None, ""),
]


@pytest.mark.parametrize("raw,expected", CASES)
def test_normalize_python(raw, expected):
    assert normalize(raw) == expected


def test_sql_normalization_matches_python():
    con = duckdb.connect()
    for raw, expected in CASES:
        if raw is None:
            continue
        got = con.execute(f"SELECT {sql_name_norm('?')}", [raw]).fetchone()[0]
        assert got == normalize(raw) == expected, raw


def test_chi2_sf_df8_matches_known_critical_values():
    """La p del chi-cuadrado (df=8) publicada en el sitio debe coincidir con
    los valores de tabla estándar."""
    from detectors.d03_benford import chi2_sf_df8
    assert chi2_sf_df8(0) == 1.0
    assert abs(chi2_sf_df8(15.507) - 0.05) < 1e-3   # valor crítico clásico
    assert abs(chi2_sf_df8(20.090) - 0.01) < 1e-3
    assert chi2_sf_df8(5) > chi2_sf_df8(10) > chi2_sf_df8(30)  # monótona
