#!/usr/bin/env python
"""Detector 01 — federal contracts awarded to SAT 69-B (EFOS) companies.

Joins ComprasMX contract data with the SAT Art. 69-B list on supplier RFC.
Headline = suppliers with status "Definitivo" (confirmed invoice mills).
Companies cleared by court or by rebuttal (Sentencia Favorable / Desvirtuado)
are explicitly excluded from the headline and reported only as context.

Outputs CSV tables under findings/ and prints a summary.
Usage: python detectors/d01_efos_contracts.py [contracts.csv ...]
"""
import sys

import duckdb

from detectors.common import MXN_OK, OUT, load_views


def main():
    con = duckdb.connect()
    load_views(con, sys.argv[1:] or None)

    con.execute("""
    CREATE VIEW hits AS
    SELECT c.*, e.situacion, e.fecha_definitivo, e.fecha_presunto, e.nombre AS nombre_69b,
      c.fecha_efectiva IS NOT NULL AND e.fecha_definitivo IS NOT NULL
        AND c.fecha_efectiva > e.fecha_definitivo AS firmado_despues_definitivo
    FROM contracts c JOIN efos e USING (rfc_norm)
    """)

    def q(sql):
        return con.execute(sql).fetchdf()

    sanity = q("""
    SELECT file_year, count(*) AS contratos, count(rfc_norm) AS con_rfc,
           count(fecha_efectiva) AS con_fecha, count(importe) AS con_importe
    FROM contracts GROUP BY 1 ORDER BY 1""")
    print("== sanity ==\n", sanity.to_string(index=False))

    resumen = q(f"""
    SELECT situacion, file_year,
           count(*) AS contratos,
           count(DISTINCT rfc_norm) AS empresas,
           round(sum(importe) FILTER {MXN_OK} / 1e6, 1) AS monto_mxn_millones
    FROM hits GROUP BY 1, 2 ORDER BY 1, 2""")
    print("\n== contratos a empresas 69-B por situación ==\n", resumen.to_string(index=False))
    resumen.to_csv(OUT / "f01_resumen_por_situacion.csv", index=False)

    despues = q(f"""
    SELECT file_year, count(*) AS contratos, count(DISTINCT rfc_norm) AS empresas,
           round(sum(importe) FILTER {MXN_OK} / 1e6, 1) AS monto_mxn_millones
    FROM hits WHERE situacion = 'Definitivo' AND firmado_despues_definitivo
    GROUP BY 1 ORDER BY 1""")
    print("\n== DEFINITIVO: contratos firmados DESPUÉS de publicación DOF como definitivo ==\n", despues.to_string(index=False))
    despues.to_csv(OUT / "f01_despues_de_definitivo.csv", index=False)

    top = q(f"""
    SELECT proveedor, rfc_norm AS rfc, situacion,
           strftime(fecha_definitivo, '%Y-%m-%d') AS definitivo_dof,
           strftime(fecha_efectiva, '%Y-%m-%d') AS fecha_contrato,
           firmado_despues_definitivo AS post_definitivo,
           institucion, tipo_procedimiento, round(importe / 1e6, 2) AS monto_mxn_millones, moneda_efectiva
    FROM hits WHERE situacion = 'Definitivo' AND importe IS NOT NULL AND {MXN_OK}
    ORDER BY importe DESC LIMIT 25""")
    print("\n== top 25 contratos a Definitivos (MXN) ==\n", top.to_string(index=False, max_colwidth=42))
    top.to_csv(OUT / "f01_top25_definitivos.csv", index=False)

    por_proc = q(f"""
    SELECT tipo_procedimiento, count(*) AS contratos,
           round(sum(importe) FILTER {MXN_OK} / 1e6, 1) AS monto_mxn_millones
    FROM hits WHERE situacion = 'Definitivo'
    GROUP BY 1 ORDER BY 2 DESC""")
    print("\n== Definitivos por tipo de procedimiento ==\n", por_proc.to_string(index=False, max_colwidth=60))
    por_proc.to_csv(OUT / "f01_definitivos_por_procedimiento.csv", index=False)

    detalle = q("""
    SELECT file_year, codigo_contrato, num_contrato, titulo_contrato, proveedor, rfc_norm AS rfc,
           situacion, strftime(fecha_definitivo, '%Y-%m-%d') AS definitivo_dof,
           strftime(fecha_efectiva, '%Y-%m-%d') AS fecha_contrato, firmado_despues_definitivo,
           institucion, nombre_uc, orden_gobierno, estado_comprador,
           tipo_procedimiento, importe, moneda_efectiva, direccion_anuncio
    FROM hits WHERE situacion IN ('Definitivo', 'Presunto')
    ORDER BY situacion, importe DESC NULLS LAST""")
    detalle.to_csv(OUT / "f01_detalle_completo.csv", index=False)
    print(f"\nwrote {len(detalle)} detail rows -> findings/f01_detalle_completo.csv")


if __name__ == "__main__":
    main()
