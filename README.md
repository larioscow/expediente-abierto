# Expediente Abierto

Cruza las compras del gobierno de México contra los registros oficiales de
sanción y fraude (SAT 69-B, SFP, DOF) y produce los hallazgos que publica
[expediente-abierto-six.vercel.app](https://expediente-abierto-six.vercel.app).
Cobertura federal (ComprasMX) y de los 32 estados (Plataforma Nacional de
Transparencia).

## Estado

12 detectores de lote, riesgo compuesto por proveedor (ensamble), backtest con
intervalos de confianza, monitor casi en tiempo real y flujo de casos (triaje a
denuncia). El 2026-06-11 el pipeline produjo las primeras 14 denuncias
presentadas en SIDEC.

## Definiciones

| Término | En el código |
|---|---|
| Capa de lote | Cruces históricos sobre CSV oficiales. Determinista. `detectors/`, vía `scripts/update.sh`. |
| Capa de tiempo real | Screen sobre lo que ComprasMX publica en vivo, capturado con scrapling. `realtime/`, vía `scripts/realtime_poll.sh`. |
| Detector | Módulo `detectors/dNN_*.py` que lee la vista de contratos, aplica una prueba y escribe `findings/fNN_*.csv`. |
| Hallazgo | El CSV de salida de un detector, con nombre, monto y fuente. |
| Índice | Estructura en memoria para cruzar en vivo: `efos_index`, `sfp_index`, `dof_index`. |
| Manifiesto | `data/raw/MANIFEST.tsv`: URL, timestamp y sha256 de cada archivo bajado. |
| Ensamble | Riesgo compuesto por proveedor (`d09`): varias señales independientes en un score. |
| Lift | Cuántas veces más probable es una sanción posterior dado que la señal disparó. |
| Frescura | Edad de cada fuente contra su umbral (`check_freshness.py`, `findings/freshness.json`). |

## Postulados

1. Las fuentes son servicios oficiales externos; el motor no crea datos. Cada
   archivo queda en el manifiesto con su sha256.
2. La descarga es condicional e idempotente (`If-Modified-Since`: un 304 no
   vuelve a bajar ~470 MB). El scraping estatal es reanudable con escritura atómica.
3. Cruce exacto por RFC sobre coincidencia difusa siempre que se pueda. El feed
   en vivo solo expone el nombre del proveedor, así que esos cruces se etiquetan
   `needs_verification`; el cruce por RFC corre en el lote.
4. El puntaje es un filtro, no un veredicto: toda señal exige verificación
   humana, y el código nunca presenta una denuncia.
5. La ausencia de un dato se reporta, nunca se silencia.
6. scrapling se monta en la autenticación del portal (`capture_xhr`): maneja la
   SPA real y captura las respuestas que la app firma, sin romper sus tokens.

### Fuentes

| Fuente | Aporta | Acceso |
|---|---|---|
| ComprasMX / CompraNet | contratos federales | CSV anual (lote) + API del portal vía scrapling (vivo) |
| SAT, listado 69-B | lista de EFOS | descarga oficial |
| SFP, directorio de sancionados | inhabilitados con RFC y periodo | API del portal vía scrapling |
| PNT / SIPOT | contrataciones de los 32 estados | scrapling (Cloudflare Turnstile) + CSV por sujeto obligado |
| DOF | circulares de inhabilitación (alerta temprana) | API abierto |
| CompraNet histórico 2010–2023 | archivo consolidado | datos.gob.mx / ATDT |
| CFE | contratos adjudicados (cobertura parcial) | datos.gob.mx / ATDT |

## Nociones comunes

`shared/` reúne lo que todo detector reusa. Sin dependencias externas, probado
en lockstep en `tests/`.

| Módulo | Provee |
|---|---|
| `estadistica.py` | Wilson, Fisher exacto de una cola, Benford 1.er/2.º dígito y Z de Nigrini, FDR de Benjamini-Hochberg, cola binomial |
| `normalizacion.py` | normalización de razón social para el cruce difuso por nombre |
| `fechas.py` | parseo de fechas y ventanas (firma dentro de una inhabilitación) |
| `manifiesto.py` | registro de evidencia (URL, timestamp, sha256) |
| `esquemas.py`, `ramos.py` | esquemas de columnas y catálogo de ramos/dependencias |

Un lift sin intervalo es media verdad: cada señal predictiva se publica con su
IC de Wilson y su p de Fisher.

## Proposiciones

Ordenadas de lo más cierto (cruce exacto por RFC) a lo más inferido (ensamble,
patrones).

| # | Detección | Base técnica |
|---|---|---|
| 01 | contratos × lista 69-B, 2023–2025 | cruce exacto por RFC |
| 01h | contratos × 69-B, 2010–2023 | cruce por nombre (`normalizacion`), menor confianza |
| 02 | concentración de adjudicaciones directas | agregación por proveedor/institución |
| 03 | conformidad Benford por institución | `estadistica` (MAD Nigrini, Z, χ², FDR) |
| 04 | reciente creación con contratos grandes | edad derivada del RFC + `fechas` |
| 05 | contratos firmados durante inhabilitación SFP | cruce por RFC + ventana de `fechas` |
| 06 | colusión: rotación, anillos, fraccionamiento mismo día | grafos de coincidencia + `fechas` |
| 07 | convenios sobre el tope legal | aritmética monto final vs original |
| 08 | CFE (fuera de ComprasMX) × 69-B/SFP | cruce por nombre |
| 09 | riesgo compuesto por proveedor | ensamble; validado en backtest (lift 5.0) |
| 10 | estatal (PNT) × 69-B/SFP | cruce por RFC + respaldo por nombre etiquetado |
| 11 | amontonamiento bajo umbrales | prueba de signo + FDR |
| 12 | Benford estatal por sujeto obligado | misma matemática que 03 |
| BT | backtest: lift de cada señal y del ensamble | IC de Wilson + Fisher exacto |

### En vivo (`realtime/risk.py`)

El score de cada procedimiento es la suma de sus banderas; cada bandera registra
por qué surgió el caso.

| Peso | Bandera |
|---|---|
| +8 | inhabilitado SFP que ganó durante la inhabilitación · ganó ya inhabilitado por circular del DOF, aún fuera del directorio |
| +6 | proveedor 69-B definitivo |
| +3 | sancionado SFP · inhabilitación del DOF recién publicada |
| +2 | 69-B presunto · adjudicación directa · plazo recortado · plazo comprimido (<10 días) · emergencia |
| +1 | excepción de ley · anticipo · monto alto (≥ $50M) |

Capa en vivo: cliente ComprasMX (`comprasmx_client.py`, `capture_xhr`), índices
`efos_index`/`sfp_index`/`dof_index`, poller `poll.py`, paquetes de verificación
`packets.py`, casero persistente `store.py`.

## Correr

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/scrapling install        # navegador para la capa de tiempo real

scripts/update.sh                  # lote: descarga CSV, detectores + backtest, datos del sitio
scripts/realtime_poll.sh           # vivo: ComprasMX en vivo, alertas, datos del sitio
```

Pruebas:

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Pipeline, cada paso depende del anterior:

```
descarga (condicional) → frescura → detectores 01–12 + backtest
  → export_web_data.py → sitio Next.js (web/) → Vercel
```

Datos estatales: `scripts/pnt_contratos.py` baja de la PNT por sujeto obligado
(reanudable), y `detectors/pnt.py` normaliza sus ~80 columnas a la misma vista
que los contratos federales.

## Casework

| Componente | Uso |
|---|---|
| `casework/triage.py` | tría hallazgos en presentar / verificar / descartar; `python -m casework.triage scan` |
| `casework/denuncias.py` | borradores en Markdown (SIDEC/OIC, ASF, CNA) |
| `casework/pdf.py` | Markdown a PDF formato legal (A4) vía Chromium |
| `casework/dashboard.py` | dashboard local (puerto 8765): casos, estados, PDF |
| `realtime/store.py` | ciclo del caso: nuevo → verificando → verificado → denunciado → publicado / descartado |

Operación continua: `scripts/install_launchd.sh` instala dos agentes en la
máquina (la captura scrapling necesita IP residencial). `com.expedienteabierto.batch`
corre diario 07:30 (`scripts/publish.sh`); `com.expedienteabierto.poll` cada 30
min (`scripts/realtime_poll.sh`, despliega solo si los datos exportados cambiaron).
Los workflows de `.github/` quedan dormantes hasta que el repo tenga el secret
`VERCEL_TOKEN`.

## Principios

1. El puntaje automático es un filtro, no un veredicto: toda señal requiere
   verificación humana antes de publicarse.
2. Cruce exacto (RFC) sobre coincidencia difusa siempre que sea posible.
3. Se excluye del hallazgo principal a las empresas aclaradas (desvirtuado /
   sentencia favorable).
4. Lenguaje de hechos verificables con fuente oficial; sin conclusiones legales.
