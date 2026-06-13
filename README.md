# Expediente Abierto

Detector de corrupción en las compras del gobierno de México. Publica hechos
verificables con fuente oficial, nunca acusaciones. Cobertura federal
(ComprasMX) y de los 32 estados (Plataforma Nacional de Transparencia).

Sitio: <https://expediente-abierto-six.vercel.app> · Nombre clave del repo:
`mx-corruption-detector`.

> **Cómo está ordenado este documento.** Sigue el método de los *Elementos* de
> Euclides: primero las **definiciones**, luego los **postulados** (los
> supuestos, puestos a la vista antes de cualquier afirmación), luego las
> **nociones comunes** (las reglas legales que se citan una y otra vez), y al
> final las **proposiciones** (los detectores), cada una apoyada en lo anterior
> y citando la regla que la justifica. Nada se afirma; todo se demuestra y se
> cita.

## Estado

Operativo: 12 detectores de lote + riesgo compuesto por proveedor (ensamble) +
backtest de precisión con intervalos de confianza + monitor casi en tiempo
real + flujo de casos (verificación → denuncia). El 2026-06-11 se presentaron
las primeras 14 denuncias formales en SIDEC a partir de hallazgos del pipeline
(contratos firmados durante una inhabilitación vigente, cruce por RFC).

---

## 1. Definiciones

Los términos que usa todo lo demás. Ninguno se emplea antes de quedar aquí
definido.

| Término | Definición |
|---|---|
| **EFOS / facturera** | Empresa que el SAT incluye en su lista del art. 69-B del Código Fiscal por facturar operaciones que no existen. Cuatro situaciones: *presunto*, *definitivo* (confirmado), *desvirtuado* y *sentencia favorable* (aclarados). |
| **Inhabilitado** | Proveedor al que la autoridad le prohibió contratar con el gobierno por un periodo; consta en el directorio de sancionados de la SFP o en una circular del DOF. |
| **Adjudicación directa** | Contrato otorgado a un solo proveedor sin licitación. La ley la admite como excepción, no como vía ordinaria. |
| **Convenio modificatorio** | Documento que aumenta el monto o el plazo de un contrato ya firmado. |
| **Colusión** | Empresas que aparentan competir pero se reparten los contratos de una misma oficina (rotación, anillos de constitución, fraccionamiento el mismo día). |
| **Señal (bandera)** | Una regla con nombre y peso que un contrato dispara. Un filtro para revisar, no una acusación. |
| **Hallazgo** | El resultado de un detector: una tabla en `findings/` con nombre, monto y fuente. |
| **Lote / tiempo real** | *Lote* = cruces históricos de alta confianza sobre CSV oficiales. *Tiempo real* = screen rápido sobre las compras que se publican en vivo. |
| **PNT / SIPOT** | Plataforma Nacional de Transparencia: la única ruta común a las contrataciones de los 32 estados y municipios. |

## 2. Postulados (los supuestos, a la vista)

Lo que el sistema da por sentado, declarado antes de cualquier hallazgo.

1. **Todo se construye sobre servicios oficiales que ya existen; no creamos
   datos.** Cada fuente se registra en `data/raw/MANIFEST.tsv` (URL, timestamp,
   sha256) como cadena de evidencia.
2. **El puntaje automático es un filtro, no un veredicto.** Toda señal exige
   verificación humana antes de publicarse.
3. **Un humano denuncia.** La herramienta tría, puntúa y redacta el documento;
   nunca presenta nada ante una autoridad.
4. **Cruce exacto por RFC sobre coincidencia difusa siempre que se pueda.** El
   feed en vivo solo expone el *nombre* del proveedor, no su RFC, así que esos
   cruces quedan marcados como *por verificar*; el cruce por RFC corre en el lote.
5. **La ausencia de un dato se reporta, nunca se silencia.**
   `scripts/check_freshness.py` alarma si una fuente envejece más allá de su
   umbral (`findings/freshness.json`).

### Fuentes (los postulados, una por una)

- **ComprasMX / CompraNet** — contratos federales. CSV anual (lote) + API en vivo
  del portal capturada vía scrapling (tiempo real).
- **SAT, listado art. 69-B CFF** — empresas que facturan operaciones inexistentes
  (presuntos, desvirtuados, definitivos, sentencia favorable).
- **SFP, Directorio de Proveedores y Contratistas Sancionados** — inhabilitados
  con RFC y periodo de inhabilitación (API del portal vía scrapling).
- **Plataforma Nacional de Transparencia (PNT / SIPOT)** — contrataciones de los
  32 estados y municipios (obligación art. 70 fr. XXVIII de la LGTAIP).
- **Diario Oficial de la Federación (DOF)** — circulares de inhabilitación, vía su
  API abierto. Alerta temprana: la inhabilitación surte efectos al publicarse,
  días antes de aparecer en el directorio.
- **CompraNet histórico 2010–2023** — archivo consolidado (datos.gob.mx / ATDT).
- **CFE, contratos adjudicados** — dataset oficial (datos.gob.mx / ATDT). CFE y
  Pemex contratan fuera de ComprasMX; este dataset cubre solo una fracción del
  volumen real.

## 3. Nociones comunes (las reglas que se citan)

Las reglas legales que las proposiciones invocan, igual que Euclides cita una
noción común en cada paso de una demostración.

| Regla | Qué fija |
|---|---|
| **CFF art. 69-B** | La lista del SAT de operaciones simuladas (EFOS). |
| **LAASSP art. 50** | Prohíbe dar contratos a una empresa inhabilitada. |
| **LGRA art. 59** | Sanciona al servidor público que autoriza ese contrato. |
| **LAASSP art. 52 / LOPSRM art. 59** | Tope de un convenio: +20 % en adquisiciones, +25 % en obra. |
| **LAASSP art. 32** | Plazo de una licitación pública: ≥15 días entre convocatoria y apertura (reducible a ≥10 con justificación). |
| **LAASSP arts. 1 y 41** | La adjudicación directa es una excepción acotada, no la regla. |
| **LGTAIP art. 70 fr. XXVIII** | Obliga a publicar las contrataciones: la ruta de los datos estatales. |

## 4. Proposiciones (los detectores)

Cada detector se apoya en las definiciones y las nociones comunes anteriores, y
va de lo más cierto (cruce exacto por RFC) a lo más inferido (ensamble,
patrones estadísticos).

| # | Señal | Regla / base |
|---|---|---|
| 01 | Contratos a empresas 69-B, 2023–2025 (cruce exacto por RFC) | CFF 69-B |
| 01h | Contratos a empresas 69-B, 2010–2023 (nombre normalizado, menor confianza) | CFF 69-B |
| 02 | Concentración de adjudicaciones directas (proveedor / institución / dependencia) | LAASSP 1 y 41 |
| 03 | Conformidad Benford de montos por institución (MAD Nigrini 1.er y 2.º dígito, Z, χ², control de FDR) | estadística |
| 04 | Empresas de reciente creación ganando contratos grandes (edad derivada del RFC) | LAASSP 1 y 41 |
| 05 | Contratos a inhabilitados por la SFP, firmados durante la inhabilitación (cruce por RFC) | LAASSP 50 · LGRA 59 |
| 06 | Colusión: rotación en grupos cerrados, anillos de constitución, fraccionamiento mismo día | patrón |
| 07 | Convenios modificatorios sobre el tope legal | LAASSP 52 · LOPSRM 59 |
| 08 | CFE (fuera de ComprasMX): contratos adjudicados × 69-B/SFP por nombre | CFF 69-B · LAASSP 50 |
| 09 | Riesgo compuesto por proveedor: ensamble de señales distintas (validado en backtest: lift 5.0) | estadística |
| 10 | Estatal (PNT): contratos de los 32 estados × 69-B/SFP por RFC, con respaldo por nombre etiquetado | CFF 69-B · LAASSP 50 |
| 11 | Amontonamiento bajo umbrales: exceso de montos justo bajo los topes (prueba de signo + FDR) | LAASSP 1 y 41 |
| 12 | Benford estatal: conformidad de montos por sujeto obligado (PNT) | estadística |
| BT | Backtest: lift de cada señal y del ensamble contra sanciones posteriores, con IC de Wilson y Fisher exacto | estadística |

La estadística forense vive en `shared/estadistica.py` (sin dependencias):
intervalo de Wilson, Fisher exacto de una cola, Benford 1.er/2.º dígito y Z de
Nigrini, control de FDR de Benjamini-Hochberg, cola binomial. Toda probada en
lockstep en `tests/`. Un *lift* sin intervalo es media verdad: cada señal
predictiva se publica con su IC y su p de Fisher.

### Proposiciones en vivo (monitor de señales)

`realtime/risk.py` puntúa cada procedimiento y adjudicación conforme se
publican. El score es la suma de las banderas; cada bandera explica por qué
surgió el caso.

| Peso | Bandera |
|---|---|
| +8 | Inhabilitado SFP que ganó **durante** la inhabilitación |
| +8 | **Ganó ya inhabilitado** por circular del DOF, aún fuera del directorio |
| +6 | Proveedor 69-B **definitivo** |
| +3 | Sancionado SFP · inhabilitación del DOF recién publicada |
| +2 | 69-B presunto · adjudicación directa · plazo recortado · plazo comprimido (<10 días) · emergencia |
| +1 | Excepción de ley · anticipo · monto alto (≥ $50M) |

Componentes: cliente ComprasMX (`comprasmx_client.py`, scrapling
`capture_xhr`), índices `efos_index` / `sfp_index` / `dof_index`, poller
`poll.py`, paquetes de verificación `packets.py`, casero persistente `store.py`.

## 5. La demostración (cómo se construye y se corre)

### Reproducir

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/scrapling install        # navegador para la capa de tiempo real

scripts/update.sh                  # lote: descarga CSV → detectores + backtest → sitio
scripts/realtime_poll.sh           # tiempo real: ComprasMX en vivo → alertas → sitio
```

Pruebas (lógica de cruces, normalización de nombres, ventanas de
inhabilitación, scoring):

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Resultados en `findings/`.

### La cadena de dependencias del pipeline

Igual que la proposición 47 de Euclides se apoya en la 41, la 37, la 35… hasta
las definiciones, cada paso del pipeline depende del anterior:

```
descarga (condicional, If-Modified-Since)
  → frescura (check_freshness.py)
    → detectores 01–12 + backtest
      → export_web_data.py  (vuelca a web/src/data/ y web/public/datos/)
        → sitio Next.js (export estático en web/) → Vercel
```

El lote cruza por RFC exacto y deriva la edad de la empresa del propio RFC. El
tiempo real maneja la SPA real de ComprasMX y captura las respuestas que la
app firma, en lugar de romper sus tokens anti-bot. Los datos estatales bajan de
la PNT (`scripts/pnt_contratos.py`, reanudable) y `detectors/pnt.py` normaliza
sus ~80 columnas a la misma vista que los contratos federales.

## 6. Del hallazgo a la denuncia

| Componente | Uso |
|---|---|
| `casework/triage.py` | tría todos los hallazgos (federal + estatal) en presentar / verificar / descartar; `python -m casework.triage scan` |
| `casework/denuncias.py` | borradores/denuncias en Markdown (SIDEC/OIC por caso, ASF y CNA consolidadas) |
| `casework/pdf.py` | Markdown → PDF formato legal (A4) vía Chromium |
| `casework/dashboard.py` | dashboard local (puerto 8765): casos, estados, generación de PDF |
| `realtime/store.py` | ciclo del caso: nuevo → verificando → verificado → denunciado → publicado / descartado |

**Operación continua.** `scripts/install_launchd.sh` instala dos agentes en la
máquina (la captura scrapling necesita IP residencial):

- `com.expedienteabierto.batch` — diario 07:30: `scripts/publish.sh` (descarga →
  detectores → build → deploy a Vercel).
- `com.expedienteabierto.poll` — cada 30 min: `scripts/realtime_poll.sh` (poll en
  vivo → alertas → despliega solo si los datos exportados cambiaron).

Los workflows de `.github/` (CI de tests, despliegue y refresco diario de datos)
quedan listos pero dormantes hasta que el repo tenga remoto y el secret
`VERCEL_TOKEN`.

## Principios

1. El puntaje automático es un filtro, no un veredicto: toda señal requiere
   verificación humana antes de publicarse.
2. Cruce exacto (RFC) sobre coincidencia difusa siempre que sea posible.
3. Se excluye del hallazgo principal a las empresas aclaradas (desvirtuado /
   sentencia favorable).
4. Lenguaje de hechos verificables con fuente oficial; sin conclusiones legales.
