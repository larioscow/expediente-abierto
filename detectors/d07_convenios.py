#!/usr/bin/env python
"""Detector 07 — contract inflation via convenios modificatorios.

The bulk CSV carries both the ORIGINAL contracted ceiling (monto_max_con_imp)
and the ceiling after the LAST modification agreement (monto_max_con_imp_uc).
The law caps how much a contract may grow by modification:

  LAASSP art. 52  — +20% of the original amount/quantity (adquisiciones)
  LOPSRM art. 59  — +25% for public works (obra pública)

An último-convenio amount above the applicable cap is a legally anchored
SCREEN (the caps admit narrow exceptions; verification decides), and the
classic shape it catches is the low-ball bid inflated after award.

Usage: python detectors/d07_convenios.py [contracts.csv ...]
"""
import sys

import duckdb
import pandas as pd

from detectors.common import MXN_OK, OUT, load_views

CAP_ADQUISICIONES = 0.20
CAP_OBRA = 0.25

# La ley permite crecer HASTA el tope: solo lo estrictamente superior es señal.
# El margen cubre el redondeo a centavos de la fuente y el float binario de
# 1+tope (sin él, un convenio exactamente en +20.000% se marcaba como
# violación), y garantiza que todo lo publicado muestre ≥ +20.1% tras
# redondear a un decimal.
MARGEN_TOPE = 0.0005


def inflated_modifications(con, cap_adq=CAP_ADQUISICIONES,
                           cap_obra=CAP_OBRA) -> pd.DataFrame:
    return con.execute(f"""
        WITH conv AS (
          SELECT *,
            TRY_CAST(replace(monto_max_con_imp, ',', '') AS DOUBLE) AS monto_original,
            TRY_CAST(replace(monto_max_con_imp_uc, ',', '') AS DOUBLE) AS monto_ultimo_convenio,
            CASE WHEN upper(coalesce(ley, '')) LIKE '%OBRAS%'
                 THEN {float(cap_obra)} ELSE {float(cap_adq)} END AS tope
          FROM contracts
          WHERE {MXN_OK}
        )
        SELECT file_year, institucion, nombre_uc, proveedor, rfc_norm AS rfc,
          codigo_contrato, num_contrato, titulo_contrato, ley, tipo_procedimiento,
          monto_original, monto_ultimo_convenio,
          round(100.0 * (monto_ultimo_convenio - monto_original) / monto_original, 1)
            AS pct_incremento,
          round(100.0 * tope, 1) AS tope_legal_pct,
          strftime(fecha_efectiva, '%Y-%m-%d') AS fecha_contrato,
          fecha_firma_ultimo_conv, direccion_anuncio
        FROM conv
        WHERE monto_original > 0 AND monto_ultimo_convenio IS NOT NULL
          AND monto_ultimo_convenio > monto_original * (1 + tope + {MARGEN_TOPE})
        ORDER BY pct_incremento DESC
    """).fetchdf()


def main():
    con = duckdb.connect()
    load_views(con, sys.argv[1:] or None)
    df = inflated_modifications(con)
    df.to_csv(OUT / "f07_convenios_inflados.csv", index=False)
    print(f"== contratos inflados por convenio sobre el tope legal: {len(df)} ==")
    cols = ["proveedor", "institucion", "pct_incremento", "tope_legal_pct",
            "monto_original", "monto_ultimo_convenio", "fecha_contrato"]
    print(df[cols].head(20).to_string(index=False, max_colwidth=44))
    extra = (df["monto_ultimo_convenio"] - df["monto_original"]).sum()
    print(f"\nincremento total sobre lo contratado: ${extra/1e6:,.1f}M MXN")


if __name__ == "__main__":
    main()
