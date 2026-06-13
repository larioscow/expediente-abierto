"""Render the denuncia drafts as professional PDFs.

Markdown → styled HTML (official-document layout, same design language as
the public site) → Chromium print-to-PDF via Playwright (already a project
dependency; no LaTeX, no pandoc).

Uso:
    python -m casework.pdf          # findings/denuncias/*.md -> *.pdf
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
DENUNCIAS = ROOT / "findings" / "denuncias"

# Tipografía de práctica forense mexicana: Arial 12pt, interlineado 1.5,
# texto justificado, monocromo, márgenes de 2.5 cm.
CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
body {
  margin: 0; color: #000; background: #fff;
  font-family: Arial, Helvetica, sans-serif;
  font-size: 12pt; line-height: 1.5;
}
.hoja { padding: 2.2cm 2.5cm 1.8cm; }
.membrete {
  display: flex; justify-content: space-between;
  font-size: 9pt; font-weight: bold; text-transform: uppercase;
  letter-spacing: .06em;
  border-bottom: 1pt solid #000; padding-bottom: 5pt; margin-bottom: 16pt;
}
h1 {
  font-size: 14pt; font-weight: bold; text-transform: uppercase;
  text-align: center; line-height: 1.35; margin: 0 0 16pt;
}
h2 {
  font-size: 12pt; font-weight: bold; text-transform: uppercase;
  margin: 16pt 0 8pt;
}
p { margin: 0 0 10pt; text-align: justify; }
strong { font-weight: bold; }
blockquote {
  margin: 0 0 12pt; padding: 8pt 12pt; font-size: 10.5pt;
  text-align: justify; border: 1pt solid #000;
}
blockquote p { margin: 0; }
ol, ul { margin: 0 0 10pt; padding-left: 1.8em; }
li { margin-bottom: 6pt; text-align: justify; }
code {
  font-family: "Courier New", Courier, monospace; font-size: 9.5pt;
  word-break: break-all;
}
a { color: #000; word-break: break-all; }
table {
  border-collapse: collapse; width: 100%; margin: 4pt 0 12pt;
  font-size: 10pt;
}
th {
  font-weight: bold; text-align: left; padding: 4pt 6pt;
  border: .75pt solid #000; background: #efefef;
}
td { border: .5pt solid #000; padding: 4pt 6pt; vertical-align: top; }
"""


def md_to_html(md_text: str, generado: str | None = None) -> str:
    """Wrap a denuncia document in the official template. The header label
    follows the document itself: drafts say borrador, verified cases don't."""
    generado = generado or date.today().isoformat()
    etiqueta = ("BORRADOR" if md_text.lstrip().startswith("# Borrador")
                else "DENUNCIA")
    body = markdown.markdown(md_text, extensions=["tables", "sane_lists"])
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><style>{CSS}</style></head>
<body><div class="hoja">
<div class="membrete">
  <span>{etiqueta}</span>
  <span>{generado}</span>
</div>
{body}
</div></body></html>"""


def _imprimir(page, html: str, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    page.set_content(html, wait_until="load")
    page.pdf(path=str(out_path), format="A4", print_background=True,
             display_header_footer=True,
             header_template="<span></span>",
             footer_template="""
               <div style="width:100%;text-align:center;
                           font:7px Menlo,monospace;color:#5d564b;">
                 <span class="pageNumber"></span> / <span class="totalPages"></span>
               </div>""",
             margin={"top": "0.8cm", "bottom": "1.1cm",
                     "left": "0", "right": "0"})


def render_pdf(html: str, out_path: Path):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        _imprimir(browser.new_page(), html, out_path)
        browser.close()


def build_pdfs(src_dir: Path = DENUNCIAS, out_dir: Path | None = None) -> list[Path]:
    """Un solo navegador para todo el lote — no uno por PDF."""
    from playwright.sync_api import sync_playwright

    out_dir = src_dir if out_dir is None else Path(out_dir)
    written = []
    files = sorted(Path(src_dir).glob("*.md"))
    if not files:
        return written
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        for md_file in files:
            pdf = out_dir / (md_file.stem + ".pdf")
            _imprimir(page, md_to_html(md_file.read_text(encoding="utf-8")), pdf)
            written.append(pdf)
        browser.close()
    return written


if __name__ == "__main__":
    files = build_pdfs()
    print(f"escribí {len(files)} PDFs -> {DENUNCIAS}")
