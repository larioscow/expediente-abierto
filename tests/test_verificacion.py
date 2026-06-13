"""Verificación determinista: cruce por nombre (advisorio) y huella de la
entidad a lo largo de hallazgos federales y estatales."""
import pandas as pd

from casework.verificacion import cross_match_name, footprint


class _FakeEfos:
    def __init__(self, by_name):
        self._b = by_name

    def match_name(self, n):
        from shared.normalizacion import normalize
        return self._b.get(normalize(n))


class _FakeSfp:
    def __init__(self, by_name):
        self._b = by_name

    def match_name(self, n):
        from shared.normalizacion import normalize
        return self._b.get(normalize(n), [])


def test_cross_match_name_uses_both_indices():
    efos = _FakeEfos({"CONSTRUCTORA X": {"rfc": "CXX010101AA1",
                                         "situacion": "Definitivo",
                                         "nombre": "CONSTRUCTORA X SA DE CV"}})
    sfp = _FakeSfp({"CONSTRUCTORA X": [{"rfc": "CXX010101AA1",
                                        "plazo_txt": "2 años", "inicio": "2024-01-01",
                                        "fin": "2026-01-01",
                                        "nombre": "CONSTRUCTORA X"}]})
    hits = cross_match_name("Constructora X, S.A. de C.V.", efos=efos, sfp=sfp)
    assert {h["fuente"] for h in hits} == {"69-B (EFOS)", "SFP sancionados"}
    assert all(h["rfc"] == "CXX010101AA1" for h in hits)


def test_cross_match_name_empty_is_safe():
    assert cross_match_name("", efos=_FakeEfos({}), sfp=_FakeSfp({})) == []


def test_footprint_matches_rfc_across_federal_and_state(tmp_path):
    f = tmp_path / "findings"
    f.mkdir()
    pd.DataFrame([{"rfc": "ABC010101AA1", "institucion": "IMSS",
                   "proveedor": "ENTIDAD X", "fecha_contrato": "2024-01-01",
                   "importe": 1000}]).to_csv(
        f / "f01_detalle_completo.csv", index=False)
    pd.DataFrame([{"estado_comprador": "JALISCO", "sujeto_obligado": "JAL - X",
                   "proveedor": "ENTIDAD X", "rfc_norm": "ABC010101AA1",
                   "fecha_efectiva": "2025-02-02", "importe": 2000}]).to_csv(
        f / "f10_inhabilitados_estatal.csv", index=False)
    fp = footprint(rfc="ABC010101AA1", findings_dir=f)
    assert len(fp) == 2
    assert set(fp["ambito"]) == {"federal", "estatal"}
    assert set(fp["origen"]) == {"f01_detalle_completo.csv",
                                 "f10_inhabilitados_estatal.csv"}


def test_footprint_matches_by_normalized_name_when_no_rfc(tmp_path):
    f = tmp_path / "findings"
    f.mkdir()
    pd.DataFrame([{"estado_comprador": "SONORA", "sujeto_obligado": "SON - X",
                   "proveedor": "Maxi Servicios de México, S.A. de C.V.",
                   "monto_mxn_millones": 5}]).to_csv(
        f / "f10_concentracion_estatal.csv", index=False)
    fp = footprint(razon_social="MAXI SERVICIOS DE MEXICO SA DE CV",
                   findings_dir=f)
    assert len(fp) == 1
    assert fp.iloc[0]["importe"] == 5_000_000   # millones -> MXN exacto


def test_footprint_empty_for_unknown(tmp_path):
    f = tmp_path / "findings"
    f.mkdir()
    fp = footprint(rfc="ZZZ999999ZZ9", findings_dir=f)
    assert fp.empty and list(fp.columns) == ["origen", "ambito", "estado",
                                             "institucion", "proveedor", "rfc",
                                             "fecha", "importe"]
