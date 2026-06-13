#!/usr/bin/env python
"""Detector 12 — Benford de montos estatales (PNT) por sujeto obligado.

La misma matemática forense de d03 (MAD primer y segundo dígito, Z de
Nigrini por dígito, control de FDR Benjamini-Hochberg sobre las pruebas
simultáneas) aplicada al universo estatal de contracts_pnt, agrupando por
sujeto obligado en vez de institución federal. Es donde el dinero local
se decide y donde el directorio nacional de sancionados llega tarde.

Los montos de la PNT traen capturas absurdas: se acota la plausibilidad
(1 MXN … 5,000 millones) igual que d10 antes de medir la distribución.

Usage: python -m detectors.d12_benford_estatal [pnt_*.csv ...]
"""
import sys

import duckdb

from detectors.common import OUT
from detectors.d03_benford import benford_por_grupo, detalle_digitos
from detectors.pnt import load_pnt_views

# misma cota de plausibilidad que d10; la moneda PNT es MXN implícita
FILTRO = ("importe BETWEEN 1 AND 5e9 AND "
          "(moneda IS NULL OR upper(moneda) LIKE '%PESO%' OR upper(moneda) = 'MXN')")
MIN_N = 200  # sujetos obligados son más chicos que dependencias federales


def main():
    con = duckdb.connect()
    load_pnt_views(con, sys.argv[1:] or None)

    df, por_so = benford_por_grupo(con, "contracts_pnt", "sujeto_obligado",
                                   filtro=FILTRO, min_n=MIN_N)
    if df.empty:
        print(f"sin sujetos obligados con n>={MIN_N} montos plausibles")
        return
    df.to_csv(OUT / "f13_benford_estatal.csv", index=False)
    n_fdr = int(df["no_conforme_fdr05"].sum())
    print(f"sujetos obligados analizados (n>={MIN_N}): {len(df)}")
    print(f"no conformes con FDR 5% (Benjamini-Hochberg): {n_fdr} de {len(df)}")
    print("\n== peores 20 por MAD primer dígito (Nigrini) ==")
    print(df.head(20).to_string(index=False, max_colwidth=46))
    print("\n== distribución de bandas (primer dígito) ==")
    print(df["banda_nigrini"].value_counts().to_string())

    worst = df.iloc[0]["sujeto_obligado"]
    n_worst = int(df.iloc[0]["n_contratos"])
    detail = detalle_digitos(por_so[worst]["f1"], n_worst)
    print(f"\n== dígitos del peor sujeto obligado: {worst} "
          f"(n={n_worst}, |Z|>1.96 = anómalo) ==")
    print(detail.to_string(index=False))
    detail.to_csv(OUT / "f13_benford_estatal_peor.csv", index=False)
    print(f"\nwrote f13_benford_estatal.csv ({len(df)}) -> findings/")


if __name__ == "__main__":
    main()
