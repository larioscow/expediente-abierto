#!/usr/bin/env python
"""Detector 03 — Benford first-digit conformity of contract amounts, per institution.

Benford's law: P(d) = log10(1 + 1/d). Contract amounts span orders of
magnitude, so institutions' amount distributions should roughly conform.
Strong deviation flags numbers that were *chosen* rather than *formed* —
e.g. amounts pinned just under approval thresholds, or fabricated invoices.

Statistics, per the forensic-accounting standard:
- MAD (mean absolute deviation) with Nigrini conformity bands — robust at any n
- chi-square (df=8) with closed-form p-value — reported for completeness;
  at large n it rejects trivially, so ranking uses MAD.

A deviation is a SCREEN, not a verdict: round-number contracting culture also
breaks Benford. Flagged institutions need the d02/d04 cross-reference.

Usage: python detectors/d03_benford.py [contracts.csv ...]
"""
import math
import sys

import duckdb

from common import OUT, load_views

MIN_N = 300

con = duckdb.connect()
load_views(con, sys.argv[1:] or None)

dist = con.execute(f"""
WITH amounts AS (
  SELECT institucion, importe,
    CAST(floor(importe / pow(10, floor(log10(importe)))) AS INT) AS d1
  FROM contracts
  WHERE importe >= 100 AND (moneda_drc = 'MXN' OR moneda_drc IS NULL)
), inst AS (
  SELECT institucion, count(*) AS n FROM amounts GROUP BY 1 HAVING count(*) >= {MIN_N}
)
SELECT a.institucion, a.d1, count(*) AS freq, any_value(i.n) AS n
FROM amounts a JOIN inst i USING (institucion)
WHERE a.d1 BETWEEN 1 AND 9
GROUP BY 1, 2 ORDER BY 1, 2
""").fetchall()

BENFORD = {d: math.log10(1 + 1 / d) for d in range(1, 10)}

def chi2_sf_df8(x):
    """Survival function of chi-square with df=8 (closed form for even df)."""
    h = x / 2
    return math.exp(-h) * sum(h ** k / math.factorial(k) for k in range(4))

by_inst = {}
for inst, d1, freq, n in dist:
    by_inst.setdefault(inst, {"n": n, "freq": {}})["freq"][d1] = freq

rows = []
for inst, data in by_inst.items():
    n = data["n"]
    mad = sum(abs(data["freq"].get(d, 0) / n - BENFORD[d]) for d in range(1, 10)) / 9
    chi2 = sum(
        (data["freq"].get(d, 0) - n * BENFORD[d]) ** 2 / (n * BENFORD[d])
        for d in range(1, 10)
    )
    band = ("conforme" if mad <= 0.006 else
            "aceptable" if mad <= 0.012 else
            "marginal" if mad <= 0.015 else "NO CONFORME")
    rows.append((inst, n, round(mad, 4), band, round(chi2, 1), chi2_sf_df8(chi2)))

rows.sort(key=lambda r: -r[2])

import pandas as pd
df = pd.DataFrame(rows, columns=["institucion", "n_contratos", "mad", "banda_nigrini", "chi2", "p_value"])
df.to_csv(OUT / "f03_benford_instituciones.csv", index=False)
print(f"instituciones analizadas (n>={MIN_N}): {len(df)}")
print("\n== peores 20 por MAD (Nigrini) ==")
print(df.head(20).to_string(index=False, max_colwidth=60))
print("\n== distribución de bandas ==")
print(df["banda_nigrini"].value_counts().to_string())

worst = df.iloc[0]["institucion"]
detail = con.execute(f"""
SELECT CAST(floor(importe / pow(10, floor(log10(importe)))) AS INT) AS digito,
  count(*) AS observado,
  round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct_observado,
  round(100 * log10(1 + 1.0 / CAST(floor(importe / pow(10, floor(log10(importe)))) AS INT)), 1) AS pct_benford
FROM contracts
WHERE institucion = ? AND importe >= 100 AND (moneda_drc = 'MXN' OR moneda_drc IS NULL)
  AND CAST(floor(importe / pow(10, floor(log10(importe)))) AS INT) BETWEEN 1 AND 9
GROUP BY 1 ORDER BY 1
""", [worst]).fetchdf()
print(f"\n== dígitos de la peor institución: {worst} ==")
print(detail.to_string(index=False))
detail.to_csv(OUT / "f03_peor_institucion_digitos.csv", index=False)
