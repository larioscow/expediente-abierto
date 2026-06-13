#!/usr/bin/env python
"""Detector 04 — recently incorporated companies winning large contracts.

For personas morales, the RFC encodes the incorporation date (positions 4-9,
YYMMDD). Company age at award is therefore computable from the contract data
alone, with no registry lookup. Flags awards where the supplier was younger
than 1 year and the amount is large; validates the signal by measuring how
overrepresented young winners are among later-confirmed 69-B shells.

Usage: python detectors/d04_young_winners.py [contracts.csv ...]
"""
import sys

import duckdb
import pandas as pd

from detectors.common import MXN_OK as MXN, OUT, load_views

MIN_IMPORTE = 5_000_000  # MXN
MAX_EDAD_DIAS = 365


def young_winner_flags(con, max_edad_dias=MAX_EDAD_DIAS,
                       min_importe=MIN_IMPORTE):
    """rfc_norm + fecha del primer contrato que dispara la señal
    'joven y grande' — el backtest importa ESTA definición."""
    return con.execute(f"""
        SELECT rfc_norm, min(fecha_efectiva)::DATE AS flag_date
        FROM contracts
        WHERE es_persona_moral AND fecha_constitucion_rfc IS NOT NULL
          AND date_diff('day', fecha_constitucion_rfc, fecha_efectiva)
              BETWEEN 0 AND {int(max_edad_dias) - 1}
          AND importe >= {float(min_importe)} AND {MXN}
        GROUP BY 1
    """).fetchdf().assign(
        flag_date=lambda d: pd.to_datetime(d["flag_date"]).dt.date)


def main():
    con = duckdb.connect()
    load_views(con, sys.argv[1:] or None)

    con.execute(f"""
    CREATE VIEW aged AS
    SELECT *, date_diff('day', fecha_constitucion_rfc, fecha_efectiva) AS edad_dias
    FROM contracts
    WHERE es_persona_moral AND fecha_constitucion_rfc IS NOT NULL AND fecha_efectiva IS NOT NULL
      AND date_diff('day', fecha_constitucion_rfc, fecha_efectiva) BETWEEN 0 AND 36500
    """)

    def q(sql):
        return con.execute(sql).fetchdf()

    resumen = q(f"""
    SELECT file_year,
      count(*) AS contratos_pm,
      count(*) FILTER (edad_dias < 365) AS a_empresas_menores_1a,
      count(*) FILTER (edad_dias < 365 AND importe >= {MIN_IMPORTE} AND {MXN}) AS jovenes_y_grandes,
      round(sum(importe) FILTER (edad_dias < 365 AND {MXN}) / 1e6, 1) AS monto_a_menores_1a_mxn_m
    FROM aged GROUP BY 1 ORDER BY 1""")
    print("== resumen por año ==\n", resumen.to_string(index=False))
    resumen.to_csv(OUT / "f04_resumen.csv", index=False)

    top = q(f"""
    SELECT proveedor, rfc_norm AS rfc,
      strftime(fecha_constitucion_rfc, '%Y-%m-%d') AS constituida,
      strftime(fecha_efectiva, '%Y-%m-%d') AS fecha_contrato,
      edad_dias, institucion, tipo_procedimiento,
      round(importe / 1e6, 2) AS monto_mxn_millones, tipo_monto, direccion_anuncio
    FROM aged
    WHERE edad_dias < 365 AND importe >= {MIN_IMPORTE} AND {MXN}
    ORDER BY importe DESC LIMIT 30""")
    print("\n== top 30 jóvenes (<1 año) y grandes (>=5M MXN) ==\n",
          top.drop(columns=["direccion_anuncio"]).to_string(index=False, max_colwidth=40))
    top.to_csv(OUT / "f04_top30_jovenes_grandes.csv", index=False)

    por_proc = q("""
    SELECT
      CASE WHEN tipo_procedimiento ILIKE 'ADJUDICACI%DIRECTA%' THEN 'ADJUDICACION DIRECTA'
           WHEN tipo_procedimiento ILIKE 'INVITACI%' THEN 'INVITACION RESTRINGIDA'
           WHEN tipo_procedimiento ILIKE 'LICITACI%' THEN 'LICITACION PUBLICA'
           ELSE 'OTRO' END AS procedimiento,
      count(*) AS contratos,
      round(median(edad_dias) / 365.25, 1) AS edad_mediana_anios,
      round(100.0 * count(*) FILTER (edad_dias < 365) / count(*), 2) AS pct_a_menores_1a
    FROM aged GROUP BY 1 ORDER BY 2 DESC""")
    print("\n== edad del proveedor por tipo de procedimiento ==\n", por_proc.to_string(index=False))
    por_proc.to_csv(OUT / "f04_edad_por_procedimiento.csv", index=False)

    # Signal validation: are young winners overrepresented among later-confirmed shells?
    enr = q("""
    WITH base AS (
      SELECT a.rfc_norm, min(a.edad_dias) AS edad_min,
             bool_or(e.situacion = 'Definitivo') AS es_definitivo
      FROM aged a LEFT JOIN efos e USING (rfc_norm)
      GROUP BY 1
    )
    SELECT
      count(*) FILTER (edad_min < 365) AS empresas_jovenes,
      count(*) FILTER (edad_min >= 365) AS empresas_viejas,
      count(*) FILTER (edad_min < 365 AND es_definitivo) AS jovenes_definitivo,
      count(*) FILTER (edad_min >= 365 AND es_definitivo) AS viejas_definitivo,
      round(10000.0 * count(*) FILTER (edad_min < 365 AND es_definitivo)
            / nullif(count(*) FILTER (edad_min < 365), 0), 2) AS tasa_jovenes_x10k,
      round(10000.0 * count(*) FILTER (edad_min >= 365 AND es_definitivo)
            / nullif(count(*) FILTER (edad_min >= 365), 0), 2) AS tasa_viejas_x10k
    FROM base""")
    print("\n== validación: tasa de 'Definitivo' posterior, empresas jóvenes vs viejas (por 10k) ==\n",
          enr.to_string(index=False))
    enr.to_csv(OUT / "f04_validacion_enriquecimiento.csv", index=False)


if __name__ == "__main__":
    main()
