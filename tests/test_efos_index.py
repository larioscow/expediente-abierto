"""Realtime 69-B name index: parsing by column NAME (not position) and
homonym preference (Definitivo first, then most recent definitivo date)."""
from datetime import date

from realtime.efos_index import EfosIndex
from tests.fixtures import write_efos_csv


def build(tmp_path, rows):
    return EfosIndex(write_efos_csv(tmp_path / "efos.csv", rows))


def test_matches_normalized_name(tmp_path):
    idx = build(tmp_path, [
        {"rfc": "AAA101010AB1", "nombre": "Comercializadora Áurea, S.A. de C.V.",
         "situacion": "Definitivo", "pub_dof_definitivos": "01/06/2015"},
    ])
    hit = idx.match("COMERCIALIZADORA AUREA SA DE CV")
    assert hit and hit["rfc"] == "AAA101010AB1" and hit["situacion"] == "Definitivo"
    assert hit["fecha_definitivo"] == date(2015, 6, 1)


def test_definitivo_date_falls_back_to_sat_publication(tmp_path):
    idx = build(tmp_path, [
        {"rfc": "AAA101010AB1", "nombre": "ACME CONSULTORES SA DE CV", "situacion": "Definitivo",
         "pub_sat_definitivos": "15/02/2018"},
    ])
    assert idx.match("ACME CONSULTORES")["fecha_definitivo"] == date(2018, 2, 15)


def test_homonym_prefers_definitivo_over_presunto(tmp_path):
    rows = [
        {"rfc": "AAA101010AB1", "nombre": "ACME CONSULTORES SA DE CV", "situacion": "Presunto"},
        {"rfc": "BBB101010AB1", "nombre": "ACME CONSULTORES, S.C.", "situacion": "Definitivo",
         "pub_dof_definitivos": "01/06/2015"},
    ]
    for order in (rows, rows[::-1]):
        assert build(tmp_path, order).match("ACME CONSULTORES")["situacion"] == "Definitivo"


def test_homonym_definitivos_prefer_most_recent(tmp_path):
    rows = [
        {"rfc": "OLD101010AB1", "nombre": "ACME CONSULTORES SA DE CV", "situacion": "Definitivo",
         "pub_dof_definitivos": "01/06/2015"},
        {"rfc": "NEW101010AB1", "nombre": "ACME CONSULTORES, S.C.", "situacion": "Definitivo",
         "pub_dof_definitivos": "01/06/2020"},
    ]
    for order in (rows, rows[::-1]):
        assert build(tmp_path, order).match("ACME CONSULTORES")["rfc"] == "NEW101010AB1"


def test_skips_invalid_rows(tmp_path):
    idx = build(tmp_path, [
        {"rfc": "SHORT", "nombre": "EMPRESA INVALIDA SA DE CV", "situacion": "Definitivo"},
        {"rfc": "AAA101010AB1", "nombre": "AB", "situacion": "Definitivo"},  # key too short
    ])
    assert idx.match("EMPRESA INVALIDA") is None
    assert idx.match("AB") is None
