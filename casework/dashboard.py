"""Dashboard local de casos — todo el triaje en una sola vista.

Servidor local (stdlib, sin dependencias) sobre la tabla `triage`
(data/cases.duckdb): lista cada caso accionable —federal y de los estados, de
todos los tiers—, permite generar su denuncia en PDF y llevar el estado del
ciclo de verificación:
nuevo → verificando → verificado → denunciado → publicado / descartado.

El estado humano vive en la tabla `triage` y `python -m casework.triage scan`
NUNCA lo pisa. Corre el scan antes de abrir el dashboard para poblarla:

    python -m casework.triage scan
    python -m casework.dashboard          # http://localhost:8765
"""
from __future__ import annotations

import html
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd

from casework.triage import (DB, GENERABLES, TriageStore, generar,
                             nombre_documento, routing)
from casework.verificacion import footprint
from realtime.store import ESTADOS

ROOT = Path(__file__).resolve().parent.parent
FINDINGS = ROOT / "findings"
DENUNCIAS = FINDINGS / "denuncias"
PUERTO = 8765

_LOCK = threading.Lock()

_HOSTS_PROPIOS = {f"localhost:{PUERTO}", f"127.0.0.1:{PUERTO}"}
_ORIGENES_PROPIOS = {f"http://{h}" for h in _HOSTS_PROPIOS}


def origen_permitido(headers) -> bool:
    """Solo tráfico del propio dashboard: una página externa no debe poder
    hacer POST ciego a localhost y alterar estados de verificación."""
    if headers.get("Host") not in _HOSTS_PROPIOS:
        return False
    origin = headers.get("Origin")
    return origin is None or origin in _ORIGENES_PROPIOS


def _txt(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def casos_triage(db: Path = DB, incluir_filed: bool = False) -> list[dict]:
    """Filas del libro de triaje listas para mostrar. Ordenadas por tier y
    puntaje (lo más denunciable primero)."""
    try:
        df = TriageStore(db).rows(incluir_filed=incluir_filed)
    except Exception:
        return []
    casos = []
    for _, r in df.iterrows():
        pat, amb = r.get("pattern"), r.get("ambito")
        aut, fund = routing(pat, amb)
        cid = r["case_id"]
        archivo = nombre_documento(pat, amb, r.get("rfc"),
                                   r.get("estado_geo"), cid) + ".pdf"
        casos.append({
            "id": cid, "tier": _txt(r.get("tier")), "score": int(r.get("score") or 0),
            "pattern": _txt(pat), "ambito": _txt(amb),
            "estado_geo": _txt(r.get("estado_geo")) or "FEDERAL",
            "sujeto": _txt(r.get("sujeto")), "rfc": _txt(r.get("rfc")),
            "institucion": _txt(r.get("institucion")),
            "monto": float(r.get("monto") or 0), "n": int(r.get("n_contratos") or 0),
            "estado": _txt(r.get("estado")) or "nuevo", "nota": _txt(r.get("nota")),
            "recomendacion": _txt(r.get("recomendacion")),
            "autoridad": aut, "archivo": archivo,
            "puede_generar": pat in GENERABLES,
            "cuarentena": _txt(r.get("cuarentena")),
        })
    casos.sort(key=lambda c: (-{"T1": 3, "T2": 2, "T3": 1}.get(c["tier"], 0),
                              -c["score"]))
    return casos


def generar_doc(case_id: str, db: Path = DB) -> Path:
    """(Re)genera la denuncia del caso. Estados verificado+ producen la versión
    presentable; lo demás, borrador. Solo patrones GENERABLES."""
    return generar(case_id, out_dir=DENUNCIAS, render_pdf=True, db=db)


# ------------------------------------------------------------------ HTML

_BADGE = {"nuevo": "#5d564b", "verificando": "#8a6d00", "verificado": "#1d6b30",
          "denunciado": "#a3001e", "publicado": "#0b4a6f", "descartado": "#999"}
_TIER = {"T1": "#a3001e", "T2": "#8a6d00", "T3": "#5d564b"}


def _fila(c: dict) -> str:
    e = html.escape
    color = _BADGE.get(c["estado"], "#5d564b")
    tcolor = _TIER.get(c["tier"], "#5d564b")
    monto = f"${c['monto']:,.2f}" if c.get("monto") else "—"
    pdf_existe = (DENUNCIAS / c["archivo"]).exists()
    cuar = (f'<span class="cuar">cuarentena: {e(c["cuarentena"])}</span>'
            if c.get("cuarentena") else "")
    opciones = "".join(
        f'<option value="{s}"{" selected" if s == c["estado"] else ""}>{s}</option>'
        for s in ESTADOS)
    gen = (f'<form method="post" action="/generar">'
           f'<input type="hidden" name="id" value="{e(c["id"])}">'
           f'<button class="btn rojo">{"Regenerar" if pdf_existe else "Generar"}'
           f' denuncia</button></form>' if c["puede_generar"]
           else '<span class="hint">expediente consolidado</span>')
    ver = (f'<a class="btn" href="/pdf/{e(c["archivo"])}" target="_blank">Ver PDF</a>'
           if pdf_existe else "")
    return f"""<tr>
<td><span class="badge" style="--c:{color}">{e(c["estado"])}</span></td>
<td><span class="tier" style="--c:{tcolor}">{e(c["tier"])}</span>
  <span class="score">{c["score"]}</span></td>
<td><strong>{e(c["sujeto"])}</strong><br>
  <span class="mono">{e(c["rfc"]) or "—"}</span>
  · <span class="amb">{e(c["ambito"])} · {e(c["estado_geo"])}</span></td>
<td class="detalle">{e(c["pattern"])} · {c["n"]} contrato(s)<br>
  <span class="aut">{e(c["autoridad"])}</span><br>
  <span class="nota">{e(c["nota"])}</span> {cuar}</td>
<td class="num mono">{monto}</td>
<td class="acciones">
  {gen} {ver}
  <a class="btn" href="/caso/{e(c["id"])}" target="_blank">Huella ↗</a>
  <form method="post" action="/estado" class="estado">
    <input type="hidden" name="id" value="{e(c["id"])}">
    <select name="estado">{opciones}</select>
    <input name="nota" placeholder="nota / folio" value="{e(c["nota"])}">
    <button class="btn">Guardar</button>
  </form>
</td></tr>"""


_ESTILO = """
:root { --papel:#f6f2ea; --tinta:#1b1713; --linea:#d8d0bf; --rojo:#a3001e; }
body { margin:0; background:var(--papel); color:var(--tinta);
       font:14px/1.5 "IBM Plex Sans", ui-sans-serif, sans-serif; }
.pagina { max-width:1320px; margin:0 auto; padding:1.2rem; }
h1 { font:700 1.7rem/1.1 Georgia, serif; margin:.4rem 0 .2rem;
     border-bottom:3px double var(--tinta); padding-bottom:.6rem; }
.sub { color:#5d564b; font-size:.82rem; margin-bottom:1.2rem; }
.msg { background:#1d6b3015; border-left:3px solid #1d6b30; padding:.4rem .8rem;
       margin-bottom:1rem; font-size:.85rem; }
table { border-collapse:collapse; width:100%; background:#fffdf8;
        border:1px solid var(--linea); }
th { font:600 .65rem/1.3 ui-monospace, Menlo, monospace; letter-spacing:.08em;
     text-transform:uppercase; color:#5d564b; text-align:left;
     padding:.5rem .6rem; border-bottom:2px solid var(--tinta); background:#efe9dd; }
td { padding:.55rem .6rem; border-bottom:1px solid var(--linea); vertical-align:top; }
tr:hover { background:#a3001e0d; }
.mono { font:.78rem ui-monospace, Menlo, monospace; }
.num { text-align:right; white-space:nowrap; }
.detalle { font-size:.82rem; max-width:30ch; }
.nota { color:var(--rojo); font-size:.75rem; }
.cuar { color:#8a6d00; font-size:.72rem; }
.aut { color:#5d564b; font-size:.74rem; }
.amb { color:#5d564b; font-size:.72rem; text-transform:uppercase; }
.badge { display:inline-block; border:1.5px solid var(--c); color:var(--c);
        font:600 .68rem/1.6 ui-monospace, Menlo, monospace; padding:0 .45em;
        text-transform:uppercase; letter-spacing:.05em; }
.tier { display:inline-block; border:1.5px solid var(--c); color:var(--c);
        font:700 .7rem/1.5 ui-monospace, Menlo, monospace; padding:0 .4em; }
.score { font:600 .8rem ui-monospace, Menlo, monospace; color:#5d564b; }
.acciones { min-width:280px; }
.acciones form { display:inline-block; margin:0 .2rem .3rem 0; }
.btn { font:600 .72rem ui-monospace, Menlo, monospace; padding:.25rem .6rem;
      background:#fff; border:1px solid var(--tinta); cursor:pointer;
      text-decoration:none; color:var(--tinta); display:inline-block; }
.btn.rojo { border-color:var(--rojo); color:var(--rojo); }
.btn:hover { background:var(--tinta); color:#fff; }
.estado select, .estado input { font:.72rem ui-monospace, Menlo, monospace;
      padding:.22rem; border:1px solid var(--linea); background:#fff; }
.estado input { width:140px; }
.hint { color:#999; font-size:.72rem; }
a { color:var(--rojo); }
"""


def render(casos: list[dict], msg: str = "") -> str:
    filas = "".join(_fila(c) for c in casos)
    n_t1 = sum(1 for c in casos if c["tier"] == "T1")
    n_den = sum(1 for c in casos if c["estado"] == "denunciado")
    vacio = ('<p class="sub">No hay casos en el libro. Corre '
             '<code>python -m casework.triage scan</code> primero.</p>'
             if not casos else "")
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Casos — Expediente Abierto</title>
<style>{_ESTILO}</style></head><body><div class="pagina">
<h1>Casos bajo señal</h1>
<p class="sub">{len(casos)} casos · {n_t1} de tier 1 · {n_den} denunciados ·
<a href="https://denuncias.gob.mx/SidecGobMX/#!/busqueda" rel="noopener"
target="_blank">seguimiento de denuncias en SIDEC ↗</a> (folio y clave: en la
nota de cada caso) · los PDF se escriben en <code>findings/denuncias/</code></p>
{f'<div class="msg">{html.escape(msg)}</div>' if msg else ''}
{vacio}
<table><thead><tr><th>estado</th><th>tier</th><th>caso</th>
<th>señal / autoridad / nota</th><th>monto (MXN)</th><th>acciones</th></tr></thead>
<tbody>{filas}</tbody></table>
</div></body></html>"""


def render_caso(case_id: str, db: Path = DB,
                findings_dir: Path = FINDINGS) -> str:
    """Detalle de un caso con su HUELLA: todos los contratos y señales de la
    entidad a lo largo de los hallazgos federales y estatales."""
    e = html.escape
    row = TriageStore(db).get(case_id)
    if not row:
        return "<p>caso desconocido</p>"
    fp = footprint(rfc=row.get("rfc"), razon_social=row.get("sujeto"),
                   findings_dir=findings_dir)
    if len(fp):
        head = "".join(f"<th>{e(c)}</th>" for c in fp.columns)
        body = "".join(
            "<tr>" + "".join(f"<td>{e(_txt(v))}</td>" for v in r) + "</tr>"
            for r in fp.itertuples(index=False))
        tabla = f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    else:
        tabla = "<p>Sin otras apariciones en los hallazgos.</p>"
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Huella — {e(_txt(row.get('sujeto')))}</title><style>{_ESTILO}</style>
</head><body><div class="pagina">
<h1>{e(_txt(row.get('sujeto')))}</h1>
<p class="sub">RFC {e(_txt(row.get('rfc'))) or '—'} · {e(_txt(row.get('ambito')))}
· tier {e(_txt(row.get('tier')))} · score {row.get('score')} ·
autoridad: {e(routing(row.get('pattern'), row.get('ambito'))[0])}</p>
<p class="sub">Huella de la entidad a lo largo de los hallazgos (cruce exacto por
RFC y por nombre normalizado):</p>
{tabla}
<p class="sub"><a href="/">← volver</a></p>
</div></body></html>"""


# ------------------------------------------------------------------ server

class _Handler(BaseHTTPRequestHandler):
    def _html(self, body: str, code: int = 200):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, msg: str = ""):
        self.send_response(303)
        q = f"/?msg={urllib.parse.quote(msg)}" if msg else "/"
        self.send_header("Location", q)
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/":
            msg = urllib.parse.parse_qs(url.query).get("msg", [""])[0]
            filed = urllib.parse.parse_qs(url.query).get("filed", ["0"])[0] == "1"
            self._html(render(casos_triage(incluir_filed=filed), msg))
        elif url.path.startswith("/caso/"):
            self._html(render_caso(urllib.parse.unquote(url.path[6:])))
        elif url.path.startswith("/pdf/"):
            name = Path(urllib.parse.unquote(url.path[5:])).name  # sin rutas
            f = DENUNCIAS / name
            if f.exists() and f.suffix == ".pdf":
                data = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._html("<p>no existe</p>", 404)
        else:
            self._html("<p>404</p>", 404)

    def do_POST(self):
        if not origen_permitido(self.headers):
            return self._html("<p>origen no permitido</p>", 403)
        n = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(n).decode())
        cid = form.get("id", [""])[0]
        if self.path == "/generar":
            try:
                with _LOCK:  # un chromium a la vez
                    out = generar_doc(cid)
            except Exception as e:
                return self._redirect(f"error al generar PDF: {e}")
            self._redirect(f"PDF generado: {out.with_suffix('.pdf').name}")
        elif self.path == "/estado":
            estado = form.get("estado", [""])[0]
            nota = form.get("nota", [""])[0]  # "" limpia la nota
            try:
                TriageStore().set_estado(cid, estado, nota)
                self._redirect(f"estado actualizado: {estado}")
            except ValueError as e:
                self._redirect(str(e))
        else:
            self._html("<p>404</p>", 404)

    def log_message(self, *a):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PUERTO), _Handler)
    print(f"dashboard: http://localhost:{PUERTO}")
    server.serve_forever()


if __name__ == "__main__":
    main()
