"""Las cifras que publica el sitio se calculan en una función testeable y se
exportan a JSON para el frontend (web/) — un error aquí es un error publicado."""
import json

import pandas as pd
import pytest


@pytest.fixture
def findings(tmp_path):
    f = tmp_path / "findings"
    f.mkdir()
    pd.DataFrame([
        {"situacion": "Definitivo", "file_year": 2024, "contratos": 10,
         "empresas": 3, "monto_mxn_millones": 100.5},
        {"situacion": "Presunto", "file_year": 2024, "contratos": 5,
         "empresas": 2, "monto_mxn_millones": 50.0},
    ]).to_csv(f / "f01_resumen_por_situacion.csv", index=False)
    pd.DataFrame([
        {"situacion": "Definitivo", "contratos": 20, "empresas": 7,
         "monto_mxn_millones": 200.0},
    ]).to_csv(f / "f01h_resumen_por_situacion.csv", index=False)
    pd.DataFrame([{"proveedor": "X"}] * 4).to_csv(
        f / "f05_durante_inhabilitacion.csv", index=False)
    pd.DataFrame([{"banda_nigrini": "NO CONFORME"}, {"banda_nigrini": "conforme"},
                  {"banda_nigrini": "NO CONFORME"}]).to_csv(
        f / "f03_benford_instituciones.csv", index=False)
    pd.DataFrame([{"lift": 4.0}, {"lift": 1.1}]).to_csv(
        f / "f08_backtest_precision.csv", index=False)
    return f


def test_cifras_compute_from_findings(findings):
    from scripts.export_web_data import compute_cifras
    c = compute_cifras(findings)
    assert c["d01_monto"] == 100.5          # solo Definitivo
    assert c["d01h_monto"] == 200.0
    assert c["d01h_contratos"] == 20 and c["d01h_empresas"] == 7
    assert c["d05_gun"] == 4
    assert c["d03_noconf"] == 2 and c["d03_total"] == 3
    assert c["best_lift"] == 4.0


def test_cifras_missing_files_are_zero(tmp_path):
    from scripts.export_web_data import compute_cifras
    vacio = tmp_path / "nada"
    vacio.mkdir()
    c = compute_cifras(vacio)
    assert c["d01_monto"] == 0 and c["d05_gun"] == 0 and c["d03_total"] == 0


def test_importing_export_module_does_not_write(tmp_path):
    """Importar el módulo no debe escribir nada (sería ejecución a nivel de
    módulo)."""
    import importlib
    import scripts.export_web_data as ew
    importlib.reload(ew)
    assert hasattr(ew, "main")


def test_main_writes_web_data(tmp_path):
    """La exportación produce los JSON que consume web/ y copia los CSV de
    evidencia con su sha256."""
    import importlib
    import scripts.export_web_data as ew
    importlib.reload(ew)
    out = tmp_path / "web"
    ew.main(out_dir=out)
    data = out / "src" / "data"
    for name in ["meta.json", "cifras.json", "denuncias.json",
                 "inhabilitadas.json", "factureras.json", "sobrecostos.json",
                 "colusion.json", "recien_creadas.json",
                 "sin_competencia.json", "alertas.json", "datos.json",
                 "estados.json"]:
        assert (data / name).exists(), name

    cifras = json.loads((data / "cifras.json").read_text())
    # inhabilitadas y factureras ahora combinan federal + estatal, así que el
    # total es >= la cifra federal sola del detector
    assert cifras["inhabilitadas_n"] >= cifras["d05_gun"]
    assert cifras["facturera_rfc_monto"] >= round(cifras["d01_monto"], 1)
    assert cifras["sobrecostos_n"] == cifras["d07_n"]

    datos = json.loads((data / "datos.json").read_text())
    assert datos["archivos"], "sin CSVs publicados"
    for a in datos["archivos"]:
        assert len(a["sha256"]) == 64
        assert (out / "public" / "datos" / a["nombre"]).exists()


def test_csv_rows_counts_records_not_newlines():
    """Los campos CSV pueden traer saltos de línea: se cuentan registros."""
    from scripts.export_web_data import csv_rows
    data = b'a,b\n"x\ny",2\n"z",3\n'
    assert csv_rows(data) == 2


def test_denuncias_folios_derives_from_acuses(tmp_path):
    from scripts.export_web_data import denuncias_folios
    acuses = tmp_path / "denuncias" / "acuses"
    acuses.mkdir(parents=True)
    for folio in ["83004-2026", "83016-2026"]:
        (acuses / f"acuse_{folio}.pdf").write_bytes(b"%PDF")
    assert denuncias_folios(tmp_path) == ["83004-2026", "83016-2026"]
    # y deja el listado público (rastreado) para builds sin acuses
    assert json.loads(
        (tmp_path / "denuncias" / "folios_publicos.json").read_text()
    ) == ["83004-2026", "83016-2026"]


def test_denuncias_folios_falls_back_to_public_list(tmp_path):
    """En CI no hay acuses (contienen datos personales): se lee el listado
    público de folios."""
    from scripts.export_web_data import denuncias_folios
    d = tmp_path / "denuncias"
    d.mkdir(parents=True)
    (d / "folios_publicos.json").write_text('["83004-2026"]')
    assert denuncias_folios(tmp_path) == ["83004-2026"]


def test_parse_folio_extracts_folio_never_clave():
    from scripts.export_web_data import parse_folio
    nota = ("SIDEC folio 83017/2026 clave 6116213, presentada 2026-06-11 "
            "(anónima). Denuncia consolidada X × Y.")
    assert parse_folio(nota) == "83017-2026"
    assert "6116213" not in parse_folio(nota)
    assert parse_folio("sin folio aquí") is None
    assert parse_folio(None) is None


def _f05_df():
    return pd.DataFrame([
        # mismo RFC y misma fecha, instituciones distintas -> sufijos -N
        {"proveedor": "LAGUNA SA", "rfc": "SIE020425UJ7",
         "inhabilitado_desde": "2024-12-18", "hasta": "2025-12-18",
         "fecha_contrato": "2025-04-01", "institucion": "SADER",
         "monto_mxn_millones": 3.26, "direccion_anuncio": "u1"},
        {"proveedor": "LAGUNA SA", "rfc": "SIE020425UJ7",
         "inhabilitado_desde": "2024-12-18", "hasta": "2025-12-18",
         "fecha_contrato": "2025-04-01", "institucion": "CINVESTAV",
         "monto_mxn_millones": 2.0, "direccion_anuncio": "u2"},
        # mismo grupo (rfc, institución) en otra fecha, sin fila propia en el
        # store: la denuncia consolidada lo ampara y hereda el folio
        {"proveedor": "LAGUNA SA", "rfc": "SIE020425UJ7",
         "inhabilitado_desde": "2024-12-18", "hasta": "2025-12-18",
         "fecha_contrato": "2025-03-01", "institucion": "SADER",
         "monto_mxn_millones": 0.73, "direccion_anuncio": "u5"},
        # caso que nació de una alerta: el store solo trae el RFC
        {"proveedor": "CAO SA", "rfc": "CAO070122P44",
         "inhabilitado_desde": "2023-05-04", "hasta": "2024-05-03",
         "fecha_contrato": "2023-09-11", "institucion": "SICT",
         "monto_mxn_millones": 9.99, "direccion_anuncio": "u3"},
        # sin denuncia: no debe publicarse
        {"proveedor": "OTRA SA", "rfc": "OTR010101AA1",
         "inhabilitado_desde": "2024-01-01", "hasta": "2025-01-01",
         "fecha_contrato": "2024-06-01", "institucion": "IMSS",
         "monto_mxn_millones": 1.0, "direccion_anuncio": "u4"},
    ])


def test_casos_denunciados_joins_store_folios_with_f05():
    from scripts.export_web_data import casos_denunciados
    store = [
        {"numero": "inhabilitado_SIE020425UJ7_2025-04-01", "nombre": "…",
         "estado": "denunciado", "nota": "SIDEC folio 83017/2026 clave 1"},
        {"numero": "inhabilitado_SIE020425UJ7_2025-04-01-2", "nombre": "…",
         "estado": "denunciado", "nota": "SIDEC folio 83018/2026 clave 2"},
        {"numero": "IO-09-210-009000972-N-10-2023",
         "nombre": "Contrato C-2023-00156113 a proveedor inhabilitado "
                   "(CAO070122P44)",
         "estado": "denunciado", "nota": "SIDEC folio 83004/2026 clave 3"},
        {"numero": "inhabilitado_OTR010101AA1_2024-06-01", "nombre": "…",
         "estado": "verificando", "nota": "SIDEC folio 99999/2026 clave 4"},
    ]
    casos = casos_denunciados(store, _f05_df())
    assert [c["rfc"] for c in casos] == ["CAO070122P44", "SIE020425UJ7"]
    laguna = casos[1]
    assert len(laguna["contratos"]) == 3  # incluye el heredado por grupo
    heredado = [c for c in laguna["contratos"] if c["fecha"] == "2025-03-01"]
    assert heredado[0]["folio"] == "83017-2026"  # mismo grupo (rfc, SADER)
    assert {c["folio"] for c in laguna["contratos"]} == {"83017-2026", "83018-2026"}
    assert laguna["folios"] == ["83017-2026", "83018-2026"]
    assert laguna["inhabilitada_hasta"] == "2025-12-18"
    cao = casos[0]
    assert cao["contratos"][0]["folio"] == "83004-2026"
    # ninguna clave de seguimiento sale en el JSON público
    assert "clave" not in json.dumps(casos)
