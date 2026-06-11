# mx-corruption-detector

Detección de señales de riesgo de corrupción en contrataciones públicas
mexicanas, con datos oficiales y metodología reproducible. Publica hechos
verificables, nunca acusaciones.

## Estado

Spike inicial (semana 1): detector 01 funcionando sobre ComprasMX 2023–2025.
Ver [findings/f01_efos_contratos_federales.md](findings/f01_efos_contratos_federales.md).

## Reproducir

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install "scrapling[fetchers]" && .venv/bin/scrapling install  # navegador para tiempo real

scripts/update.sh        # lote: descarga CSVs -> 5 detectores -> sitio
scripts/realtime_poll.sh # tiempo real: consulta ComprasMX en vivo -> alertas -> sitio
```

Resultados en `findings/`. Cada archivo fuente queda registrado en
`data/raw/MANIFEST.tsv` (URL, timestamp, sha256) como cadena de evidencia.

## Dos capas

**Lote (histórico, alta confianza).** CSVs oficiales (ComprasMX anual + 69-B +
CompraNet histórico 2010–2023). Cruce exacto por RFC, edad de empresa derivada
del RFC, Benford. Frescura: contratos por año vencido; 69-B mensual.

**Tiempo real (en vivo, screen rápido).** `realtime/poll.py` consulta el portal
ComprasMX en vivo vía **scrapling** (`capture_xhr`): en lugar de romper los
tokens anti-bot del sitio, maneja la SPA real y captura las respuestas de las
llamadas que la propia app firma — se monta en la autenticación existente. Marca
procedimientos/adjudicaciones de riesgo conforme se publican. Limitación honesta:
el feed en vivo expone nombre del proveedor (no RFC) → cruce 69-B por nombre
(verificar); el cruce por RFC y la edad corren en el lote.

## Fuentes (servicios existentes, no creados por nosotros)

- **ComprasMX / CompraNet** — contratos federales. CSV anual (lote) + API en vivo
  del portal capturada vía scrapling (tiempo real).
- **SAT, listado Art. 69-B CFF** — empresas que facturan operaciones inexistentes
  (EFOS): presuntos, desvirtuados, definitivos, sentencia favorable.
- **SFP, Directorio de Proveedores y Contratistas Sancionados** — proveedores
  inhabilitados con RFC y periodo de inhabilitación (API del portal vía scrapling).
- **CompraNet histórico 2010–2023** — archivo consolidado (datos.gob.mx / ATDT).

## Detectores

| # | Señal | Estado |
|---|---|---|
| 01 | Contratos a empresas 69-B, 2023–2025 (cruce exacto por RFC) | ✅ |
| 01h | Contratos a empresas 69-B, 2010–2023 (nombre normalizado, menor confianza) | ✅ |
| 02 | Concentración de adjudicaciones directas (proveedor / institución / dependencia) con etiquetas de contexto | ✅ |
| 03 | Conformidad Benford de montos por institución (MAD Nigrini + χ²) | ✅ |
| 04 | Empresas de reciente creación ganando contratos grandes (edad derivada del RFC) | ✅ |
| 05 | Contratos a proveedores inhabilitados por la SFP (cruce por RFC; firmados durante inhabilitación) | ✅ |

## Realtime (en vivo)

| Componente | Archivo |
|---|---|
| Cliente ComprasMX (scrapling capture_xhr) | `realtime/comprasmx_client.py` |
| Índice 69-B por nombre normalizado | `realtime/efos_index.py` |
| Índice SFP (RFC + nombre + inhabilitación) | `realtime/sfp_index.py` |
| Reglas de riesgo (procedimiento + adjudicación) | `realtime/risk.py` |
| Poller con estado y alertas | `realtime/poll.py` |
| Runner para cron | `scripts/realtime_poll.sh` |

Señales en vivo (pesos de riesgo): proveedor inhabilitado SFP **durante** la
inhabilitación (+8), proveedor 69-B definitivo (+6), proveedor sancionado SFP
(+3), adjudicación directa (+2), **plazo recortado** (+2), contratación de
emergencia (+2), excepción de ley (+1), monto alto (+1). El score es la suma de
banderas; cada bandera explica por qué surgió el caso. Estado en
`data/state/seen.json`; alertas en `findings/alerts.jsonl`.

## Tracker

`scripts/update.sh` corre el lote completo (descarga → detectores → sitio);
`scripts/realtime_poll.sh` corre la capa en vivo. Ambos regeneran
`site/index.html` — página estática en español con cifras, tablas y método.

## Principios

1. El puntaje automático es un filtro, no un veredicto — toda señal requiere
   verificación humana antes de publicarse.
2. Cruce exacto (RFC) sobre coincidencia difusa siempre que sea posible.
3. Se excluye del hallazgo principal a empresas aclaradas (Desvirtuado /
   Sentencia Favorable).
4. Lenguaje de hechos verificables con fuente oficial; sin conclusiones legales.
