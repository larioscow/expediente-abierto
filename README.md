# Expediente Abierto — el motor

Motor de detección detrás de <https://expediente-abierto-six.vercel.app>. Cruza
las compras públicas de México contra registros oficiales de sanción y fraude,
y produce los hallazgos que alimentan el sitio. Cobertura federal (ComprasMX) y
de los 32 estados (Plataforma Nacional de Transparencia).

> **Alcance de este README.** Documenta el *motor*, no el dominio. Qué es una
> facturera, qué dice el art. 50 de la LAASSP o por qué un contrato es señal de
> riesgo se explican en el sitio; aquí solo está la máquina que los detecta:
> capas, módulos, algoritmos y dependencias.
>
> **Cómo está ordenado.** Sigue el método de los *Elementos* de Euclides, pero
> en clave técnica: **definiciones** (el vocabulario del código) → **postulados**
> (los supuestos de ingeniería) → **nociones comunes** (los primitivos
> compartidos que todo detector reusa) → **proposiciones** (los detectores, cada
> uno sobre los anteriores). Nada se afirma sin nombrar la dependencia que lo
> sostiene.

## Estado

Operativo: 12 detectores de lote + riesgo compuesto por proveedor (ensamble) +
backtest de precisión con intervalos de confianza + monitor casi en tiempo real
+ flujo de casos (triaje → denuncia). El 2026-06-11 el pipeline produjo las
primeras 14 denuncias formales presentadas en SIDEC.

---

## 1. Definiciones (el vocabulario del código)

Los términos técnicos que usa el resto del documento.

| Término | Qué es en el código |
|---|---|
| **Capa de lote** | Cruces históricos de alta confianza sobre CSV oficiales descargados. Determinista y reproducible. `detectors/`, orquestado por `scripts/update.sh`. |
| **Capa de tiempo real** | Screen rápido sobre las compras que ComprasMX publica en vivo, capturadas con scrapling. `realtime/`, orquestado por `scripts/realtime_poll.sh`. |
| **Detector** | Un módulo `detectors/dNN_*.py` que lee la vista de contratos, aplica una prueba y escribe un `findings/fNN_*.csv`. |
| **Hallazgo** | El artefacto de salida de un detector: un CSV en `findings/` con nombre, monto y fuente. |
| **Índice** | Estructura en memoria para cruzar en vivo: `efos_index`, `sfp_index`, `dof_index` (nombre/RFC → situación). |
| **Manifiesto** | `data/raw/MANIFEST.tsv`: URL, timestamp y sha256 de cada archivo bajado. La cadena de evidencia del motor. |
| **Ensamble** | Riesgo compuesto por proveedor (`d09`): combina varias señales independientes en un score. |
| **Backtest / lift** | Mide cada señal contra sanciones posteriores. *Lift* = cuántas veces más probable es la sanción dado que la señal disparó. |
| **Frescura** | Edad de cada fuente contra su umbral (`check_freshness.py` → `findings/freshness.json`). |

## 2. Postulados (los supuestos de ingeniería)

Lo que el motor da por sentado, declarado antes de cualquier detector.

1. **Las fuentes son servicios oficiales externos; el motor no crea datos.** Cada
   archivo queda en el manifiesto con su sha256.
2. **La descarga es condicional e idempotente.** `If-Modified-Since`: un 304 no
   vuelve a bajar ~470 MB. El scraping estatal (PNT) es reanudable con escritura
   atómica.
3. **Cruce exacto por RFC sobre coincidencia difusa siempre que se pueda.** El
   feed en vivo solo expone el nombre del proveedor, así que esos cruces se
   etiquetan `needs_verification`; el cruce por RFC corre en el lote.
4. **El puntaje es un filtro, no un veredicto.** Toda señal exige verificación
   humana antes de publicarse, y la herramienta nunca presenta una denuncia.
5. **La ausencia de un dato se reporta, nunca se silencia** (frescura + manifiesto).
6. **scrapling se monta en la autenticación existente del portal** (`capture_xhr`):
   maneja la SPA real y captura las respuestas que la app firma, en lugar de
   romper sus tokens anti-bot.

### Inventario de fuentes (de dónde y cómo se obtienen)

| Fuente | Qué aporta | Acceso |
|---|---|---|
| ComprasMX / CompraNet | contratos federales | CSV anual (lote) + API del portal vía scrapling (vivo) |
| SAT, listado 69-B | lista de EFOS | descarga oficial |
| SFP, directorio de sancionados | inhabilitados con RFC y periodo | API del portal vía scrapling |
| PNT / SIPOT | contrataciones de los 32 estados | scrapling (Cloudflare Turnstile) + export CSV por sujeto obligado |
| DOF | circulares de inhabilitación (alerta temprana) | API abierto |
| CompraNet histórico 2010–2023 | archivo consolidado | datos.gob.mx / ATDT |
| CFE | contratos adjudicados (cobertura parcial) | datos.gob.mx / ATDT |

## 3. Nociones comunes (los primitivos compartidos)

`shared/` reúne lo que todo detector cita, igual que Euclides invoca una noción
común en cada paso. Sin dependencias externas, probado en lockstep en `tests/`.

| Módulo | Qué provee |
|---|---|
| `shared/estadistica.py` | intervalo de Wilson, Fisher exacto de una cola, Benford 1.er/2.º dígito y Z de Nigrini, control de FDR (Benjamini-Hochberg), cola binomial |
| `shared/normalizacion.py` | normalización de razón social para el cruce difuso por nombre |
| `shared/fechas.py` | parseo de fechas y cálculo de ventanas (p. ej. firma dentro de una inhabilitación) |
| `shared/manifiesto.py` | registro de evidencia (URL, timestamp, sha256) |
| `shared/esquemas.py`, `shared/ramos.py` | esquemas de columnas y catálogo de ramos/dependencias |

Regla transversal: un *lift* sin intervalo es media verdad. Cada señal
predictiva se publica con su IC de Wilson y su p de Fisher.

## 4. Proposiciones (los detectores)

Cada detector se apoya en los primitivos y las fuentes anteriores, y va de lo
más cierto (cruce exacto por RFC) a lo más inferido (ensamble, patrones).

| # | Detección | Base técnica / dependencias |
|---|---|---|
| 01 | contratos × lista 69-B, 2023–2025 | cruce exacto por RFC |
| 01h | contratos × 69-B, 2010–2023 | cruce por nombre (`normalizacion`), menor confianza |
| 02 | concentración de adjudicaciones directas | agregación por proveedor/institución + etiquetas de contexto |
| 03 | conformidad Benford por institución | `estadistica` (MAD Nigrini, Z, χ², FDR) |
| 04 | empresas de reciente creación con contratos grandes | edad derivada del RFC + `fechas` |
| 05 | contratos firmados durante inhabilitación SFP | cruce por RFC + ventana de `fechas` |
| 06 | colusión: rotación, anillos de constitución, fraccionamiento mismo día | grafos de coincidencia + `fechas` |
| 07 | convenios sobre el tope legal | aritmética monto final vs original |
| 08 | CFE (fuera de ComprasMX) × 69-B/SFP | cruce por nombre |
| 09 | riesgo compuesto por proveedor (ensamble) | combinación de señales, validado en backtest (lift 5.0) |
| 10 | estatal (PNT) × 69-B/SFP | cruce por RFC + respaldo por nombre etiquetado |
| 11 | amontonamiento bajo umbrales de adjudicación | prueba de signo + FDR (`estadistica`) |
| 12 | Benford estatal por sujeto obligado | misma matemática que 03 |
| BT | backtest: lift de cada señal y del ensamble | IC de Wilson + Fisher exacto |

### Proposiciones en vivo (`realtime/risk.py`)

Puntúa cada procedimiento y adjudicación conforme se publican; el score es la
suma de las banderas, y cada bandera registra por qué surgió el caso.

| Peso | Bandera |
|---|---|
| +8 | inhabilitado SFP que ganó **durante** la inhabilitación · **ganó ya inhabilitado** por circular del DOF aún fuera del directorio |
| +6 | proveedor 69-B definitivo |
| +3 | sancionado SFP · inhabilitación del DOF recién publicada |
| +2 | 69-B presunto · adjudicación directa · plazo recortado · plazo comprimido (<10 días) · emergencia |
| +1 | excepción de ley · anticipo · monto alto (≥ $50M) |

Componentes de la capa: cliente ComprasMX (`comprasmx_client.py`,
`capture_xhr`), índices `efos_index`/`sfp_index`/`dof_index`, poller `poll.py`,
paquetes de verificación `packets.py`, casero persistente `store.py`.

## 5. La demostración (correr y construir)

### Reproducir

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/scrapling install        # navegador para la capa de tiempo real

scripts/update.sh                  # lote: descarga CSV → detectores + backtest → datos del sitio
scripts/realtime_poll.sh           # tiempo real: ComprasMX en vivo → alertas → datos del sitio
```

Pruebas (lógica de cruces, normalización, ventanas, scoring, estadística):

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Resultados en `findings/`.

### Cadena de dependencias del pipeline

Cada paso depende del anterior:

```
descarga (condicional, If-Modified-Since)
  → frescura (check_freshness.py)
    → detectores 01–12 + backtest
      → export_web_data.py  (vuelca a web/src/data/ y web/public/datos/)
        → sitio Next.js (export estático en web/) → Vercel
```

Datos estatales: `scripts/pnt_contratos.py` baja de la PNT por sujeto obligado
(reanudable), y `detectors/pnt.py` normaliza sus ~80 columnas a la misma vista
que los contratos federales (`contracts_pnt`).

## 6. Del hallazgo a la denuncia (`casework/`)

| Componente | Uso |
|---|---|
| `casework/triage.py` | tría todos los hallazgos en presentar / verificar / descartar; `python -m casework.triage scan` |
| `casework/denuncias.py` | borradores/denuncias en Markdown (SIDEC/OIC, ASF, CNA) |
| `casework/pdf.py` | Markdown → PDF formato legal (A4) vía Chromium |
| `casework/dashboard.py` | dashboard local (puerto 8765): casos, estados, PDF |
| `realtime/store.py` | ciclo del caso: nuevo → verificando → verificado → denunciado → publicado / descartado |

**Operación continua.** `scripts/install_launchd.sh` instala dos agentes en la
máquina (la captura scrapling necesita IP residencial):

- `com.expedienteabierto.batch` — diario 07:30: `scripts/publish.sh` (descarga →
  detectores → build → deploy a Vercel).
- `com.expedienteabierto.poll` — cada 30 min: `scripts/realtime_poll.sh` (poll en
  vivo → alertas → despliega solo si los datos exportados cambiaron).

Los workflows de `.github/` (CI de tests, despliegue y refresco diario) quedan
listos pero dormantes hasta que el repo tenga el secret `VERCEL_TOKEN`.

## Principios

1. El puntaje automático es un filtro, no un veredicto: toda señal requiere
   verificación humana antes de publicarse.
2. Cruce exacto (RFC) sobre coincidencia difusa siempre que sea posible.
3. Se excluye del hallazgo principal a las empresas aclaradas (desvirtuado /
   sentencia favorable).
4. Lenguaje de hechos verificables con fuente oficial; sin conclusiones legales.
