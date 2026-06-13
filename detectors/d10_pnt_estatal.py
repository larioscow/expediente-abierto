#!/usr/bin/env python
"""Detector 10 — contratos ESTATALES (PNT fr. XXVIII) a factureras 69-B y a
proveedores inhabilitados, cruce por RFC.

El dinero estatal no pasa por ComprasMX: viene de la PNT (contracts_pnt).
La calidad del RFC varía por estado (45-86% válido), así que el cruce
principal exige RFC válido y el respaldo por razón social sale en archivo
APARTE etiquetado como pendiente de verificación — jamás se mezclan.
Los montos del formato traen capturas absurdas: se reporta el monto crudo
y un flag de plausibilidad; las sumas headline usan solo montos plausibles.

Usage: python -m detectors.d10_pnt_estatal [pnt_*.csv ...]
"""
import sys

import duckdb
import pandas as pd

from detectors.common import OUT, load_sfp_views, load_views
from detectors.d06_colusion import widest_incorporation_run
from detectors.pnt import PROVEEDOR_PLAUSIBLE, load_pnt_views
from shared.normalizacion import sql_name_norm

# anillo de constitución: empresas "competidoras" en un mismo sujeto obligado
# constituidas con pocos días de diferencia (red de cascarones coordinada).
# El sujeto obligado es un comprador amplio (no una unidad compradora fina
# como en el nivel federal), así que sin un piso de PROPORCIÓN un comprador
# enorme dispara la señal por azar (31 de 5000 empresas constituidas en
# cualquier ventana de 30 días). Se exige que el anillo sea una fracción
# significativa de los proveedores persona-moral del sujeto.
ANILLO_VENTANA_DIAS = 30
ANILLO_MIN_EMPRESAS = 3
ANILLO_MIN_SHARE = 0.25   # el anillo es >=25% de los proveedores del sujeto

# moneda del formato: MXN implícito cuando viene vacía
MXN_PNT = ("(moneda IS NULL OR upper(moneda) LIKE '%PESO%' "
           "OR upper(moneda) = 'MXN')")
# tope de plausibilidad por contrato estatal: 5,000 millones MXN
IMPORTE_OK = f"(importe IS NOT NULL AND importe BETWEEN 1 AND 5e9 AND {MXN_PNT})"
# empresa joven y contrato grande, igual criterio que d04 federal
MAX_EDAD_DIAS = 365
MIN_JOVEN_MXN = 5_000_000
# concentración de directas a un solo proveedor dentro de un sujeto obligado
# (umbrales menores que d02 federal: los sujetos estatales son más chicos)
CONC_MIN_GASTO = 10_000_000   # gasto directo total del sujeto obligado
CONC_MIN_DIRECTAS = 15        # número de adjudicaciones directas del sujeto
CONC_MIN_SHARE = 0.5          # fracción que concentra el proveedor


def consultas(con) -> dict:
    """Las cuatro tablas del detector sobre vistas ya cargadas (contracts_pnt,
    efos, sfp). Separado de main() para poder probarse con fixtures."""
    def q(sql):
        return con.execute(sql).fetchdf()

    cobertura = q(f"""
    SELECT estado_comprador, ejercicio, count(*) AS contratos,
      round(100.0 * count(*) FILTER (rfc_valido) / count(*), 1) AS pct_rfc_valido,
      round(100.0 * count(fecha_efectiva) / count(*), 1) AS pct_con_fecha,
      round(sum(importe) FILTER ({IMPORTE_OK}) / 1e6, 1) AS monto_mxn_millones,
      count(DISTINCT id_sujeto) AS sujetos_obligados
    FROM contracts_pnt GROUP BY 1, 2 ORDER BY 1, 2""")

    efos = q(f"""
    SELECT c.estado_comprador, c.sujeto_obligado, c.proveedor,
      c.rfc_norm AS rfc, e.situacion,
      strftime(e.fecha_definitivo, '%Y-%m-%d') AS definitivo_dof,
      strftime(c.fecha_efectiva, '%Y-%m-%d') AS fecha_contrato,
      c.fecha_efectiva IS NOT NULL AND e.fecha_definitivo IS NOT NULL
        AND c.fecha_efectiva > e.fecha_definitivo AS firmado_despues_definitivo,
      c.tipo_procedimiento, c.ejercicio, c.importe,
      round(c.importe / 1e6, 2) AS monto_mxn_millones,
      {IMPORTE_OK} AS importe_plausible, c.direccion_anuncio
    FROM contracts_pnt c JOIN efos e USING (rfc_norm)
    WHERE c.rfc_valido AND e.situacion IN ('Definitivo', 'Presunto')
    ORDER BY e.situacion, firmado_despues_definitivo DESC,
             c.importe DESC NULLS LAST""")

    inhab = q(f"""
    SELECT * EXCLUDE (_cid, _rn) FROM (
      SELECT c.*, s.nombre AS nombre_sfp, s.multa, s.institucion_sancionadora,
        s.inicio, s.fin, s.plazo_txt,
        c.fecha_efectiva IS NOT NULL AND s.inicio IS NOT NULL
          AND c.fecha_efectiva >= s.inicio
          AND s.fin IS NOT NULL AND c.fecha_efectiva <= s.fin
          AS durante_inhabilitacion,
        row_number() OVER (
          PARTITION BY c._cid
          ORDER BY (c.fecha_efectiva IS NOT NULL AND s.inicio IS NOT NULL
                    AND c.fecha_efectiva >= s.inicio
                    AND s.fin IS NOT NULL AND c.fecha_efectiva <= s.fin) DESC,
                   s.inicio DESC NULLS LAST) AS _rn
      FROM (SELECT *, row_number() OVER () AS _cid
            FROM contracts_pnt WHERE rfc_valido) c
      JOIN sfp s USING (rfc_norm)
    ) WHERE _rn = 1""")

    nombre = q(f"""
    WITH sin_rfc AS (
      SELECT *, {sql_name_norm('proveedor')} AS nombre_norm
      FROM contracts_pnt
      WHERE NOT rfc_valido AND proveedor IS NOT NULL
    ), efos_def AS (
      SELECT {sql_name_norm('nombre')} AS nombre_norm, rfc_norm AS rfc_69b,
        situacion, fecha_definitivo
      FROM efos WHERE situacion = 'Definitivo' AND length(nombre) >= 8
    )
    SELECT c.estado_comprador, c.sujeto_obligado, c.proveedor,
      e.rfc_69b, e.situacion,
      strftime(e.fecha_definitivo, '%Y-%m-%d') AS definitivo_dof,
      strftime(c.fecha_efectiva, '%Y-%m-%d') AS fecha_contrato,
      c.ejercicio, c.importe, round(c.importe / 1e6, 2) AS monto_mxn_millones,
      c.direccion_anuncio
    FROM sin_rfc c JOIN efos_def e USING (nombre_norm)
    WHERE length(c.nombre_norm) >= 8
    ORDER BY c.importe DESC NULLS LAST""")

    jovenes = q(f"""
    SELECT estado_comprador, sujeto_obligado, proveedor, rfc_norm AS rfc,
      strftime(fecha_constitucion_rfc, '%Y-%m-%d') AS constituida,
      strftime(fecha_efectiva, '%Y-%m-%d') AS fecha_contrato,
      date_diff('day', fecha_constitucion_rfc, fecha_efectiva) AS edad_dias,
      tipo_procedimiento, ejercicio, importe,
      round(importe / 1e6, 2) AS monto_mxn_millones, direccion_anuncio
    FROM contracts_pnt
    WHERE rfc_valido AND es_persona_moral
      AND fecha_constitucion_rfc IS NOT NULL AND fecha_efectiva IS NOT NULL
      AND date_diff('day', fecha_constitucion_rfc, fecha_efectiva)
          BETWEEN 0 AND {MAX_EDAD_DIAS - 1}
      AND {IMPORTE_OK} AND importe >= {MIN_JOVEN_MXN}
    ORDER BY importe DESC NULLS LAST""")

    concentracion = q(f"""
    WITH directas AS (
      SELECT estado_comprador, sujeto_obligado, proveedor, importe
      FROM contracts_pnt
      WHERE tipo_procedimiento ILIKE 'ADJUDICACI%DIRECTA%'
        AND {PROVEEDOR_PLAUSIBLE} AND {IMPORTE_OK}
    ), por_prov AS (
      SELECT estado_comprador, sujeto_obligado, proveedor,
        count(*) AS contratos, sum(importe) AS monto
      FROM directas GROUP BY 1, 2, 3
    ), por_so AS (
      SELECT sujeto_obligado, sum(monto) AS total_directo,
        sum(contratos) AS n_directas
      FROM por_prov GROUP BY 1
    )
    SELECT p.estado_comprador, p.sujeto_obligado, p.proveedor,
      p.contratos, round(p.monto / 1e6, 2) AS monto_mxn_millones,
      round(100.0 * p.monto / nullif(s.total_directo, 0), 1) AS pct_del_gasto_directo,
      s.n_directas AS directas_del_sujeto
    FROM por_prov p JOIN por_so s USING (sujeto_obligado)
    WHERE s.total_directo >= {CONC_MIN_GASTO}
      AND s.n_directas >= {CONC_MIN_DIRECTAS}
      AND p.monto >= {CONC_MIN_SHARE} * s.total_directo
    ORDER BY p.monto DESC NULLS LAST""")

    base_anillos = con.execute(f"""
        SELECT estado_comprador, sujeto_obligado, rfc_norm,
               any_value(proveedor) AS proveedor,
               fecha_constitucion_rfc::DATE AS constituida,
               min(fecha_efectiva)::DATE AS primer_contrato,
               count(*) AS contratos,
               sum(importe) FILTER ({IMPORTE_OK}) AS monto
        FROM contracts_pnt
        WHERE rfc_valido AND es_persona_moral
          AND fecha_constitucion_rfc IS NOT NULL AND sujeto_obligado IS NOT NULL
        GROUP BY 1, 2, 3, 5
    """).fetchdf()
    # proveedores persona-moral distintos por sujeto, para el piso de proporción
    total_prov = (base_anillos.drop_duplicates(["sujeto_obligado", "rfc_norm"])
                  .groupby("sujeto_obligado").size())
    miembros = widest_incorporation_run(
        base_anillos, ["estado_comprador", "sujeto_obligado"],
        ANILLO_VENTANA_DIAS, ANILLO_MIN_EMPRESAS)
    anillos = _resume_anillos(miembros, total_prov)

    return {"cobertura": cobertura, "efos": efos, "inhabilitados": inhab,
            "por_nombre": nombre, "jovenes": jovenes,
            "concentracion": concentracion, "anillos": anillos}


def _resume_anillos(miembros, total_prov) -> pd.DataFrame:
    """Un renglón por anillo (estado, sujeto obligado), solo si el anillo es
    >= ANILLO_MIN_SHARE de los proveedores persona-moral del sujeto (descarta
    el ruido de compradores enormes). total_prov: Series sujeto -> nº de
    proveedores distintos."""
    cols = ["estado_comprador", "sujeto_obligado", "empresas",
            "proveedores_del_sujeto", "pct_del_sujeto",
            "dias_entre_constituciones", "constituidas_desde",
            "constituidas_hasta", "contratos", "monto_mxn_millones",
            "proveedores"]
    if miembros.empty:
        return pd.DataFrame(columns=cols)
    filas = []
    for (estado, so), c in miembros.groupby(["estado_comprador",
                                             "sujeto_obligado"]):
        n_total = int(total_prov.get(so, len(c)))
        share = len(c) / n_total if n_total else 1.0
        if share < ANILLO_MIN_SHARE:
            continue
        filas.append({
            "estado_comprador": estado, "sujeto_obligado": so,
            "empresas": len(c), "proveedores_del_sujeto": n_total,
            "pct_del_sujeto": round(100 * share, 1),
            "dias_entre_constituciones":
                (c["constituida"].max() - c["constituida"].min()).days,
            "constituidas_desde": str(c["constituida"].min()),
            "constituidas_hasta": str(c["constituida"].max()),
            "contratos": int(c["contratos"].sum()),
            "monto_mxn_millones": round(float(c["monto"].sum() or 0) / 1e6, 1),
            "proveedores": " | ".join(
                f"{r.proveedor} ({r.rfc_norm}, {r.constituida})"
                for r in c.itertuples()),
        })
    if not filas:
        return pd.DataFrame(columns=cols)
    return (pd.DataFrame(filas)
            .sort_values("monto_mxn_millones", ascending=False)
            .reset_index(drop=True))


def main():
    con = duckdb.connect()
    load_views(con)        # efos (y contracts federal, para vocabulario)
    load_sfp_views(con)    # sfp: ventanas de inhabilitación
    load_pnt_views(con, sys.argv[1:] or None)
    t = consultas(con)

    print("== cobertura PNT por estado ==\n",
          t["cobertura"].to_string(index=False))
    efos, inhab = t["efos"], t["inhabilitados"]
    n_def = int((efos["situacion"] == "Definitivo").sum())
    print(f"\n== contratos estatales a 69-B por RFC: {len(efos)} "
          f"({n_def} a Definitivos) ==")
    if len(efos):
        print(efos.head(15).drop(columns=["direccion_anuncio"])
              .to_string(index=False, max_colwidth=34))
    gun = inhab[inhab["durante_inhabilitacion"]]
    print(f"\n== estatales a sancionados: {len(inhab)} | DURANTE la "
          f"inhabilitación: {len(gun)} ==")
    if len(gun):
        print(gun[["estado_comprador", "sujeto_obligado", "proveedor",
                   "rfc_norm", "fecha_efectiva", "importe"]]
              .head(15).to_string(index=False, max_colwidth=34))
    print(f"\n== respaldo por razón social (REQUIERE VERIFICACIÓN): "
          f"{len(t['por_nombre'])} ==")

    jov = t["jovenes"]
    print(f"\n== empresas jóvenes (<1 año) con contrato grande estatal: "
          f"{len(jov)} ==")
    if len(jov):
        print(jov[["estado_comprador", "proveedor", "constituida",
                   "fecha_contrato", "edad_dias", "monto_mxn_millones"]]
              .head(15).to_string(index=False, max_colwidth=34))

    conc = t["concentracion"]
    print(f"\n== un proveedor concentra ≥{int(CONC_MIN_SHARE * 100)}% del gasto "
          f"directo de su sujeto obligado: {len(conc)} ==")
    if len(conc):
        print(conc[["estado_comprador", "sujeto_obligado", "proveedor",
                    "contratos", "monto_mxn_millones", "pct_del_gasto_directo"]]
              .head(15).to_string(index=False, max_colwidth=34))

    anillos = t["anillos"]
    print(f"\n== anillos de constitución (empresas constituidas con días de "
          f"diferencia en un mismo sujeto obligado): {len(anillos)} ==")
    if len(anillos):
        print(anillos[["estado_comprador", "sujeto_obligado", "empresas",
                       "dias_entre_constituciones", "monto_mxn_millones"]]
              .head(15).to_string(index=False, max_colwidth=34))

    archivos = {"f10_cobertura_estatal.csv": t["cobertura"],
                "f10_efos_estatal.csv": efos,
                "f10_inhabilitados_estatal.csv": inhab,
                "f10_efos_estatal_por_nombre.csv": t["por_nombre"],
                "f10_jovenes_estatal.csv": jov,
                "f10_concentracion_estatal.csv": conc,
                "f10_anillos_estatal.csv": anillos}
    for nombre_csv, df in archivos.items():
        df.to_csv(OUT / nombre_csv, index=False)
    print("wrote " + ", ".join(f"{n} ({len(d)})"
                               for n, d in archivos.items()) + " -> findings/")


if __name__ == "__main__":
    main()
