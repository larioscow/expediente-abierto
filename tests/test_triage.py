"""Triaje: identidad estable, cotejo contra lo ya presentado, libro de vistos
(nuevo/cambiado), cuarentena de evidencia incompleta, y el estado humano que
scan jamás pisa."""
import json
from datetime import date

import pandas as pd

from casework import triage
from casework.triage import (TriageStore, case_id, iter_candidatos,
                             load_filed_index, scan)

HOY = date(2026, 6, 13)


def _f05(rows):
    cols = ["proveedor", "rfc", "inhabilitado_desde", "hasta", "fecha_contrato",
            "institucion", "orden_gobierno", "estado_comprador",
            "tipo_procedimiento", "importe", "monto_mxn_millones",
            "direccion_anuncio"]
    return pd.DataFrame([{c: r.get(c, "") for c in cols} for r in rows])


def _f10_inhab(rows):
    cols = ["estado_comprador", "sujeto_obligado", "proveedor", "rfc_norm",
            "fecha_efectiva", "importe", "inicio", "fin",
            "durante_inhabilitacion", "rfc_valido", "nombre_sfp",
            "institucion_sancionadora", "expediente", "url_fallo",
            "direccion_anuncio"]
    return pd.DataFrame([{c: r.get(c, "") for c in cols} for r in rows])


def _f10_efos(rows):
    cols = ["estado_comprador", "sujeto_obligado", "proveedor", "rfc",
            "situacion", "definitivo_dof", "fecha_contrato",
            "firmado_despues_definitivo", "importe", "monto_mxn_millones",
            "importe_plausible", "direccion_anuncio"]
    return pd.DataFrame([{c: r.get(c, "") for c in cols} for r in rows])


def _findings(tmp_path, **frames):
    f = tmp_path / "findings"
    f.mkdir(exist_ok=True)
    for name, df in frames.items():
        df.to_csv(f / name, index=False)
    return f


def _denuncias(tmp_path, publicas=None, folios=None):
    d = tmp_path / "denuncias"
    d.mkdir(exist_ok=True)
    (d / "denuncias_publicas.json").write_text(
        json.dumps(publicas or []), encoding="utf-8")
    (d / "folios_publicos.json").write_text(
        json.dumps(folios or []), encoding="utf-8")
    return d


def test_case_id_is_stable_and_normalized():
    a = case_id("est", "inhabilitado", "VERACRUZ", "Sec. de Salud", "ABC010101AA1")
    b = case_id("est", "inhabilitado", "veracruz", "SEC.  DE SALUD", "abc010101aa1")
    assert a == b and len(a) == 32


def test_state_debarment_groups_and_scores(tmp_path):
    f = _findings(tmp_path, **{"f10_inhabilitados_estatal.csv": _f10_inhab([
        # dos contratos del mismo proveedor/sujeto -> un solo caso
        {"estado_comprador": "VERACRUZ", "sujeto_obligado": "VER - Salud",
         "proveedor": "PROV X", "rfc_norm": "PXX010101AA1",
         "fecha_efectiva": "2025-03-10", "importe": 500000, "inicio": "2025-01-01",
         "fin": "2025-12-31", "durante_inhabilitacion": True, "rfc_valido": True},
        {"estado_comprador": "VERACRUZ", "sujeto_obligado": "VER - Salud",
         "proveedor": "PROV X", "rfc_norm": "PXX010101AA1",
         "fecha_efectiva": "2025-04-10", "importe": 300000, "inicio": "2025-01-01",
         "fin": "2025-12-31", "durante_inhabilitacion": True, "rfc_valido": True},
    ])})
    d = _denuncias(tmp_path)
    cands = iter_candidatos(f, d, hoy=HOY)
    assert len(cands) == 1
    c = cands[0]
    assert c.ambito == "estatal" and c.pattern == "inhabilitado"
    assert c.n_contratos == 2 and c.monto == 800000
    assert c.tier == "T1" and not c.cuarentena and not c.already_filed
    assert c.gates["ventana_ok"] and c.gates["rfc_valido"]
    assert c.recomendacion == "revisar" and c.score > 0


def test_already_filed_is_suppressed(tmp_path):
    f = _findings(tmp_path, **{"f05_durante_inhabilitacion.csv": _f05([
        {"proveedor": "CONSTRUCTORA X", "rfc": "CXC070122P44",
         "inhabilitado_desde": "2023-05-04", "hasta": "2024-05-03",
         "fecha_contrato": "2023-09-11", "institucion": "SICT",
         "orden_gobierno": "APF", "importe": 9985448.58,
         "direccion_anuncio": "https://x.mx/detalle/" + "a" * 32 + "/proc"},
    ])})
    d = _denuncias(tmp_path, publicas=[{
        "rfc": "CXC070122P44", "contratos": [
            {"institucion": "SICT",
             "url": "https://x.mx/detalle/" + "a" * 32 + "/proc"}]}])
    c = iter_candidatos(f, d, hoy=HOY)[0]
    assert c.already_filed and c.recomendacion == "suppress"
    rep = scan(f, d, db=tmp_path / "t.duckdb", hoy=HOY)
    assert rep["suprimidos"] == 1 and rep["nuevos"] == 0 and rep["emitidos"] == []


def test_future_dated_state_efos_is_quarantined(tmp_path):
    f = _findings(tmp_path, **{"f10_efos_estatal.csv": _f10_efos([
        {"estado_comprador": "BAJA CALIFORNIA", "sujeto_obligado": "BCN - X",
         "proveedor": "ARCH", "rfc": "AET201113369", "situacion": "Definitivo",
         "definitivo_dof": "2026-04-24", "fecha_contrato": "2026-10-20",
         "firmado_despues_definitivo": True, "importe": 74240,
         "importe_plausible": True},
    ])})
    d = _denuncias(tmp_path)
    c = iter_candidatos(f, d, hoy=HOY)[0]
    assert "no_futura" in c.cuarentena and c.recomendacion == "cuarentena"


def test_seen_ledger_new_then_idempotent(tmp_path):
    f = _findings(tmp_path, **{"f10_inhabilitados_estatal.csv": _f10_inhab([
        {"estado_comprador": "SONORA", "sujeto_obligado": "SON - Obras",
         "proveedor": "P", "rfc_norm": "PPP010101AA1",
         "fecha_efectiva": "2025-05-01", "importe": 1000000,
         "inicio": "2025-01-01", "fin": "2025-12-31",
         "durante_inhabilitacion": True, "rfc_valido": True}])})
    d = _denuncias(tmp_path)
    db = tmp_path / "t.duckdb"
    r1 = scan(f, d, db=db, hoy=HOY)
    assert r1["nuevos"] == 1 and len(r1["emitidos"]) == 1
    r2 = scan(f, d, db=db, hoy=HOY)
    assert r2["nuevos"] == 0 and r2["cambiados"] == 0 and r2["emitidos"] == []


def test_changed_evidence_resurfaces(tmp_path):
    base = {"estado_comprador": "SONORA", "sujeto_obligado": "SON - Obras",
            "proveedor": "P", "rfc_norm": "PPP010101AA1",
            "fecha_efectiva": "2025-05-01", "importe": 1000000,
            "inicio": "2025-01-01", "fin": "2025-12-31",
            "durante_inhabilitacion": True, "rfc_valido": True}
    db = tmp_path / "t.duckdb"
    d = _denuncias(tmp_path)
    f = _findings(tmp_path, **{"f10_inhabilitados_estatal.csv": _f10_inhab([base])})
    scan(f, d, db=db, hoy=HOY)
    # un segundo contrato cambia monto y n -> el hash cambia, el caso resurge
    f = _findings(tmp_path, **{"f10_inhabilitados_estatal.csv": _f10_inhab([
        base, dict(base, fecha_efectiva="2025-06-01", importe=250000)])})
    r = scan(f, d, db=db, hoy=HOY)
    assert r["cambiados"] == 1 and len(r["emitidos"]) == 1


def test_scan_never_clobbers_human_estado(tmp_path):
    f = _findings(tmp_path, **{"f10_inhabilitados_estatal.csv": _f10_inhab([
        {"estado_comprador": "JALISCO", "sujeto_obligado": "JAL - X",
         "proveedor": "P", "rfc_norm": "PPP010101AA1",
         "fecha_efectiva": "2025-05-01", "importe": 1000000,
         "inicio": "2025-01-01", "fin": "2025-12-31",
         "durante_inhabilitacion": True, "rfc_valido": True}])})
    d = _denuncias(tmp_path)
    db = tmp_path / "t.duckdb"
    rep = scan(f, d, db=db, hoy=HOY)
    cid = rep["emitidos"][0].case_id
    store = TriageStore(db)
    store.set_estado(cid, "verificado", "revisé el portal", folio="99999-2026")
    scan(f, d, db=db, hoy=HOY)               # re-scan no debe pisar el estado
    row = TriageStore(db).get(cid)
    assert row["estado"] == "verificado" and row["folio"] == "99999-2026"


def test_filed_index_matches_by_pair_and_uuid(tmp_path):
    d = _denuncias(tmp_path, publicas=[{
        "rfc": "AAA010101AA1", "contratos": [
            {"institucion": "IMSS",
             "url": "https://x/detalle/" + "b" * 32 + "/p"}]}])
    idx = load_filed_index(d)
    assert ("AAA010101AA1", "IMSS") in idx.pares
    assert ("b" * 32) in idx.uuids


def test_generar_borrador_estatal_desde_libro(tmp_path):
    f = _findings(tmp_path, **{"f10_inhabilitados_estatal.csv": _f10_inhab([
        {"estado_comprador": "VERACRUZ", "sujeto_obligado": "VER - Salud",
         "proveedor": "PROV X SA DE CV", "rfc_norm": "PXX010101AA1",
         "fecha_efectiva": "2025-03-10", "importe": 500000, "inicio": "2025-01-01",
         "fin": "2025-12-31", "durante_inhabilitacion": True, "rfc_valido": True,
         "url_fallo": "https://veracruz.gob.mx/fallo/1"}])})
    d = _denuncias(tmp_path)
    db = tmp_path / "t.duckdb"
    rep = scan(f, d, db=db, hoy=HOY)
    cid = rep["emitidos"][0].case_id
    p = triage.generar(cid, out_dir=tmp_path / "out", render_pdf=False, db=db)
    assert p.exists()
    md = p.read_text()
    assert "PXX010101AA1" in md and "VERACRUZ" in md
    assert md.startswith("# Borrador")           # estado 'nuevo' -> borrador
    # tras verificar, el documento sale presentable
    TriageStore(db).set_estado(cid, "verificado", "ok")
    p2 = triage.generar(cid, out_dir=tmp_path / "out", render_pdf=False, db=db)
    assert p2.read_text().startswith("# Denuncia")


def test_real_findings_scan_is_idempotent(tmp_path):
    """Contra los hallazgos reales del repo: corre dos veces y la segunda no
    reporta nada nuevo ni cambiado (determinismo)."""
    db = tmp_path / "real.duckdb"
    r1 = scan(triage.FINDINGS, triage.DENUNCIAS, db=db, hoy=HOY)
    r2 = scan(triage.FINDINGS, triage.DENUNCIAS, db=db, hoy=HOY)
    assert r1["scanned"] > 0
    assert r2["nuevos"] == 0 and r2["cambiados"] == 0
    # los 20 renglones federales de f05 ya están presentados -> 0 nuevos federales
    fed_inhab = [c for c in r1["emitidos"]
                 if c.pattern == "inhabilitado" and c.ambito == "federal"]
    assert fed_inhab == []
