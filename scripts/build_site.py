#!/usr/bin/env python
"""Generate the static tracker page (site/index.html) from findings/ CSVs.

Plain HTML, no JS frameworks, Spanish, screens-not-verdicts language.
Run after the detectors; reads data coverage from data/raw/MANIFEST.tsv.
"""
import csv
import html
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
F = ROOT / "findings"
SITE = ROOT / "site"
SITE.mkdir(exist_ok=True)

manifest = {}
with open(ROOT / "data" / "raw" / "MANIFEST.tsv") as fh:
    for row in csv.DictReader(fh, delimiter="\t"):
        manifest[row["file"]] = row["retrieved_at"][:10]

import json as _json


def load_alerts(limit=50):
    p = F / "alerts.jsonl"
    if not p.exists():
        return []
    rows = [_json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
    # dedupe by uuid keeping highest score, then sort by score desc
    best = {}
    for r in rows:
        u = r.get("uuid")
        if u not in best or r["score"] > best[u]["score"]:
            best[u] = r
    return sorted(best.values(), key=lambda x: -x["score"])[:limit]


def alerts_html(alerts):
    if not alerts:
        return "<p><em>Sin alertas todavía. Corre <code>python -m realtime.poll</code>.</em></p>"
    out = ['<table><tr><th>Score</th><th>Dependencia</th><th>Procedimiento</th>'
           '<th>Tipo</th><th>Por qué</th><th></th></tr>']
    for a in alerts:
        reasons = "<br>".join(html.escape(r) for r in a.get("reasons", []))
        out.append(
            f'<tr><td><b>{a["score"]}</b></td><td>{html.escape(a.get("dependencia",""))}</td>'
            f'<td>{html.escape(a.get("numero",""))}<br><small>{html.escape(a.get("nombre","")[:80])}</small></td>'
            f'<td>{html.escape(a.get("tipo",""))}</td><td><small>{reasons}</small></td>'
            f'<td><a href="{html.escape(a.get("url","#"))}" target="_blank">ver</a></td></tr>'
        )
    out.append("</table>")
    return "".join(out)


def table(csv_name, n=15, cols=None, rename=None):
    p = F / csv_name
    if not p.exists():
        return "<p><em>pendiente</em></p>"
    df = pd.read_csv(p)
    if cols:
        df = df[[c for c in cols if c in df.columns]]
    if rename:
        df = df.rename(columns=rename)
    return df.head(n).to_html(index=False, border=0, escape=True,
                              float_format=lambda x: f"{x:,.1f}")


def read_csv(name):
    p = F / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()

# key numbers
r01 = read_csv("f01_resumen_por_situacion.csv")
defin = r01[r01["situacion"] == "Definitivo"] if not r01.empty else r01
d01_contratos = int(defin["contratos"].sum()) if not defin.empty else 0
d01_monto = defin["monto_mxn_millones"].sum() if not defin.empty else 0
r01h = read_csv("f01h_resumen_por_situacion.csv")
dh = r01h[r01h["situacion"] == "Definitivo"] if not r01h.empty else r01h
d01h_monto = dh["monto_mxn_millones"].sum() if not dh.empty else 0
r04 = read_csv("f04_resumen.csv")
d04_monto = r04["monto_a_menores_1a_mxn_m"].sum() if not r04.empty else 0
r05 = read_csv("f05_resumen.csv")
d05_monto = r05["monto_mxn_millones"].sum() if not r05.empty else 0
f05gun = read_csv("f05_durante_inhabilitacion.csv")
d05_gun = len(f05gun)
r03 = read_csv("f03_benford_instituciones.csv")
d03_noconf = int((r03["banda_nigrini"] == "NO CONFORME").sum()) if not r03.empty else 0
d03_total = len(r03)
alerts = load_alerts()
alerts_ts = alerts[0]["ts"][:16].replace("T", " ") + " UTC" if alerts else "—"

page = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Señales de riesgo en contrataciones públicas — México</title>
<style>
  body {{ font: 15px/1.5 system-ui, sans-serif; color: #1a1a1a; max-width: 1080px; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ font-size: 1.5rem; margin-bottom: .25rem; }}
  h2 {{ font-size: 1.15rem; margin-top: 2.5rem; border-bottom: 1px solid #ddd; padding-bottom: .25rem; }}
  .meta, .caveat {{ color: #555; font-size: .85rem; }}
  .nums {{ display: flex; gap: 2.5rem; flex-wrap: wrap; margin: 1.5rem 0; }}
  .nums div b {{ display: block; font-size: 1.6rem; }}
  table {{ border-collapse: collapse; font-size: .8rem; margin-top: .75rem; }}
  th, td {{ text-align: left; padding: .3rem .6rem; border-bottom: 1px solid #eee; }}
  th {{ background: #fafafa; position: sticky; top: 0; }}
  .wrap {{ overflow-x: auto; }}
  code {{ background: #f4f4f4; padding: 0 .25rem; }}
</style></head><body>

<h1>Señales de riesgo en contrataciones públicas federales</h1>
<p class="meta">Cruces reproducibles de datos oficiales (ComprasMX, SAT 69-B, CompraNet histórico).
Cada señal es un <strong>filtro estadístico que requiere verificación humana</strong>, no una acusación.
Generado: {date.today().isoformat()} ·
Datos: contratos 2023–2025 (descarga {manifest.get('contratos_2025.csv', '—')}),
histórico 2010–2023 (corte 2025-07), 69-B al 2026-04-30.</p>

<div class="nums">
  <div><b>${d01_monto + d01h_monto:,.0f}M MXN</b>en contratos a empresas después confirmadas como factureras (EFOS definitivo), 2010–2025</div>
  <div><b>${d04_monto:,.0f}M MXN</b>a empresas con menos de 1 año de constituidas, 2023–2025</div>
  <div><b>{d03_noconf}/{d03_total}</b>instituciones fuera de conformidad Benford (MAD &gt; 0.015)</div>
  <div><b>{d05_gun}</b>contratos firmados durante una inhabilitación vigente (SFP)</div>
  <div><b>{len(alerts)}</b>alertas en seguimiento (monitoreo casi en tiempo real)</div>
</div>

<h2>0 · Monitoreo casi en tiempo real (ComprasMX en vivo)</h2>
<p>Un poller (<code>realtime/poll.py</code>) consulta el portal ComprasMX en vivo
—montándose en la propia autenticación del sitio vía scrapling— y marca
procedimientos y adjudicaciones de riesgo conforme se publican, no un año después.
Señales: adjudicación directa, plazo recortado, contratación de emergencia,
proveedor en la lista 69-B (cruce por nombre, verificar), montos altos.
Última actualización de alertas: {alerts_ts}.</p>
<div class="wrap">{alerts_html(alerts)}</div>
<p class="caveat">El feed en vivo expone nombre del proveedor (no RFC); el cruce 69-B
aquí es por nombre y requiere verificación. El cruce exacto por RFC y la edad de
la empresa corren en el lote periódico cuando se publica el CSV anual.</p>

<h2>1 · Contratos a empresas del listado 69-B del SAT (factureras)</h2>
<p>Cruce exacto por RFC (2023–2025) y por nombre normalizado (histórico 2010–2023,
menor confianza). Se excluyen empresas que desvirtuaron o ganaron en tribunales.
El patrón estructural: <strong>el 100% de los contratos se firmó antes de la confirmación
del SAT</strong> — la confirmación tarda 12–36 meses; la detección al momento de la
adjudicación es el hueco que este rastreador cubre.</p>
<div class="wrap">{table("f01_top25_definitivos.csv", 10)}</div>
<p class="caveat">Tier histórico (por nombre, verificar homonimia antes de citar): ${d01h_monto:,.0f}M MXN, 613 contratos, 304 empresas.</p>

<h2>2 · Empresas jóvenes ganando contratos grandes</h2>
<p>La fecha de constitución de una persona moral está codificada en su RFC
(posiciones 4–9). Señal: empresa con &lt;1 año de vida ganando ≥$5M MXN.
La vía repetida: adjudicación directa por «urgencia y eventualidad» en salud.
<code>tipo_monto=techo_maximo</code> indica contrato abierto mín/máx: el monto es
el techo contractual, no necesariamente lo ejercido.</p>
<p class="caveat">Caso verificado en el anuncio oficial (2026-06-11): WHITEMED, S.A. de C.V.,
constituida 2023-10-17, firmó a los 179 días el contrato 012NEF001I03224-039-00 con el IMSS
(adjudicación directa AA-12-NEF-012NEF001-I-32-2024, genéricos 2024) por un mínimo garantizado
de $404.3M y techo de $1,010.8M MXN sin impuestos, más un segundo contrato IMSS-Bienestar
(mín $36.0M / máx $90.0M).</p>
<div class="wrap">{table("f04_top30_jovenes_grandes.csv", 12, cols=["proveedor","rfc","constituida","fecha_contrato","edad_dias","institucion","tipo_procedimiento","monto_mxn_millones","tipo_monto"])}</div>

<h2>3 · Concentración de adjudicaciones directas</h2>
<p>Instituciones por % del gasto vía adjudicación directa, y dependencias de un
solo proveedor. El contexto importa: medicamentos de patente y entidades
estatales tienen vías legales de excepción (columna <code>contexto</code> en el CSV).</p>
<div class="wrap">{table("f02_instituciones_pct_directas.csv", 12)}</div>
<div class="wrap">{table("f02_dependencia_proveedor_unico.csv", 10)}</div>

<h2>5 · Contratos a proveedores inhabilitados por la SFP</h2>
<p>Cruce exacto por RFC contra el Directorio de Proveedores y Contratistas
Sancionados de la SFP (con periodo de inhabilitación). Señal fuerte: contrato
firmado <strong>mientras la empresa estaba inhabilitada</strong> para contratar
con el gobierno. {d05_gun} casos detectados 2023–2025.</p>
<div class="wrap">{table("f05_durante_inhabilitacion.csv", 15, cols=["proveedor","rfc","inhabilitado_desde","hasta","fecha_contrato","institucion","tipo_procedimiento","monto_mxn_millones"])}</div>
<p class="caveat">Inhabilitaciones sin fecha de fin (registro abierto) requieren
verificación: pueden reflejar sanciones antiguas o artefactos del registro.</p>

<h2>4 · Conformidad Benford de montos por institución</h2>
<p>Primer dígito de los montos vs. ley de Benford (MAD, bandas de Nigrini;
χ² df=8 de referencia). La cultura de montos redondos también rompe Benford:
esta señal se cruza con las anteriores, no se publica sola. Caso ilustrativo:
exceso de montos que inician con 9 — consistente con fraccionar justo debajo
de umbrales de aprobación.</p>
<div class="wrap">{table("f03_benford_instituciones.csv", 12)}</div>

<h2>Método, fuentes y límites</h2>
<ul class="caveat">
<li>Fuentes oficiales con cadena de evidencia (URL + timestamp + sha256 en <code>data/raw/MANIFEST.tsv</code>); pipeline reproducible (<code>scripts/update.sh</code>).</li>
<li>Montos en MXN; «$XM» = millones de pesos. Otras monedas se reportan por separado en los CSV.</li>
<li>El listado 69-B es un acto administrativo del SAT, impugnable; aquí se reportan hechos publicados, no conclusiones legales.</li>
<li>Cobertura federal (ComprasMX). Estatal/municipal: pendiente — la disolución del INAI (2025) degradó el acceso vía PNT.</li>
<li>Datos del año en curso (2026): el CSV anual aún no se publica; la actualización es anual para contratos y mensual para 69-B.</li>
</ul>
</body></html>"""

(SITE / "index.html").write_text(page, encoding="utf-8")
print(f"wrote {SITE / 'index.html'} ({len(page):,} bytes)")
