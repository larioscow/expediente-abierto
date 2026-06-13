# mx-corruption-detector

Detección de señales de riesgo de corrupción en contrataciones públicas
mexicanas, con datos oficiales y metodología reproducible. Publica hechos
verificables, nunca acusaciones.

## Estado

Operativo: 12 detectores batch + riesgo compuesto por proveedor (ensamble) +
backtest de precisión con intervalos de confianza + monitor casi en tiempo
real + flujo de casos (verificación → denuncia). Cobertura federal (ComprasMX)
y estatal/municipal (los 32 estados vía la Plataforma Nacional de
Transparencia). El 2026-06-11 se presentaron las primeras 14 denuncias
formales en SIDEC a partir de hallazgos del pipeline (contratos firmados
durante inhabilitación vigente, cruce por RFC).

## Reproducir

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/scrapling install  # navegador para la capa de tiempo real

scripts/update.sh        # lote: descarga CSVs -> detectores + backtest -> sitio
scripts/realtime_poll.sh # tiempo real: consulta ComprasMX en vivo -> alertas -> sitio
```

Pruebas (lógica de cruces, normalización de nombres, ventanas de
inhabilitación, scoring):

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Resultados en `findings/`. Cada archivo fuente queda registrado en
`data/raw/MANIFEST.tsv` (URL, timestamp, sha256) como cadena de evidencia.

## Dos capas

**Lote (histórico, alta confianza).** CSVs oficiales (ComprasMX anual + 69-B +
CompraNet histórico 2010–2023). Cruce exacto por RFC, edad de empresa derivada
del RFC, Benford. Frescura: contratos por año vencido; 69-B mensual. La
descarga es condicional (If-Modified-Since: un 304 no re-baja ~470 MB), los
años de contratos son dinámicos (2023..año en curso; el portal publica el CSV
anual con rezago — su ausencia se reporta, nunca se silencia) y
`scripts/check_freshness.py` alarma si alguna fuente envejece más allá de su
umbral (`findings/freshness.json`).

**Tiempo real (en vivo, screen rápido).** `realtime/poll.py` consulta el portal
ComprasMX en vivo vía **scrapling** (`capture_xhr`): en lugar de romper los
tokens anti-bot del sitio, maneja la SPA real y captura las respuestas de las
llamadas que la propia app firma — se monta en la autenticación existente.
Pagina el listado (`--pages`, 3×100 filas por poll) para que una ráfaga de
publicaciones no se escape entre polls. Marca procedimientos/adjudicaciones de
riesgo conforme se publican, incluida una **alerta temprana del DOF**: las
inhabilitaciones surten efecto al publicarse en el Diario Oficial, días antes
de aparecer en el directorio de sancionados; `realtime/dof_index.py` baja esas
circulares y marca a un ganador recién inhabilitado que el directorio aún no
refleja. Limitación honesta: el feed en vivo expone nombre del proveedor (no
RFC) → cruce 69-B por nombre (verificar); el cruce por RFC y la edad corren en
el lote.

**Datos estatales (PNT, lote).** El dinero estatal y municipal no pasa por
ComprasMX. `scripts/pnt_contratos.py` baja de la Plataforma Nacional de
Transparencia (obligación art. 70 fr. XXVIII) los resultados de procedimientos
de los 32 estados, por sujeto obligado, de forma reanudable (manifiesto +
escritura atómica). `detectors/pnt.py` normaliza esas ~80 columnas a la misma
vista que los contratos federales (`contracts_pnt`) y `detectors/d10` los cruza
contra 69-B y SFP por RFC (con respaldo por razón social etiquetado aparte: la
calidad del RFC capturado va de 45 % a 86 % según el estado).

## Fuentes (servicios existentes, no creados por nosotros)

- **ComprasMX / CompraNet** — contratos federales. CSV anual (lote) + API en vivo
  del portal capturada vía scrapling (tiempo real).
- **SAT, listado Art. 69-B CFF** — empresas que facturan operaciones inexistentes
  (EFOS): presuntos, desvirtuados, definitivos, sentencia favorable.
- **SFP, Directorio de Proveedores y Contratistas Sancionados** — proveedores
  inhabilitados con RFC y periodo de inhabilitación (API del portal vía scrapling).
- **Plataforma Nacional de Transparencia (PNT / SIPOT)** — contrataciones de los
  32 estados y municipios (obligación art. 70 fr. XXVIII), la única ruta común a
  todo el dinero estatal. Acceso vía scrapling (Cloudflare Turnstile) + export
  CSV por sujeto obligado.
- **Diario Oficial de la Federación (DOF)** — circulares de inhabilitación
  ("abstenerse de … celebrar contratos con …"), vía su API abierto. Alerta
  temprana: la inhabilitación es efectiva al publicarse, antes del directorio.
- **CompraNet histórico 2010–2023** — archivo consolidado (datos.gob.mx / ATDT).
- **CFE, contratos adjudicados** — dataset oficial (datos.gob.mx / ATDT). CFE y
  Pemex contratan FUERA de ComprasMX; este dataset cubre solo una fracción del
  volumen real. Pendiente: histórico completo de msc.cfe.mx y Pemex (EBDI no
  publica contratos en formato máquina); recuperación de RFC vía RUPC (el
  portal no expone búsqueda capturable sin automatización de UI dedicada).

## Detectores

| # | Señal | Estado |
|---|---|---|
| 01 | Contratos a empresas 69-B, 2023–2025 (cruce exacto por RFC) | ✅ |
| 01h | Contratos a empresas 69-B, 2010–2023 (nombre normalizado, menor confianza) | ✅ |
| 02 | Concentración de adjudicaciones directas (proveedor / institución / dependencia) con etiquetas de contexto | ✅ |
| 03 | Conformidad Benford de montos por institución (MAD Nigrini 1.er y 2.º dígito, Z por dígito, χ², control de FDR) | ✅ |
| 04 | Empresas de reciente creación ganando contratos grandes (edad derivada del RFC) | ✅ |
| 05 | Contratos a proveedores inhabilitados por la SFP (cruce por RFC; firmados durante inhabilitación) | ✅ |
| 06 | Colusión: rotación de licitaciones en grupos cerrados, anillos de constitución, fraccionamiento mismo día | ✅ |
| 07 | Convenios modificatorios sobre el tope legal (LAASSP +20% / LOPSRM +25%) | ✅ |
| 08 | CFE (fuera de ComprasMX): contratos adjudicados publicados × 69-B/SFP por nombre | ✅ |
| 09 | Riesgo compuesto por proveedor: ensamble de señales predictivas distintas (validado en el backtest: lift 5.0) | ✅ |
| 10 | Estatal (PNT): contratos de los 32 estados × 69-B/SFP por RFC, con respaldo por nombre etiquetado | ✅ |
| 11 | Amontonamiento bajo umbrales: exceso de montos justo bajo los topes de adjudicación (prueba de signo + FDR) | ✅ |
| 12 | Benford estatal: conformidad de montos por sujeto obligado (PNT), misma matemática que 03 | ✅ |
| BT | Backtest: lift de cada señal y del ensamble contra sanciones posteriores (69-B/SFP), con IC de Wilson y Fisher exacto | ✅ |

La estadística forense vive en `shared/estadistica.py` (sin dependencias):
intervalo de Wilson, Fisher exacto de una cola, Benford 1.er/2.º dígito y Z de
Nigrini, control de FDR de Benjamini-Hochberg, cola binomial — toda probada en
lockstep en `tests/`. Un *lift* sin intervalo es media verdad: cada señal
predictiva se publica con su IC y su p de Fisher.

## Realtime (en vivo)

| Componente | Archivo |
|---|---|
| Cliente ComprasMX (scrapling capture_xhr) | `realtime/comprasmx_client.py` |
| Índice 69-B por nombre normalizado | `realtime/efos_index.py` |
| Índice SFP (RFC + nombre + inhabilitación) | `realtime/sfp_index.py` |
| Índice DOF (circulares de inhabilitación, alerta temprana) | `realtime/dof_index.py` |
| Reglas de riesgo (procedimiento + adjudicación) | `realtime/risk.py` |
| Poller con estado y alertas | `realtime/poll.py` |
| Paquetes de verificación por alerta (evidencia + checklist) | `realtime/packets.py` |
| Casero persistente (estados: nuevo→verificando→verificado→denunciado→publicado/descartado) | `realtime/store.py` |
| Borradores de denuncia formal (SIDEC/OIC, ASF, CNA) | `casework/denuncias.py` — `python -m casework.denuncias` |
| Runner para cron | `scripts/realtime_poll.sh` |

Señales en vivo (pesos de riesgo): proveedor inhabilitado SFP **durante** la
inhabilitación (+8), **ganó ya inhabilitado por circular del DOF** aún fuera del
directorio (+8), proveedor 69-B definitivo (+6), 69-B presunto (+2), proveedor
sancionado SFP (+3), inhabilitación del DOF recién publicada (+3), adjudicación
directa (+2), **plazo recortado** (+2), **plazo comprimido calculado** (<10 días
convocatoria→apertura en licitación, +2), contratación de emergencia (+2),
excepción de ley (+1), anticipo (+1), monto alto (+1). El score es la suma de
banderas; cada bandera explica por qué surgió el caso. Los procedimientos
estatales/municipales con recursos federales (orden GEM) se etiquetan con su
entidad. Estado en `data/state/seen.json`; alertas en `findings/alerts.jsonl`.

## Casework (del hallazgo a la denuncia)

| Componente | Uso |
|---|---|
| `casework/denuncias.py` | borradores/denuncias en Markdown (SIDEC/OIC por caso, ASF y CNA consolidadas); `--verificado RFC=fecha` produce versión presentable |
| `casework/pdf.py` | Markdown → PDF formato legal (Arial 12, A4) vía Chromium; `python -m casework.pdf` |
| `casework/dashboard.py` | dashboard local (`python -m casework.dashboard`, puerto 8765): casos, estados, generación de PDF |
| `realtime/store.py` | estados del ciclo: nuevo → verificando → verificado → denunciado → publicado / descartado |

## Tracker

`scripts/update.sh` corre el lote completo (descarga → frescura → detectores →
`scripts/export_web_data.py`, que vuelca los hallazgos a `web/src/data/` y
`web/public/datos/`); `scripts/realtime_poll.sh` corre la capa en vivo. El
sitio es una app Next.js de exportación estática en `web/` (una página por
tipo de evidencia, en español), publicada en **Vercel**
(<https://expediente-abierto-six.vercel.app>).

**Operación continua.** `scripts/install_launchd.sh` instala dos agentes
launchd en esta máquina (la captura scrapling necesita IP residencial):

- `com.expedienteabierto.batch` — diario 07:30: `scripts/publish.sh`
  (descarga → detectores → build → deploy a Vercel).
- `com.expedienteabierto.poll` — cada 30 min: `scripts/realtime_poll.sh`
  (poll en vivo → alertas → **despliega solo si los datos exportados
  cambiaron**, huella en `data/state/web_data.sha`).

Logs en `data/state/logs/`. Los workflows de `.github/` (CI de tests,
despliegue y refresco diario de datos) quedan listos pero dormantes hasta que
el repo tenga remoto en GitHub + secret `VERCEL_TOKEN`.

## Principios

1. El puntaje automático es un filtro, no un veredicto — toda señal requiere
   verificación humana antes de publicarse.
2. Cruce exacto (RFC) sobre coincidencia difusa siempre que sea posible.
3. Se excluye del hallazgo principal a empresas aclaradas (Desvirtuado /
   Sentencia Favorable).
4. Lenguaje de hechos verificables con fuente oficial; sin conclusiones legales.
