"""Denuncia PDFs: the markdown drafts must render into a clean, official-
looking HTML document (the PDF itself is Chromium print — not unit-tested)."""
from casework.pdf import md_to_html

MD = """# Borrador de denuncia — contratación con proveedor inhabilitado

**Presentar en:** SIDEC (<https://sidec.buengobierno.gob.mx/>).

> **Aviso.** Describe hechos verificables y **se solicita** su investigación.

## Hechos

1. Registro con RFC **CAO070122P44** del **2023-05-04** al **2024-05-03**.

| proveedor | monto |
|---|---|
| VITAL SA | $1,000 |

- `sfp_sancionados.json` — sha256 `aa11`
"""


def test_renders_structure_not_literal_markdown():
    html = md_to_html(MD)
    assert "<h1>" in html and "<h2>" in html
    assert "<strong>CAO070122P44</strong>" in html
    assert "<td>VITAL SA</td>" in html          # tables extension on
    assert "<blockquote>" in html               # aviso box
    assert "sidec.buengobierno.gob.mx" in html
    # no literal markdown syntax leaks into the document
    for leak in ("##", "**", "| proveedor |"):
        assert leak not in html


def test_document_chrome_is_minimal():
    html = md_to_html(MD, generado="2026-06-11")
    assert "2026-06-11" in html
    assert "@page" in html                      # print setup
    for slop in ["EXPEDIENTE ABIERTO", "generado automáticamente", "pipeline"]:
        assert slop not in html, slop


def test_legal_standard_typography():
    """Práctica forense mexicana: Arial 12pt, interlineado 1.5, justificado,
    monocromo — sin tipografías decorativas ni acentos de color."""
    html = md_to_html(MD)
    assert "Arial" in html
    assert "12pt" in html
    assert "1.5" in html
    for decorativo in ["Georgia", "Fraunces", "#a3001e"]:
        assert decorativo not in html, decorativo
