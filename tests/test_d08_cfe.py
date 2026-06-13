"""d08 — CFE awarded contracts (own open dataset, outside ComprasMX) crossed
against 69-B and SFP by normalized name."""
import csv
import json
from datetime import date

from detectors.d08_cfe import cfe_risk, parse_fecha
from realtime.efos_index import EfosIndex
from realtime.sfp_index import SfpIndex
from tests.fixtures import write_efos_csv

CFE_HEADER = ["numero", "descripcion", "tipo_procedimiento", "tipo_contratacion",
              "fecha_publicacion", "estado_procedimiento",
              "nomb_proveedor_adjudicado", "monto", "fecha_fallo",
              "area_contratante", "area_requirente"]


def write_cfe(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CFE_HEADER)
        w.writeheader()
        w.writerows(rows)
    return path


def cfe_row(prov, fallo="15/01/2025 10:30"):
    return {"numero": "CFE-0001", "descripcion": "x",
            "tipo_procedimiento": "Adjudicación directa",
            "fecha_publicacion": "2025-01-14", "estado_procedimiento": "Adjudicado",
            "nomb_proveedor_adjudicado": prov, "monto": "402616.0",
            "fecha_fallo": fallo, "area_contratante": "Gerencia X"}


def test_parse_fecha_handles_both_formats():
    assert parse_fecha("15/01/2025 10:30") == date(2025, 1, 15)
    assert parse_fecha("2025-01-14") == date(2025, 1, 14)
    assert parse_fecha("") is None


def test_cfe_cross_matches_by_normalized_name(tmp_path):
    cfe = write_cfe(tmp_path / "cfe.csv", [
        cfe_row("Proveedora Fantasma, S.A. de C.V."),
        cfe_row("Empresa Honesta SA de CV"),
    ])
    efos = EfosIndex(write_efos_csv(tmp_path / "efos.csv", [
        {"rfc": "PFA101010AB1", "nombre": "PROVEEDORA FANTASMA SA DE CV",
         "situacion": "Definitivo", "pub_dof_definitivos": "01/06/2015"}]))
    sfp_path = tmp_path / "sfp.json"
    sfp_path.write_text(json.dumps([]))
    df = cfe_risk(cfe, efos, SfpIndex(sfp_path))
    assert list(df["proveedor"]) == ["Proveedora Fantasma, S.A. de C.V."]
    r = df.iloc[0]
    assert r["lista"] == "69-B" and r["rfc"] == "PFA101010AB1"
    assert bool(r["needs_verification"])


def test_cfe_flags_award_during_debarment(tmp_path):
    cfe = write_cfe(tmp_path / "cfe.csv", [cfe_row("Castigada SA de CV")])
    efos = EfosIndex(write_efos_csv(tmp_path / "efos.csv", []))
    sfp_path = tmp_path / "sfp.json"
    sfp_path.write_text(json.dumps([{
        "rfc": "CAS101010AB1", "nombre_razon_social": "CASTIGADA SA DE CV",
        "plazo": {"fecha_inicial": "2024-06-01", "fecha_final": "2025-06-01"}}]))
    df = cfe_risk(cfe, efos, SfpIndex(sfp_path))
    r = df.iloc[0]
    assert r["lista"] == "SFP" and bool(r["durante_inhabilitacion"])
