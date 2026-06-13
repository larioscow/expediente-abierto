"""Una denuncia por proveedor × institución, listando todos los contratos
firmados durante la inhabilitación ante esa misma dependencia."""
from casework.denuncias import denuncia_inhabilitado_multi, build_inhabilitado

MANIFEST = {"sfp_sancionados.json": {"retrieved_at": "2026-06-11", "sha256": "aa"},
            "contratos_2025.csv": {"retrieved_at": "2026-06-11", "sha256": "bb"}}

GRUPO = {
    "proveedor": "SERVICIOS INDUSTRIALES SA DE CV", "rfc": "SIE020425UJ7",
    "institucion": "COMISION NACIONAL DEL AGUA",
    "inhabilitado_desde": "2024-12-18", "hasta": "2025-12-18",
    "contratos": [
        {"fecha_contrato": "2025-04-01", "importe": 3262500.0,
         "tipo_procedimiento": "ADJUDICACIÓN DIRECTA",
         "direccion_anuncio": "https://x.mx/detalle/" + "a"*32 + "/p"},
        {"fecha_contrato": "2025-06-04", "importe": 764620.0,
         "tipo_procedimiento": "ADJUDICACIÓN DIRECTA",
         "direccion_anuncio": "https://x.mx/detalle/" + "b"*32 + "/p"},
    ],
}


def test_nan_importe_never_prints_nan():
    """Un importe NaN no debe colarse como '$nan MXN' en un documento legal."""
    g = dict(GRUPO, contratos=[
        {"fecha_contrato": "2025-04-01", "importe": float("nan"),
         "tipo_procedimiento": "AD", "direccion_anuncio": ""},
        {"fecha_contrato": "2025-05-01", "importe": 100.0,
         "tipo_procedimiento": "AD", "direccion_anuncio": ""},
    ])
    md = denuncia_inhabilitado_multi(g, MANIFEST)
    assert "nan" not in md.lower().replace("financ", "")  # sin $nan
    assert "$100.00" in md


def test_nan_hasta_prints_open_window():
    """Inhabilitación sin fecha de fin (hasta=NaN en el CSV) no debe imprimir
    'al nan' — debe decir que no hay término registrado."""
    g = dict(GRUPO, hasta=float("nan"))
    md = denuncia_inhabilitado_multi(g, MANIFEST)
    assert "nan" not in md.lower().replace("financ", "")
    assert "sin fecha de término" in md


def test_lists_every_contract_once():
    md = denuncia_inhabilitado_multi(GRUPO, MANIFEST, verificado="2026-06-11")
    assert md.startswith("# Denuncia")
    assert "SIE020425UJ7" in md
    assert md.count("COMISION NACIONAL DEL AGUA") >= 1
    assert "2025-04-01" in md and "2025-06-04" in md
    assert "$3,262,500.00" in md and "$764,620.00" in md
    assert "$4,027,120.00" in md           # monto total del grupo
    assert "2024-12-18" in md and "2025-12-18" in md   # ventana una vez
    assert "artículo 59" in md and "no constituye una acusación" in md
    # ligas reconstruidas al portal vigente
    assert "buengobierno.gob.mx" in md and "x.mx" not in md


def test_build_groups_by_supplier_and_institution(tmp_path):
    import pandas as pd
    rows = [
        {"proveedor": "P", "rfc": "AAA101010AB1", "institucion": "IMSS",
         "inhabilitado_desde": "2023-01-01", "hasta": "2024-01-01",
         "fecha_contrato": "2023-06-01", "importe": 100.0, "tipo_procedimiento": "AD",
         "direccion_anuncio": "https://x.mx/detalle/" + "c"*32 + "/p"},
        {"proveedor": "P", "rfc": "AAA101010AB1", "institucion": "IMSS",
         "inhabilitado_desde": "2023-01-01", "hasta": "2024-01-01",
         "fecha_contrato": "2023-07-01", "importe": 200.0, "tipo_procedimiento": "AD",
         "direccion_anuncio": "https://x.mx/detalle/" + "d"*32 + "/p"},
        {"proveedor": "P", "rfc": "AAA101010AB1", "institucion": "SICT",
         "inhabilitado_desde": "2023-01-01", "hasta": "2024-01-01",
         "fecha_contrato": "2023-08-01", "importe": 300.0, "tipo_procedimiento": "AD",
         "direccion_anuncio": "https://x.mx/detalle/" + "e"*32 + "/p"},
        # ventana abierta: se omite
        {"proveedor": "Q", "rfc": "BBB101010AB1", "institucion": "IMSS",
         "inhabilitado_desde": "2015-01-01", "hasta": float("nan"),
         "fecha_contrato": "2024-01-01", "importe": 9.0, "tipo_procedimiento": "AD",
         "direccion_anuncio": "https://x.mx/detalle/" + "f"*32 + "/p"},
    ]
    f = tmp_path / "findings"; f.mkdir()
    pd.DataFrame(rows).to_csv(f / "f05_durante_inhabilitacion.csv", index=False)
    grupos = build_inhabilitado(findings_dir=f, solo_acotadas=True)
    # P×IMSS (2 contratos) y P×SICT (1) -> 2 grupos; Q omitida por ventana abierta
    claves = {(g["rfc"], g["institucion"]) for g in grupos}
    assert claves == {("AAA101010AB1", "IMSS"), ("AAA101010AB1", "SICT")}
    imss = next(g for g in grupos if g["institucion"] == "IMSS")
    assert len(imss["contratos"]) == 2
