"""d06 — collusion screens over winners-only contract data.

Three signals, each a SCREEN requiring human verification:
  rotation  — a small closed group of suppliers splits public-tender wins
              near-evenly inside one unidad compradora
  ring      — winners in the same UC whose RFC incorporation dates cluster
              within days of each other (batch-created shells)
  split     — one supplier, one UC, one day, several direct awards
              (fraccionamiento: slicing to stay under thresholds)
"""
import duckdb
import pytest

from detectors.common import load_views
from detectors.d06_colusion import (incorporation_clusters, rotation_candidates,
                                    same_day_splits)
from tests.fixtures import write_contracts_csv, write_efos_csv


def contract(uc, proveedor, rfc, tipo="LICITACIÓN PÚBLICA", fecha="10/05/2024",
             importe="1,000,000"):
    return {"institucion": "INST X", "nombre_uc": uc, "proveedor": proveedor,
            "rfc": rfc, "tipo_procedimiento": tipo,
            "fecha_firma_contrato": fecha, "importe_drc": importe,
            "moneda_drc": "MXN"}


@pytest.fixture
def con(tmp_path):
    rows = []
    # UC ROTACION: 3 suppliers, 8 public-tender wins each, near-identical money
    for i, (prov, rfc) in enumerate([("ALFA", "AAA180101AA1"),
                                     ("BETA", "BBB170202BB2"),
                                     ("GAMA", "CCC160303CC3")]):
        for k in range(8):
            rows.append(contract("UC ROTACION", prov, rfc,
                                 fecha=f"{(k % 27) + 1:02d}/{(k % 12) + 1:02d}/2024"))
    # UC SANA: 12 suppliers, 2 wins each — open competition
    for i in range(12):
        for k in range(2):
            rows.append(contract("UC SANA", f"PROV{i}", f"DDD10{i:02d}01DD{i % 9}"))
    # UC MONO: one dominant supplier (d02's case, not rotation)
    for k in range(20):
        rows.append(contract("UC MONO", "SOLO", "EEE150505EE5"))
    # UC RING: 3 winners incorporated within 8 days of each other
    rows += [contract("UC RING", "RING1", "FFF240101FF1", tipo="ADJUDICACIÓN DIRECTA"),
             contract("UC RING", "RING2", "GGG240105GG2", tipo="ADJUDICACIÓN DIRECTA"),
             contract("UC RING", "RING3", "HHH240108HH3", tipo="ADJUDICACIÓN DIRECTA")]
    # UC VIEJA: winners incorporated years apart — no cluster
    rows += [contract("UC VIEJA", "OLD1", "III100101II1", tipo="ADJUDICACIÓN DIRECTA"),
             contract("UC VIEJA", "OLD2", "JJJ150505JJ2", tipo="ADJUDICACIÓN DIRECTA"),
             contract("UC VIEJA", "OLD3", "KKK200909KK3", tipo="ADJUDICACIÓN DIRECTA")]
    # UC SPLIT: 4 direct awards, same supplier, same day, 2M each
    for k in range(4):
        rows.append(contract("UC SPLIT", "REBANADA", "LLL120606LL6",
                             tipo="ADJUDICACIÓN DIRECTA", fecha="15/07/2024",
                             importe="2,000,000"))
    # UC DUO: only 2 direct awards same day — below the split threshold
    for k in range(2):
        rows.append(contract("UC DUO", "PAR", "MMM130707MM7",
                             tipo="ADJUDICACIÓN DIRECTA", fecha="15/07/2024",
                             importe="2,000,000"))

    contracts = write_contracts_csv(tmp_path / "contratos_2024.csv", rows)
    efos = write_efos_csv(tmp_path / "efos.csv", [])
    c = duckdb.connect()
    load_views(c, [str(contracts)], efos_path=efos)
    return c


def test_rotation_flags_closed_even_group_only(con):
    df = rotation_candidates(con, min_contracts=12)
    assert list(df["nombre_uc"]) == ["UC ROTACION"]
    r = df.iloc[0]
    assert r["n_proveedores"] == 3 and r["contratos"] == 24
    assert r["evenness"] > 0.95


def test_rotation_ignores_monopoly_and_open_competition(con):
    df = rotation_candidates(con, min_contracts=12)
    assert "UC MONO" not in set(df["nombre_uc"])
    assert "UC SANA" not in set(df["nombre_uc"])


def test_incorporation_cluster_found(con):
    df = incorporation_clusters(con, window_days=30, min_companies=3)
    assert list(df["nombre_uc"]) == ["UC RING"]
    assert df.iloc[0]["empresas"] == 3
    assert df.iloc[0]["dias_entre_constituciones"] <= 8


def test_no_cluster_for_spread_incorporations(con):
    df = incorporation_clusters(con, window_days=30, min_companies=3)
    assert "UC VIEJA" not in set(df["nombre_uc"])


def test_same_day_split_flagged(con):
    df = same_day_splits(con, min_contracts=3, min_total=5_000_000)
    assert list(df["nombre_uc"]) == ["UC SPLIT"]
    r = df.iloc[0]
    assert r["contratos"] == 4 and r["total_mxn"] == 8_000_000


def test_two_same_day_contracts_not_flagged(con):
    df = same_day_splits(con, min_contracts=3, min_total=5_000_000)
    assert "UC DUO" not in set(df["nombre_uc"])
