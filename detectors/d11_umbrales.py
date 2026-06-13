#!/usr/bin/env python
"""Detector 11 — amontonamiento de montos justo bajo umbrales (bunching).

La ley fija montos máximos anuales para adjudicar directo o por invitación;
quien fracciona o "ajusta" precios para esquivar la licitación deja una
firma estadística: exceso de contratos apenas DEBAJO de un corte y hueco
apenas arriba. En vez de cablear los umbrales legales (cambian por año y por
presupuesto de la dependencia), se barren cortes candidatos redondos y se
aplica la prueba de signo local: en una ventana angosta alrededor del corte,
una densidad suave reparte los contratos como volados justos; un exceso
sistemático abajo es p_binomial chico. El control de multiplicidad
(Benjamini-Hochberg) corre sobre TODAS las pruebas institución × corte.

Los montos exactamente EN el corte se reportan aparte (pct_exacto): el
número redondo es cultura de cotización, no necesariamente evasión; la
prueba los excluye para medir solo el "apenas abajo".

Usage: python -m detectors.d11_umbrales [contracts.csv ...]
"""
import sys

import duckdb
import pandas as pd

from detectors.common import MXN_OK, OUT, load_views
from shared.estadistica import benjamini_hochberg, binomial_sf_half

# cortes candidatos en MXN: redondos donde viven los topes típicos de
# adjudicación directa / invitación (varían por año y dependencia)
UMBRALES = [50_000, 100_000, 150_000, 200_000, 300_000, 400_000, 500_000,
            750_000, 1_000_000, 1_500_000, 2_000_000, 3_000_000, 5_000_000]
VENTANA = 0.05   # ±5% del corte
MIN_VENTANA = 30  # contratos mínimos en la ventana para probar


def bunching_table(con, umbrales=UMBRALES, ventana=VENTANA,
                   min_ventana=MIN_VENTANA) -> pd.DataFrame:
    """Una fila por (institución, corte) con la prueba de signo local.
    Solo procedimientos sin licitación (directa/invitación), que es donde
    el tope muerde."""
    casos = []
    for t in umbrales:
        lo, hi = t * (1 - ventana), t * (1 + ventana)
        casos.append(f"""
        SELECT institucion, {t} AS umbral,
          count(*) FILTER (importe >= {lo} AND importe < {t}) AS bajo,
          count(*) FILTER (importe > {t} AND importe <= {hi}) AS sobre,
          count(*) FILTER (importe = {t}) AS exacto
        FROM contracts
        WHERE importe IS NOT NULL AND {MXN_OK}
          AND upper(tipo_procedimiento) NOT LIKE '%LICITACI%'
          AND importe >= {lo} AND importe <= {hi}
        GROUP BY 1""")
    df = con.execute(" UNION ALL ".join(casos)).fetchdf()
    df["n_ventana"] = df["bajo"] + df["sobre"]
    df = df[df["n_ventana"] >= min_ventana].copy()
    if df.empty:
        return df.assign(razon=[], p_binomial=[], q_fdr05=[], pct_exacto=[])
    df["razon"] = df["bajo"] / df["sobre"].where(df["sobre"] > 0)
    df["p_binomial"] = [binomial_sf_half(int(b), int(n))
                        for b, n in zip(df["bajo"], df["n_ventana"])]
    df["q_fdr05"] = benjamini_hochberg(df["p_binomial"].tolist(), q=0.05)
    df["pct_exacto"] = (100 * df["exacto"]
                        / (df["n_ventana"] + df["exacto"])).round(1)
    return df.sort_values("p_binomial").reset_index(drop=True)


def main():
    con = duckdb.connect()
    load_views(con, sys.argv[1:] or None)
    df = bunching_table(con)
    sig = df[df["q_fdr05"]]
    df["p_binomial"] = df["p_binomial"].map(lambda p: round(p, 6))
    df["razon"] = df["razon"].round(2)
    df.to_csv(OUT / "f11_umbrales_bunching.csv", index=False)
    print(f"pruebas institución×corte con n>={MIN_VENTANA}: {len(df)}")
    print(f"con exceso bajo el corte a FDR 5%: {len(sig)}")
    print("\n== peores 20 (exceso de contratos apenas bajo el corte) ==")
    cols = ["institucion", "umbral", "bajo", "sobre", "razon",
            "p_binomial", "q_fdr05", "pct_exacto"]
    print(df[cols].head(20).to_string(index=False, max_colwidth=52))
    print("\nrazon = contratos apenas abajo / apenas arriba (±5% del corte, "
          "excluyendo el monto exacto).\nUna densidad suave da ~1; el "
          "fraccionamiento para esquivar licitación infla la razón.\n"
          "pct_exacto = % de la ventana clavado en el corte (cultura de "
          "número redondo, se reporta aparte).")


if __name__ == "__main__":
    main()
