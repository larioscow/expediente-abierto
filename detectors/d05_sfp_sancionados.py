#!/usr/bin/env python
"""Detector 05 — federal contracts to SFP-debarred suppliers (exact RFC join).

Headline signal: a contract whose effective date falls INSIDE the supplier's
debarment window — i.e. awarded while the company was legally barred from
receiving government contracts. Also reports all-time contracts to ever-debarred
suppliers as context.

Usage: python detectors/d05_sfp_sancionados.py [contracts.csv ...]
"""
import sys

import duckdb

from detectors.common import MXN_OK, OUT, load_sfp_views, load_views


def main():
    con = duckdb.connect()
    load_views(con, sys.argv[1:] or None)
    load_sfp_views(con)

    def q(sql):
        return con.execute(sql).fetchdf()

    print("== SFP universo ==")
    print(q("""SELECT count(*) AS sanciones, count(DISTINCT rfc_norm) AS empresas,
      count(DISTINCT rfc_norm) FILTER (fin >= current_date) AS vigentes_aprox
    FROM sfp""").to_string(index=False))

    resumen = q(f"""
    SELECT file_year, count(*) AS contratos, count(DISTINCT rfc_norm) AS empresas,
      round(sum(importe) FILTER {MXN_OK}/1e6, 1) AS monto_mxn_millones
    FROM sfp_hits GROUP BY 1 ORDER BY 1""")
    print("\n== contratos a proveedores sancionados por la SFP (cruce por RFC) ==\n", resumen.to_string(index=False))
    resumen.to_csv(OUT / "f05_resumen.csv", index=False)

    gun = q(f"""
    SELECT proveedor, rfc_norm AS rfc,
      strftime(inicio,'%Y-%m-%d') AS inhabilitado_desde, strftime(fin,'%Y-%m-%d') AS hasta,
      strftime(fecha_efectiva,'%Y-%m-%d') AS fecha_contrato,
      institucion, orden_gobierno, estado_comprador, tipo_procedimiento, importe,
      round(importe/1e6,2) AS monto_mxn_millones, direccion_anuncio
    FROM sfp_hits WHERE durante_inhabilitacion AND {MXN_OK}
    ORDER BY importe DESC NULLS LAST""")
    print(f"\n== SMOKING GUN: contratos firmados DURANTE la inhabilitación: {len(gun)} ==")
    print(gun.drop(columns=["direccion_anuncio"]).head(20).to_string(index=False, max_colwidth=40))
    gun.to_csv(OUT / "f05_durante_inhabilitacion.csv", index=False)

    detalle = q("""
    SELECT file_year, codigo_contrato, proveedor, rfc_norm AS rfc, nombre_sfp,
      strftime(inicio,'%Y-%m-%d') AS inhab_desde, strftime(fin,'%Y-%m-%d') AS inhab_hasta,
      strftime(fecha_efectiva,'%Y-%m-%d') AS fecha_contrato, durante_inhabilitacion,
      institucion, orden_gobierno, estado_comprador, tipo_procedimiento,
      importe, moneda_efectiva, multa,
      institucion_sancionadora, direccion_anuncio
    FROM sfp_hits ORDER BY durante_inhabilitacion DESC, importe DESC NULLS LAST, codigo_contrato""")
    detalle.to_csv(OUT / "f05_detalle_completo.csv", index=False)
    print(f"\nwrote {len(detalle)} detail rows -> findings/f05_detalle_completo.csv")


if __name__ == "__main__":
    main()
