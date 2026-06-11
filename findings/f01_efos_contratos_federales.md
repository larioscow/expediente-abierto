# Hallazgo 01 — Contratos federales a empresas del listado 69-B del SAT (2023–2025)

**Fecha de análisis:** 2026-06-10
**Detector:** `detectors/d01_efos_contracts.py`
**Datos:** ComprasMX contratos 2023, 2024, 2025 (403,959 contratos) × Listado completo Art. 69-B CFF del SAT (actualizado 2026-04-30). Procedencia y checksums en `data/raw/MANIFEST.tsv`.

## Qué se midió

Cruce por RFC (exacto, sin coincidencia difusa de nombres) entre los contratos
públicos federales registrados en ComprasMX y el listado del Artículo 69-B del
Código Fiscal de la Federación. El estatus **"Definitivo"** significa que el SAT
publicó que la empresa **factura operaciones inexistentes** (EFOS) y no logró
desvirtuarlo. Las empresas con estatus "Desvirtuado" o "Sentencia Favorable"
fueron **excluidas** del hallazgo principal por haber sido aclaradas o haber
ganado en tribunales; se reportan solo como contexto en los CSV.

## Hallazgo principal

**21 contratos por ~$190.4 millones MXN fueron adjudicados en 2023–2024 a 14
empresas que el SAT publicó posteriormente como EFOS definitivos.**

| Año | Contratos | Empresas | Monto (MXN) |
|---|---|---|---|
| 2023 | 17 | 11 | $179.2M |
| 2024 | 4 | 3 | $11.2M |
| 2025 | 0 | — | — |

**El patrón temporal es el hallazgo estructural:** en el 100% de los casos el
contrato se firmó *antes* de la publicación definitiva en el DOF — la
confirmación llegó 12 a 36 meses después de que las empresas ya habían cobrado
dinero público. En esta ventana no se detectaron pagos *posteriores* a la
confirmación (el bloqueo posterior parece funcionar); **el hueco está en la
detección tardía**, no en el bloqueo. Un sistema que evaluara señales de riesgo
al momento de la adjudicación —empresa de reciente creación, adjudicación
directa, montos atípicos— habría marcado varios de estos casos años antes.

## Casos destacados (hechos verificables, no conclusiones legales)

1. **FERROCLIN U&Q, S.A. DE C.V.** (RFC FUQ140426I3A) recibió de **CONAGUA** un
   contrato por **$156.7M MXN** en marzo de 2023 mediante **"adjudicación
   directa por licitaciones públicas desiertas"**. El SAT la publicó como EFOS
   definitivo el 2026-03-13. Un solo contrato concentra el 82% del monto total
   del hallazgo. *Pendiente: verificación manual del expediente (URL en el CSV
   de detalle).*
2. **CONSTRUCTORA BARLE, S.A. DE C.V.** (RFC CBA220225AL7 — constituida en
   febrero de 2022 según su RFC) ganó contratos del **IMSS** por ~$10M MXN en
   mayo de 2024, además de contratos estatales en 2023. Publicada como EFOS
   definitivo el 2025-12-12: ganó contratos federales ~2 años después de
   constituirse y fue confirmada como facturera ~18 meses más tarde.
3. **CONSTRUAGREGADOS HOPELCHEN, S.A. DE C.V.** (RFC CHO170605TF6): 5 contratos
   con **4 instituciones distintas** (Secretaría de Salud federal, desarrollo
   urbano estatal, municipio de Macuspana, colegio tecnológico) entre 2023 y
   2024. Definitivo el 2026-02-20.

## Distribución por tipo de procedimiento (Definitivos)

12 de 21 contratos (57%) se otorgaron por **adjudicación directa o invitación
restringida**, incluida la modalidad "por licitaciones públicas desiertas" del
caso de mayor monto.

## Método y límites

- **Cruce exacto por RFC** — sin falsos positivos por homonimia. Límite: si el
  RFC en ComprasMX está mal capturado, el contrato no se detecta (subconteo).
- Montos = `Importe DRC` en MXN; contratos en otras monedas se reportan aparte.
- La fecha "definitivo" usa la publicación en DOF (respaldo: página SAT).
- **Lenguaje:** este reporte enuncia hechos publicados por fuentes oficiales
  (ComprasMX, SAT, DOF). No afirma ni implica la comisión de delitos por parte
  de empresas, funcionarios o instituciones. La inclusión en el 69-B es un acto
  administrativo del SAT, impugnable por las empresas.
- Cobertura: solo contratos federales registrados en ComprasMX 2023–2025. No
  incluye 2010–2022 (sistema histórico de CompraNet, siguiente paso) ni
  contrataciones estatales/municipales fuera de ComprasMX.

## Archivos

- `f01_resumen_por_situacion.csv` — totales por estatus 69-B y año
- `f01_top25_definitivos.csv` — los 25 contratos de mayor monto (Definitivos)
- `f01_definitivos_por_procedimiento.csv` — distribución por procedimiento
- `f01_detalle_completo.csv` — 42 filas Definitivo+Presunto con URL del anuncio
  para verificación manual
