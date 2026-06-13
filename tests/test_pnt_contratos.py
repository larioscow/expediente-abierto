"""Lógica pura del ingestor PNT (scripts/pnt_contratos.py): elección de
facetas, reanudación por manifiesto y atomicidad — sin red."""

from scripts.pnt_contratos import (carga_manifiesto, clave_entrega,
                                   guarda_manifiesto, nombre_archivo,
                                   parsea_facetas, pendiente)


def test_pendiente_si_nunca_bajo_crecio_o_quedaron_fallidos():
    clave = clave_entrega(26, "2024", "59747")
    assert pendiente({}, clave, 10)  # nunca bajado
    man = {clave: {"filas": 49_000, "sujetos_fallidos": []}}
    assert not pendiente(man, clave, 49_000)   # al día
    assert not pendiente(man, clave, 48_500)   # el remoto se encogió
    assert pendiente(man, clave, 49_100)       # creció: re-bajar
    man[clave]["sujetos_fallidos"] = ["4870"]
    assert pendiente(man, clave, 49_000)       # reintentar fallidos


def test_ejercicios_default_sigue_el_anio_en_curso():
    from datetime import date

    from scripts.pnt_contratos import ejercicios_default
    # año en curso y el anterior, sin literales que caduquen
    assert ejercicios_default(date(2026, 6, 1)) == "2025,2026"
    assert ejercicios_default(date(2028, 1, 1)) == "2027,2028"


def test_clave_y_nombre_de_archivo_estables():
    assert clave_entrega(7, "2024", "59729") == "07_2024_59729"
    assert nombre_archivo(7, "2024", "59729") == "pnt_07_2024_59729.csv"


def test_parsea_facetas_prioriza_vigentes_y_ordena_por_volumen():
    d = {"facets_hist": {
        "id_formato": {
            "59747": {"label": "Resultados de procedimientos de adjudicación "
                               "directa, licitación pública e invitación "
                               "restringida", "count": 24435},
            "59748": {"label": "Resultados de procedimientos de adjudicación "
                               "directa realizados", "count": 24688},
            "11111": {"label": "Padrón de proveedores", "count": 99999},
        },
        "id_sujetoobligado": {
            "4875": {"label": "SON - Colegio de Bachilleres", "count": 323},
            "4870": {"label": "SON - Centro de Evaluación", "count": 36},
        },
    }}
    formatos, sujetos = parsea_facetas(d)
    assert [f[0] for f in formatos] == ["59748", "59747"]  # padrón excluido
    assert [s[0] for s in sujetos] == ["4875", "4870"]     # mayores primero


def test_parsea_facetas_cae_a_etiquetas_de_adjudicacion():
    d = {"facets_hist": {
        "id_formato": {
            "100": {"label": "Procedimientos de licitación pública", "count": 5},
            "200": {"label": "Algo sin relación", "count": 50},
        },
        "id_sujetoobligado": {},
    }}
    formatos, sujetos = parsea_facetas(d)
    assert [f[0] for f in formatos] == ["100"]
    assert sujetos == []


def test_un_sujeto_colgado_no_tira_al_estado(tmp_path):
    """Un timeout en un sujeto obligado se registra como fallido y los demás
    se descargan completos (la lección de Zacatecas)."""
    from scripts.pnt_contratos import descarga_formato

    class SesionFalsa:
        def get(self, path):
            if "id_sujetoobligado=MALO" in path:
                raise TimeoutError("curl 28")
            return 200, "text/csv", "A,B\n1,2\n"

    destino = tmp_path / "pnt_32_2024_1.csv"
    filas, por_sujeto, fallidos = descarga_formato(
        SesionFalsa(), "Zacatecas", 32, "2024", "1",
        [("MALO", "SO colgado", 5), ("BUENO", "SO sano", 5)], destino)
    assert fallidos == ["MALO"]
    assert por_sujeto == {"BUENO": 1}
    assert filas == 1
    assert destino.exists() and "SO sano" in destino.read_text()


def test_manifiesto_atomico_y_tolerante(tmp_path):
    path = tmp_path / "manifiesto.json"
    guarda_manifiesto({"a": {"filas": 1}}, path)
    assert carga_manifiesto(path) == {"a": {"filas": 1}}
    assert not path.with_suffix(".json.tmp").exists()
    path.write_text("{corrupto")
    assert carga_manifiesto(path) == {}  # se reconstruye, no truena
