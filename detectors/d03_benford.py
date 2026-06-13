#!/usr/bin/env python
"""Detector 03 — Benford first-digit conformity of contract amounts, per institution.

Benford's law: P(d) = log10(1 + 1/d). Contract amounts span orders of
magnitude, so institutions' amount distributions should roughly conform.
Strong deviation flags numbers that were *chosen* rather than *formed* —
e.g. amounts pinned just under approval thresholds, or fabricated invoices.

Statistics, per the forensic-accounting standard:
- MAD (mean absolute deviation) with Nigrini conformity bands — robust at any n
- first AND second digit: the second digit is more sensitive to fabricated or
  rounded amounts and harder to fake by accident
- per-digit Nigrini Z on the worst institution — pinpoints WHICH digits drive
  the deviation (e.g. an excess of amounts starting 9 just under a threshold)
- chi-square (df=8) with closed-form p-value — reported for completeness;
  at large n it rejects trivially, so ranking uses MAD.

A deviation is a SCREEN, not a verdict: round-number contracting culture also
breaks Benford. Flagged institutions need the d02/d04 cross-reference.

Usage: python detectors/d03_benford.py [contracts.csv ...]
"""
import math
import sys

import duckdb

from detectors.common import MXN_OK, OUT, load_views
from shared.estadistica import (benford_first, benford_second,
                                benjamini_hochberg, mad_benford, z_digito)

MIN_N = 300

# bandas de Nigrini para la MAD del primer dígito
BANDAS_MAD1 = ((0.006, "conforme"), (0.012, "aceptable"), (0.015, "marginal"))
# segundo dígito: bandas de Nigrini propias (más estrechas)
BANDAS_MAD2 = ((0.008, "conforme"), (0.010, "aceptable"), (0.012, "marginal"))

BENFORD = benford_first()
BENFORD2 = benford_second()


def banda(mad: float, bandas) -> str:
    for tope, nombre in bandas:
        if mad <= tope:
            return nombre
    return "NO CONFORME"


def chi2_sf_df8(x):
    """Survival function of chi-square with df=8 (closed form for even df)."""
    h = x / 2
    return math.exp(-h) * sum(h ** k / math.factorial(k) for k in range(4))


# primer dígito: floor(x / 10^floor(log10 x)); segundo: el dígito siguiente
D1_SQL = "CAST(floor(importe / pow(10, floor(log10(importe)))) AS INT)"
D2_SQL = ("CAST(floor(importe / pow(10, floor(log10(importe)) - 1)) AS INT) "
          "% 10")


def benford_por_grupo(con, fuente: str, grupo: str, *, filtro: str = "TRUE",
                      min_n: int = MIN_N):
    """Tabla de conformidad Benford por grupo sobre cualquier vista.

    fuente/grupo: nombre de vista y columna que agrupa (institucion,
    sujeto_obligado…). filtro: condición SQL extra (p.ej. plausibilidad de
    monto en datos estatales). Devuelve (df, frecuencias_por_grupo) donde
    el df ya trae MAD1/MAD2, bandas, chi², p y el flag FDR. La misma
    matemática para datos federales y estatales — un solo lugar que probar.
    """
    import pandas as pd

    dist = con.execute(f"""
    WITH amounts AS (
      SELECT {grupo} AS grupo, {D1_SQL} AS d1, {D2_SQL} AS d2
      FROM {fuente} WHERE importe >= 100 AND {grupo} IS NOT NULL AND ({filtro})
    ), grp AS (
      SELECT grupo, count(*) AS n FROM amounts
      GROUP BY 1 HAVING count(*) >= {int(min_n)}
    )
    SELECT a.grupo, a.d1, a.d2, g.n
    FROM amounts a JOIN grp g USING (grupo)
    """).fetchall()

    por_grupo = {}
    for g, d1, d2, n in dist:
        e = por_grupo.setdefault(g, {"n": n, "f1": {}, "f2": {}})
        if d1 is not None and 1 <= d1 <= 9:
            e["f1"][d1] = e["f1"].get(d1, 0) + 1
        if d2 is not None and 0 <= d2 <= 9:
            e["f2"][d2] = e["f2"].get(d2, 0) + 1

    rows = []
    for g, data in por_grupo.items():
        n = data["n"]
        mad1 = mad_benford(data["f1"], n, BENFORD)
        mad2 = mad_benford(data["f2"], n, BENFORD2)
        chi2 = sum((data["f1"].get(d, 0) - n * BENFORD[d]) ** 2
                   / (n * BENFORD[d]) for d in range(1, 10))
        rows.append((g, n, round(mad1, 4), banda(mad1, BANDAS_MAD1),
                     round(mad2, 4), banda(mad2, BANDAS_MAD2),
                     round(chi2, 1), chi2_sf_df8(chi2)))
    rows.sort(key=lambda r: -r[2])
    df = pd.DataFrame(rows, columns=[
        grupo, "n_contratos", "mad", "banda_nigrini",
        "mad_segundo_digito", "banda_segundo_digito", "chi2", "p_value"])
    df["no_conforme_fdr05"] = benjamini_hochberg(df["p_value"].tolist(), q=0.05)
    return df, por_grupo


def detalle_digitos(frecuencias: dict, n: int):
    """Z de Nigrini por dígito de un grupo: qué dígitos sobre/sub-pesan."""
    import pandas as pd
    return pd.DataFrame([{
        "digito": d, "observado": frecuencias.get(d, 0),
        "pct_observado": round(100 * frecuencias.get(d, 0) / n, 1),
        "pct_benford": round(100 * BENFORD[d], 1),
        "z_nigrini": round(z_digito(frecuencias.get(d, 0), n, BENFORD[d]), 2),
        "anomalo": z_digito(frecuencias.get(d, 0), n, BENFORD[d]) > 1.96,
    } for d in range(1, 10)])


def main():
    con = duckdb.connect()
    load_views(con, sys.argv[1:] or None)

    df, por_inst = benford_por_grupo(con, "contracts", "institucion",
                                     filtro=MXN_OK)
    df.to_csv(OUT / "f03_benford_instituciones.csv", index=False)
    print(f"instituciones analizadas (n>={MIN_N}): {len(df)}")
    print(f"no conformes con FDR 5% (Benjamini-Hochberg): "
          f"{int(df['no_conforme_fdr05'].sum())} de {len(df)}")
    print("\n== peores 20 por MAD primer dígito (Nigrini) ==")
    print(df.head(20).to_string(index=False, max_colwidth=52))
    print("\n== distribución de bandas (primer dígito) ==")
    print(df["banda_nigrini"].value_counts().to_string())
    print("\n== distribución de bandas (segundo dígito) ==")
    print(df["banda_segundo_digito"].value_counts().to_string())

    worst = df.iloc[0]["institucion"]
    n_worst = int(df.iloc[0]["n_contratos"])
    detail = detalle_digitos(por_inst[worst]["f1"], n_worst)
    print(f"\n== dígitos de la peor institución: {worst} "
          f"(n={n_worst}, |Z|>1.96 = anómalo) ==")
    print(detail.to_string(index=False))
    detail.to_csv(OUT / "f03_peor_institucion_digitos.csv", index=False)


if __name__ == "__main__":
    main()
