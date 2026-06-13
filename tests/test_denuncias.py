"""Denuncia drafts: each document must carry the facts (RFC, dates, amounts),
the precise legal hook, the evidence chain, and prudent request-language —
solicita investigación, never asserts guilt."""
import pandas as pd

from casework.denuncias import (denuncia_asf_convenios, denuncia_cna_rotacion,
                                denuncia_efos_post_definitivo,
                                denuncia_inhabilitado,
                                denuncia_inhabilitado_estatal, build_all)

MANIFEST = {
    "sfp_sancionados.json": {"retrieved_at": "2026-06-11", "sha256": "aa11"},
    "contratos_2023.csv": {"retrieved_at": "2026-06-11", "sha256": "bb22"},
    "contratos_2024.csv": {"retrieved_at": "2026-06-11", "sha256": "cc33"},
    "contratos_2025.csv": {"retrieved_at": "2026-06-11", "sha256": "dd44"},
}

CASO = {"proveedor": "CONSTRUCTORA X SA DE CV", "rfc": "CXC070122P44",
        "inhabilitado_desde": "2023-05-04", "hasta": "2024-05-03",
        "fecha_contrato": "2023-09-11", "institucion": "SICT",
        "tipo_procedimiento": "INVITACIÓN A CUANDO MENOS 3 PERSONAS",
        "importe": 9985448.58, "monto_mxn_millones": 9.99,
        "direccion_anuncio": "https://x.mx/p/1"}


def test_denuncia_inhabilitado_contains_facts_law_and_evidence():
    md = denuncia_inhabilitado(CASO, MANIFEST)
    for needle in ["CXC070122P44", "2023-05-04", "2023-09-11", "SICT",
                   "artículo 59", "Ley General de Responsabilidades",
                   "artículo 50", "LAASSP", "aa11",
                   "no constituye una acusación"]:
        assert needle in md, needle


def test_denuncia_links_to_live_portal_domain():
    caso = dict(CASO, direccion_anuncio=(
        "https://upcp-compranet.funcionpublica.gob.mx/sitiopublico/#/"
        "sitiopublico/detalle/8a8bd18d1d6b47bda970f21c4df78a57/procedimiento"))
    md = denuncia_inhabilitado(caso, MANIFEST)
    assert "buengobierno.gob.mx" in md
    assert "funcionpublica.gob.mx" not in md


def test_denuncia_carries_no_meta_chrome():
    """The filed document states facts — no tooling talk, no filing
    instructions, no branding."""
    md = denuncia_inhabilitado(CASO, MANIFEST, verificado="2026-06-11")
    for slop in ["generado automáticamente", "Presentar en", "SIDEC",
                 "pipeline", "código abierto", "EXPEDIENTE ABIERTO"]:
        assert slop not in md, slop


def test_denuncia_states_exact_amount_when_available():
    md = denuncia_inhabilitado(CASO, MANIFEST)
    assert "$9,985,448.58 MXN" in md          # cantidad exacta, no "9.99M"
    sin_importe = {k: v for k, v in CASO.items() if k != "importe"}
    assert "$9.99M MXN" in denuncia_inhabilitado(sin_importe, MANIFEST)


def test_verified_case_is_not_a_draft():
    """Once a human verified the case against the live portal, the filed
    document must not call itself borrador — but it keeps the prudent
    no-accusation language."""
    md = denuncia_inhabilitado(CASO, MANIFEST, verificado="2026-06-11")
    assert md.startswith("# Denuncia —")
    assert "orrador" not in md
    assert "verificados el 2026-06-11" in md
    assert "no constituye una acusación" in md
    # default remains a draft
    assert denuncia_inhabilitado(CASO, MANIFEST).startswith("# Borrador")


def test_denuncia_asf_cites_caps_and_totals():
    df = pd.DataFrame([{
        "proveedor": "VITAL SA", "institucion": "ISSSTE", "rfc": "VIT900101AA1",
        "pct_incremento": 27.6, "tope_legal_pct": 20.0,
        "monto_original": 1_000_000.0, "monto_ultimo_convenio": 1_276_000.0,
        "fecha_contrato": "2024-01-09", "ley": "LAASSP"}])
    md = denuncia_asf_convenios(df, MANIFEST)
    for needle in ["Auditoría Superior de la Federación", "artículo 52",
                   "LAASSP", "VITAL SA", "27.6", "1 caso",
                   "f07_convenios_inflados.csv", "no constituye una acusación"]:
        assert needle in md, needle


def test_denuncia_cna_cites_lfce():
    df = pd.DataFrame([{
        "institucion": "CAMARGO", "nombre_uc": "OBRAS PUBLICAS",
        "contratos": 14, "n_proveedores": 3, "evenness": 0.966,
        "anios_activos": 2, "monto_mxn_millones": 24.0,
        "proveedores": "A (6) | B (5) | C (3)"}])
    md = denuncia_cna_rotacion(df, MANIFEST)
    for needle in ["Comisión Nacional Antimonopolio", "artículo 53",
                   "CAMARGO", "0.966", "no constituye una acusación"]:
        assert needle in md, needle


GRUPO_ESTATAL = {
    "proveedor": "PROVEEDORA ESTATAL SA DE CV", "rfc": "PES010101AA1",
    "institucion": "VER - Ayuntamiento de Nanchital", "estado": "VERACRUZ",
    "inhabilitado_desde": "2024-03-30", "hasta": "2024-06-30", "rfc_valido": True,
    "contratos": [{"fecha": "2024-05-24", "importe": 500000.0,
                   "url": "https://veracruz.gob.mx/fallo/123"}]}

GRUPO_EFOS = {
    "proveedor": "FACTURERA FANTASMA SA DE CV", "rfc": "FAF010101AA1",
    "institucion": "INSTITUTO MEXICANO DEL SEGURO SOCIAL", "estado": None,
    "definitivo_dof": "2024-01-15",
    "contratos": [{"fecha": "2024-06-01", "importe": 2000000.0,
                   "institucion": "INSTITUTO MEXICANO DEL SEGURO SOCIAL",
                   "url": "https://x.mx/detalle/" + "a" * 32 + "/p"}]}


def test_denuncia_inhabilitado_estatal_routes_to_state_oic():
    md = denuncia_inhabilitado_estatal(GRUPO_ESTATAL, MANIFEST)
    for needle in ["PES010101AA1", "2024-03-30", "2024-05-24", "VERACRUZ",
                   "VER - Ayuntamiento de Nanchital",
                   "Contraloría del Estado de VERACRUZ", "artículo 59",
                   "Plataforma Nacional de Transparencia", "$500,000.00 MXN",
                   "no constituye una acusación"]:
        assert needle in md, needle
    # no se enruta al SIDEC federal
    assert "SIDEC" not in md
    assert md.startswith("# Borrador")
    assert denuncia_inhabilitado_estatal(
        GRUPO_ESTATAL, MANIFEST, verificado="2026-06-13").startswith("# Denuncia")


def test_denuncia_inhabilitado_estatal_flags_invalid_rfc():
    g = dict(GRUPO_ESTATAL, rfc_valido=False)
    md = denuncia_inhabilitado_estatal(g, MANIFEST)
    assert "debe cotejarse" in md


def test_denuncia_efos_cites_69b_and_fgr():
    md = denuncia_efos_post_definitivo(GRUPO_EFOS, MANIFEST)
    for needle in ["FAF010101AA1", "2024-01-15", "artículo 69-B",
                   "113-bis", "Servicio de Administración Tributaria",
                   "Fiscalía General de la República", "$2,000,000.00 MXN",
                   "no constituye una acusación"]:
        assert needle in md, needle


def test_denuncia_efos_estatal_adds_state_oic_copy():
    g = dict(GRUPO_EFOS, estado="JALISCO",
             institucion="JAL - Secretaria de Administracion")
    md = denuncia_efos_post_definitivo(g, MANIFEST)
    assert "Contraloría del Estado de JALISCO" in md
    assert "Fiscalía General de la República" in md


def test_build_all_writes_files(tmp_path):
    f = tmp_path / "findings"
    f.mkdir()
    pd.DataFrame([CASO]).to_csv(f / "f05_durante_inhabilitacion.csv", index=False)
    paths = build_all(findings_dir=f, out_dir=tmp_path / "out", manifest=MANIFEST)
    assert paths and all(p.exists() for p in paths)
    assert any("inhabilitado" in p.name for p in paths)
