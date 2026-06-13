#!/usr/bin/env python
"""Detector 02 — direct-award concentration.

Two views of the same risk: suppliers who live off direct awards (count,
share, money, breadth of buyers), and institutions whose spending leans on
direct awards / on a single supplier.

Usage: python detectors/d02_direct_award_concentration.py [contracts.csv ...]
"""
import sys

import duckdb
import pandas as pd

from detectors.common import MXN_OK as MXN, OUT, load_views


MIN_DIRECTAS = 10
MIN_PCT_DIRECTAS = 0.8
MIN_MONTO_DIRECTAS = 20e6


def direct_concentration_flags(con, min_directas=MIN_DIRECTAS,
                               min_pct=MIN_PCT_DIRECTAS,
                               min_monto=MIN_MONTO_DIRECTAS):
    """rfc_norm + fecha de la N-ésima adjudicación directa para proveedores
    que viven de directas — el backtest importa ESTA definición."""
    return con.execute(f"""
        WITH directas AS (
          SELECT rfc_norm, fecha_efectiva,
                 row_number() OVER (PARTITION BY rfc_norm
                                    ORDER BY fecha_efectiva) AS rn
          FROM contracts
          WHERE tipo_procedimiento ILIKE 'ADJUDICACI%DIRECTA%'
            AND rfc_norm IS NOT NULL AND fecha_efectiva IS NOT NULL
        ), crit AS (
          SELECT rfc_norm FROM contracts WHERE rfc_norm IS NOT NULL
          GROUP BY 1
          HAVING count(*) FILTER (tipo_procedimiento ILIKE 'ADJUDICACI%DIRECTA%')
                 >= {int(min_directas)}
             AND count(*) FILTER (tipo_procedimiento ILIKE 'ADJUDICACI%DIRECTA%')
                 >= {float(min_pct)} * count(*)
             AND sum(importe) FILTER (
                   tipo_procedimiento ILIKE 'ADJUDICACI%DIRECTA%' AND {MXN})
                 >= {float(min_monto)}
        )
        SELECT d.rfc_norm, d.fecha_efectiva::DATE AS flag_date
        FROM directas d JOIN crit USING (rfc_norm)
        WHERE rn = {int(min_directas)}
    """).fetchdf().assign(
        flag_date=lambda d: pd.to_datetime(d["flag_date"]).dt.date)


def main():
    con = duckdb.connect()
    load_views(con, sys.argv[1:] or None)

    con.execute(f"""
    CREATE VIEW clasif AS
    SELECT *,
      CASE WHEN tipo_procedimiento ILIKE 'ADJUDICACI%DIRECTA%' THEN 'directa'
           WHEN tipo_procedimiento ILIKE 'INVITACI%' THEN 'invitacion'
           WHEN tipo_procedimiento ILIKE 'LICITACI%' THEN 'licitacion'
           ELSE 'otro' END AS proc_clase,
      importe IS NOT NULL AND {MXN} AS mxn_ok
    FROM contracts
    """)

    def q(sql):
        return con.execute(sql).fetchdf()

    proveedores = q("""
    SELECT proveedor, rfc_norm AS rfc,
      CASE
        WHEN regexp_matches(upper(proveedor),
          'ROCHE|NOVARTIS|LABORATORIOS PISA|GILEAD|NOVO NORDISK|GLAXO|TAKEDA|AMGEN|JANSSEN|MERCK|ASTELLAS|PFIZER|ELI LILLY|CSL BEHRING|OCTAPHARMA|MEDTRONIC|BAYER|SANOFI|BOEHRINGER|ASTRAZENECA|BRISTOL|ABBVIE|BIOGEN')
          THEN 'farmaceutica_patente'
        WHEN regexp_matches(upper(proveedor),
          'LICONSA|DICONSA|IMPRESORA Y ENCUADERNADORA PROGRESO|TALLERES GRAFICOS|ESTUDIOS CHURUBUSCO|AEROPUERTOS Y SERVICIOS AUXILIARES|SERVICIO POSTAL|TELECOMUNICACIONES DE MEXICO')
          THEN 'entidad_estatal'
        ELSE ''
      END AS contexto,
      count(*) AS contratos,
      count(*) FILTER (proc_clase = 'directa') AS directas,
      round(100.0 * count(*) FILTER (proc_clase = 'directa') / count(*), 1) AS pct_directas,
      count(DISTINCT institucion) AS instituciones,
      round(sum(importe) FILTER (mxn_ok) / 1e6, 1) AS monto_mxn_millones,
      round(sum(importe) FILTER (mxn_ok AND proc_clase = 'directa') / 1e6, 1) AS monto_directas_mxn_m
    FROM clasif
    GROUP BY 1, 2, 3
    HAVING count(*) FILTER (proc_clase = 'directa') >= 10
       AND 100.0 * count(*) FILTER (proc_clase = 'directa') / count(*) >= 80
       AND sum(importe) FILTER (mxn_ok AND proc_clase = 'directa') >= 20e6
    ORDER BY monto_directas_mxn_m DESC, rfc""")
    print(f"== proveedores con >=10 directas, >=80% directas, >=20M MXN: {len(proveedores)} ==")
    print(proveedores.head(25).to_string(index=False, max_colwidth=44))
    proveedores.to_csv(OUT / "f02_proveedores_concentracion_directas.csv", index=False)

    instituciones = q("""
    SELECT institucion,
      count(*) AS contratos,
      round(100.0 * count(*) FILTER (proc_clase = 'directa') / count(*), 1) AS pct_directas_n,
      round(sum(importe) FILTER (mxn_ok) / 1e6, 1) AS monto_mxn_millones,
      round(100.0 * sum(importe) FILTER (mxn_ok AND proc_clase = 'directa')
            / nullif(sum(importe) FILTER (mxn_ok), 0), 1) AS pct_directas_monto
    FROM clasif
    GROUP BY 1 HAVING count(*) >= 100 AND sum(importe) FILTER (mxn_ok) >= 100e6
    ORDER BY pct_directas_monto DESC NULLS LAST LIMIT 40""")
    print("\n== instituciones (>=100 contratos, >=100M MXN) por % de monto en directas ==")
    print(instituciones.head(20).to_string(index=False, max_colwidth=54))
    instituciones.to_csv(OUT / "f02_instituciones_pct_directas.csv", index=False)

    dependencia = q("""
    WITH inst_prov AS (
      SELECT institucion, proveedor,
        sum(importe) FILTER (mxn_ok AND proc_clase = 'directa') AS monto_directas,
        count(*) FILTER (proc_clase = 'directa') AS n_directas
      FROM clasif GROUP BY 1, 2
    ), inst AS (
      SELECT institucion, sum(monto_directas) AS total_directas, sum(n_directas) AS n_total
      FROM inst_prov GROUP BY 1
    )
    SELECT ip.institucion, ip.proveedor,
      round(ip.monto_directas / 1e6, 1) AS monto_directas_mxn_m,
      ip.n_directas,
      round(100.0 * ip.monto_directas / nullif(i.total_directas, 0), 1) AS pct_del_gasto_directo
    FROM inst_prov ip JOIN inst i USING (institucion)
    WHERE i.total_directas >= 50e6 AND i.n_total >= 50 AND ip.monto_directas >= 0.5 * i.total_directas
    ORDER BY ip.monto_directas DESC LIMIT 30""")
    print("\n== dependencia: un proveedor concentra >=50% del gasto directo de la institución ==")
    print(dependencia.head(20).to_string(index=False, max_colwidth=44))
    dependencia.to_csv(OUT / "f02_dependencia_proveedor_unico.csv", index=False)


if __name__ == "__main__":
    main()
