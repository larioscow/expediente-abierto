"""Realtime risk rules — procedure-level flags."""
from realtime.comprasmx_client import Procedure
from realtime.risk import assess_procedure


def proc(tipo="LICITACIÓN PÚBLICA", **kw):
    return Procedure(uuid="u1", numero="N1", nombre="x", siglas="IMSS",
                     estatus="VIGENTE", tipo_procedimiento=tipo,
                     tipo_contratacion="", caracter="", entidad="",
                     unidad_compradora="", fecha_apertura=kw.pop("fecha_apertura", None),
                     cod_expediente="")


def codes(a):
    return {f.code for f in a.flags}


def test_compressed_tender_window_flags():
    """LAASSP floor is 10 days even with a justified reduction — fewer days
    between convocatoria and apertura is a screen, declared or not."""
    a = assess_procedure(proc(), {"fecha_publicacion": "2026-06-01T09:00:00",
                                  "fecha_apertura": "2026-06-06T10:00:00"})
    assert "PLAZO_COMPRIMIDO" in codes(a)
    assert a.score >= 2


def test_normal_tender_window_does_not_flag():
    a = assess_procedure(proc(), {"fecha_publicacion": "2026-06-01T09:00:00",
                                  "fecha_apertura": "2026-06-21T10:00:00"})
    assert "PLAZO_COMPRIMIDO" not in codes(a)


def test_direct_award_has_no_window_rule():
    a = assess_procedure(proc(tipo="ADJUDICACIÓN DIRECTA"),
                         {"fecha_publicacion": "2026-06-01T09:00:00",
                          "fecha_apertura": "2026-06-03T10:00:00"})
    assert "PLAZO_COMPRIMIDO" not in codes(a)


def test_garbage_dates_are_ignored():
    a = assess_procedure(proc(), {"fecha_publicacion": "no es fecha",
                                  "fecha_apertura": None})
    assert "PLAZO_COMPRIMIDO" not in codes(a)


def test_apertura_falls_back_to_listing_field():
    a = assess_procedure(proc(fecha_apertura="2026-06-05T10:00:00"),
                         {"fecha_publicacion": "2026-06-01T09:00:00"})
    assert "PLAZO_COMPRIMIDO" in codes(a)
