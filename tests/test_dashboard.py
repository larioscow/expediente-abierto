"""Dashboard sobre la tabla `triage`: lista todos los casos (federal + estados,
todos los tiers) con su estado humano persistente, y el guardado de estado que
el scan jamás pisa."""
from datetime import date

import pandas as pd

from casework.dashboard import casos_triage, render, render_caso
from casework.triage import TriageStore, scan

HOY = date(2026, 6, 13)


def _state_findings(tmp_path):
    f = tmp_path / "findings"
    f.mkdir(exist_ok=True)
    cols = ["estado_comprador", "sujeto_obligado", "proveedor", "rfc_norm",
            "fecha_efectiva", "importe", "inicio", "fin",
            "durante_inhabilitacion", "rfc_valido"]
    pd.DataFrame([
        {"estado_comprador": "JALISCO", "sujeto_obligado": "JAL - Admin",
         "proveedor": "MAXI SERVICIOS DE MEXICO SA DE CV",
         "rfc_norm": "MSM0705117N6", "fecha_efectiva": "2025-12-19",
         "importe": 37404049.2, "inicio": "2025-09-13", "fin": "2026-10-13",
         "durante_inhabilitacion": True, "rfc_valido": True},
    ], columns=cols).to_csv(f / "f10_inhabilitados_estatal.csv", index=False)
    return f


def _denuncias(tmp_path):
    d = tmp_path / "denuncias"
    d.mkdir(exist_ok=True)
    (d / "denuncias_publicas.json").write_text("[]")
    (d / "folios_publicos.json").write_text("[]")
    return d


def _scan(tmp_path):
    db = tmp_path / "cases.duckdb"
    scan(_state_findings(tmp_path), _denuncias(tmp_path), db=db, hoy=HOY)
    return db


def test_dashboard_lists_state_cases_with_tier_and_authority(tmp_path):
    db = _scan(tmp_path)
    casos = casos_triage(db=db)
    assert len(casos) == 1
    c = casos[0]
    assert c["tier"] == "T1" and c["ambito"] == "estatal"
    assert c["estado_geo"] == "JALISCO" and c["rfc"] == "MSM0705117N6"
    assert "Contraloría" in c["autoridad"] and c["estado"] == "nuevo"
    assert c["puede_generar"] is True


def test_estado_persists_and_scan_does_not_clobber(tmp_path):
    db = _scan(tmp_path)
    cid = casos_triage(db=db)[0]["id"]
    TriageStore(db).set_estado(cid, "denunciado", "folio 90001-2026")
    # re-scan: el estado humano debe sobrevivir
    scan(_state_findings(tmp_path), _denuncias(tmp_path), db=db, hoy=HOY)
    c = next(x for x in casos_triage(db=db) if x["id"] == cid)
    assert c["estado"] == "denunciado" and "90001" in c["nota"]


def test_render_has_one_global_sidec_link(tmp_path):
    db = _scan(tmp_path)
    html = render(casos_triage(db=db))
    assert html.count("denuncias.gob.mx/SidecGobMX/#!/busqueda") == 1
    assert "MAXI SERVICIOS" in html and "T1" in html


def test_render_caso_shows_footprint(tmp_path):
    db = _scan(tmp_path)
    findings = tmp_path / "findings"
    cid = casos_triage(db=db)[0]["id"]
    html = render_caso(cid, db=db, findings_dir=findings)
    assert "MAXI SERVICIOS" in html and "MSM0705117N6" in html
    assert "Huella" in html or "huella" in html


def test_empty_book_renders_hint(tmp_path):
    db = tmp_path / "empty.duckdb"
    TriageStore(db)  # crea esquema vacío
    html = render(casos_triage(db=db))
    assert "scan" in html


def test_origin_guard_blocks_cross_site_posts():
    from casework.dashboard import origen_permitido
    assert origen_permitido({"Host": "localhost:8765"})
    assert origen_permitido({"Host": "127.0.0.1:8765",
                             "Origin": "http://127.0.0.1:8765"})
    assert not origen_permitido({"Host": "localhost:8765",
                                 "Origin": "https://evil.example"})
    assert not origen_permitido({"Host": "evil.example"})
    assert not origen_permitido({})
