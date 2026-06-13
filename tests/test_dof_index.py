"""Circulares de inhabilitación del DOF: parser del título, índice con
vigencia y la señal de alerta temprana en el scoring del monitoreo."""
import io
import json
from datetime import date

from realtime.comprasmx_client import Award
from realtime.dof_index import DofIndex, fetch_dia, parse_titulo, refresh
from realtime.risk import Assessment, assess_awards
from realtime.efos_index import EfosIndex


class TestParseTitulo:
    def test_empresa(self):
        t = ("Circular por la que se comunica ... que deberán abstenerse de "
             "aceptar propuestas o celebrar contratos con la empresa "
             "Garza Gas, S. A. de C.V.")
        assert parse_titulo(t) == ["Garza Gas, S. A. de C.V"]

    def test_persona_fisica(self):
        t = ("CIRCULAR ... deberán abstenerse de aceptar propuestas o "
             "celebrar contrato con la persona física con actividad "
             "empresarial Juan Pérez López.")
        assert parse_titulo(t) == ["Juan Pérez López"]

    def test_variantes_reales_del_dof(self):
        # "y/o celebrar" + "la empresa"
        assert parse_titulo(
            "... que deberán abstenerse de aceptar propuestas y/o celebrar "
            "contratos con la empresa Brigalag, S.A. de C.V."
        ) == ["Brigalag, S.A. de C.V"]
        # "participar en procedimientos de contratación o celebrar" + moral
        assert parse_titulo(
            "... que deberán abstenerse de participar en procedimientos de "
            "contratación o celebrar contratos con la persona moral "
            "Servicios Especiales de Gas LP, S.A. de C.V."
        ) == ["Servicios Especiales de Gas LP, S.A. de C.V"]
        # "denominada"
        assert parse_titulo(
            "... deberán abstenerse de aceptar propuestas y/o celebrar "
            "contratos con la persona moral denominada Corporativo Mexicano "
            "Revelor, S.A. de C.V."
        ) == ["Corporativo Mexicano Revelor, S.A. de C.V"]
        # "la moral" a secas
        assert parse_titulo(
            "... deberán abstenerse de aceptar propuestas o celebrar "
            "contratos con la moral Bioabast, S.A. de C.V."
        ) == ["Bioabast, S.A. de C.V"]

    def test_plural_separa_nombres(self):
        t = ("... deberán abstenerse de aceptar propuestas o celebrar "
             "contratos con las empresas Alfa Construcciones, S.A. de C.V. y "
             "Beta Servicios, S.A. de C.V.")
        assert parse_titulo(t) == ["Alfa Construcciones, S.A. de C.V.",
                                   "Beta Servicios, S.A. de C.V"]

    def test_titulo_ajeno(self):
        assert parse_titulo("Convenio de Coordinación y Adhesión ...") == []


def abre_falso(respuestas: dict):
    """Devuelve un urlopen falso que sirve JSON por URL (context manager)."""
    class _Resp(io.StringIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def abre(url, timeout=30):
        for fragmento, payload in respuestas.items():
            if fragmento in url:
                return _Resp(json.dumps(payload))
        raise AssertionError(f"URL inesperada: {url}")
    return abre


DIA = {"NotasMatutinas": [
    {"codNota": 111, "titulo": "Convenio de Coordinación ..."},
    {"codNota": 222, "titulo": ("Circular por la que se comunica ... que "
                                "deberán abstenerse de aceptar propuestas o "
                                "celebrar contratos con la empresa "
                                "Fantasma SA de CV")},
], "NotasVespertinas": [], "NotasExtraordinarias": []}

NOTA = {"Nota": {"cadenaContenido": (
    "<p>... R.F.C. FAN101010AAA ... la INHABILITACIÓN TEMPORAL por un "
    "periodo de DOS (2) AÑOS; para participar ...</p>")}}


def test_fetch_dia_filtra_y_extrae():
    out = fetch_dia("09-06-2026", abre=abre_falso({"/notas/09-06-2026": DIA}))
    assert len(out) == 1
    assert out[0]["quien"] == "Fantasma SA de CV"
    assert out[0]["fecha_dof"] == "2026-06-09"
    assert "dof.gob.mx" in out[0]["url"]


def test_refresh_acumula_y_enriquece(tmp_path):
    path = tmp_path / "dof.json"
    abre = abre_falso({"/notas/nota/222": NOTA,
                       "/notas/": DIA})  # todos los días devuelven lo mismo
    todas = refresh(dias=2, path=path, abre=abre, hoy=date(2026, 6, 9))
    assert len(todas) == 1  # dedupe por cod_nota entre días
    assert todas[0]["rfc"] == "FAN101010AAA"
    assert "DOS (2) AÑOS" in todas[0]["plazo_txt"]
    # segundo refresh no duplica
    assert len(refresh(dias=1, path=path, abre=abre, hoy=date(2026, 6, 9))) == 1


def indice(tmp_path, fecha_dof="2026-06-01", hoy=date(2026, 6, 12)):
    path = tmp_path / "dof.json"
    path.write_text(json.dumps({"generado": "2026-06-12T00:00:00+00:00",
                                "circulares": [{
                                    "cod_nota": 1, "fecha_dof": fecha_dof,
                                    "titulo": "t", "quien": "Fantasma SA de CV",
                                    "rfc": None, "plazo_txt": None,
                                    "url": "https://dof.gob.mx/x"}]}))
    return DofIndex(path, hoy=hoy)


def test_indice_vigencia(tmp_path):
    assert indice(tmp_path).match_name("FANTASMA, S.A. DE C.V.") is not None
    viejo = indice(tmp_path, fecha_dof="2024-01-01")
    assert viejo.match_name("FANTASMA, S.A. DE C.V.") is None  # >180 días


def premio(licitante="FANTASMA SA DE CV", fecha="2026-06-10"):
    return Award(licitante=licitante, importe=1.0, importe_max=None,
                 moneda="MXN", institucion="IMSS", estatus="ADJUDICADO",
                 titulo="x", fecha_inicio=fecha, fecha_publicacion=fecha,
                 cod_drc="X")


def test_senal_dof_gano_ya_inhabilitado(tmp_path):
    a = Assessment("u", "n", "x", "IMSS", "VIGENTE")
    efos_vacio = EfosIndex.__new__(EfosIndex)
    efos_vacio.by_name = {}
    a = assess_awards(a, [premio()], efos_vacio, sfp=None,
                      dof=indice(tmp_path))
    codigos = [f.code for f in a.flags]
    assert "DOF_INHABILITACION" in codigos
    assert a.score >= 8  # ganó después de la publicación: peso máximo
    assert a.awards_flagged[0]["lista"] == "DOF"
    assert a.awards_flagged[0]["gano_ya_inhabilitado"] is True
