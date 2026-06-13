"""Unión y dedupe de páginas capturadas del listado de ComprasMX."""
from realtime.comprasmx_client import merge_list_pages


def _page(uuids, success=True):
    return {"success": success,
            "data": [{"registros": [{"uuid_procedimiento": u} for u in uuids]}]}


def test_merges_pages_preserving_order():
    rows = merge_list_pages([_page(["a", "b"]), _page(["c"])])
    assert [r["uuid_procedimiento"] for r in rows] == ["a", "b", "c"]


def test_dedupes_rows_repeated_across_pages():
    """Si el portal publica entre clics, una fila se corre de página y
    aparece dos veces: debe contarse una sola vez."""
    rows = merge_list_pages([_page(["a", "b"]), _page(["b", "c"])])
    assert [r["uuid_procedimiento"] for r in rows] == ["a", "b", "c"]


def test_skips_failed_payloads_and_garbage():
    rows = merge_list_pages([
        _page(["a"]),
        _page(["x"], success=False),
        {"success": True, "data": None},
        "no-es-dict",
    ])
    assert [r["uuid_procedimiento"] for r in rows] == ["a"]


def test_rows_without_uuid_are_kept():
    # una fila rara sin uuid no debe tirar el poll ni dedupearse entre sí
    rows = merge_list_pages([_page(["a"]),
                             {"success": True, "data": [{"registros": [{}]}]}])
    assert len(rows) == 2
