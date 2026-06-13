#!/usr/bin/env python
"""Backtest — measured precision of the predictive screens.

For each signal, the flagged suppliers' rate of being sanctioned AFTER the
flag date (SAT 69-B presunto/definitivo publication, or SFP debarment start)
is compared against the rate for ALL contracting suppliers after their first
contract. Strict time ordering: a sanction that predates the flag is never
counted as a prediction.

d01/d05 are excluded by construction — they're defined by the sanction lists,
so backtesting them against the same lists would be circular. d03 scores
institutions, not suppliers.

Caveats (stated, not hidden):
  - open horizon: "later" means any time after the flag inside the data
    coverage, so older flags have more exposure time; the median days-to-
    sanction column gives the scale.
  - d02's eligibility criteria use full-period totals; only its flag DATE
    (the 10th direct award) is time-anchored.

Usage: python detectors/backtest.py [contracts.csv ...]
"""
import sys

import duckdb
import pandas as pd

from detectors.common import OUT, load_sfp_views, load_views
from detectors.d02_direct_award_concentration import direct_concentration_flags
from detectors.d04_young_winners import young_winner_flags
from detectors.d06_colusion import (incorporation_cluster_members,
                                    rotation_members, same_day_splits)
from detectors.d07_convenios import inflated_modifications
from shared.estadistica import fisher_exact_greater, wilson_interval


def sanction_dates(con) -> pd.DataFrame:
    """Earliest sanction signal per RFC: 69-B presunto/definitivo publication
    or SFP debarment start. Tolerates a missing sfp view (tests)."""
    frames = [con.execute("""
        SELECT rfc_norm,
               least(coalesce(fecha_presunto, fecha_definitivo),
                     coalesce(fecha_definitivo, fecha_presunto))::DATE AS fecha
        FROM efos
        WHERE fecha_presunto IS NOT NULL OR fecha_definitivo IS NOT NULL
    """).fetchdf()]
    try:
        frames.append(con.execute("""
            SELECT rfc_norm, min(inicio)::DATE AS fecha
            FROM sfp WHERE inicio IS NOT NULL GROUP BY 1
        """).fetchdf())
    except duckdb.CatalogException:
        pass
    both = pd.concat(frames, ignore_index=True)
    out = both.groupby("rfc_norm", as_index=False)["fecha"].min()
    out["fecha"] = pd.to_datetime(out["fecha"]).dt.date
    return out.rename(columns={"fecha": "fecha_sancion"})


def supplier_universe(con) -> pd.DataFrame:
    """All personas morales that won anything, anchored at first contract."""
    return con.execute("""
        SELECT rfc_norm, min(fecha_efectiva)::DATE AS t0
        FROM contracts
        WHERE es_persona_moral AND fecha_efectiva IS NOT NULL
        GROUP BY 1
    """).fetchdf()


def evaluate(signal: str, flags: pd.DataFrame, universe: pd.DataFrame,
             sanctions: pd.DataFrame) -> dict:
    """flags: rfc_norm, flag_date. universe: rfc_norm, t0.
    sanctions: rfc_norm, fecha_sancion."""
    s = sanctions.copy()
    s["fecha_sancion"] = pd.to_datetime(s["fecha_sancion"])

    f = (flags.groupby("rfc_norm", as_index=False)["flag_date"].min()
         if len(flags) else flags.copy())
    f = f.merge(s, on="rfc_norm", how="left")
    if len(f):
        f["flag_date"] = pd.to_datetime(f["flag_date"])
        f["hit"] = f["fecha_sancion"].notna() & (f["fecha_sancion"] > f["flag_date"])
    else:
        f["hit"] = pd.Series(dtype=bool)

    u = universe.merge(s, on="rfc_norm", how="left")
    u["t0"] = pd.to_datetime(u["t0"])
    u["hit"] = u["fecha_sancion"].notna() & (u["fecha_sancion"] > u["t0"])

    n_f, n_hit = len(f), int(f["hit"].sum())
    hits = f[f["hit"]]
    days = ((hits["fecha_sancion"] - hits["flag_date"]).dt.days
            if n_hit else pd.Series(dtype=int))

    # 2×2 marcadas vs NO marcadas (= universo menos marcadas): grupos
    # disjuntos, para que lift, su IC y Fisher midan lo mismo. El grupo base
    # se construye EXCLUYENDO las marcadas por RFC — restar conteos (n_uhit -
    # n_hit) mezclaría anclas de tiempo (universo cuenta desde t0; marcadas
    # desde flag_date), dejando aciertos de marcadas en la base e inflándola.
    marcadas = set(f["rfc_norm"])
    nm = u[~u["rfc_norm"].isin(marcadas)]
    nm_tot, nm_hit = len(nm), int(nm["hit"].sum())
    rate_f = n_hit / n_f if n_f else None
    rate_b = nm_hit / nm_tot if nm_tot else None
    p_fisher = fisher_exact_greater(n_hit, n_f - n_hit,
                                    nm_hit, nm_tot - nm_hit) if n_f else None
    f_lo, f_hi = wilson_interval(n_hit, n_f) if n_f else (None, None)
    if rate_f is not None and rate_b:
        b_lo, b_hi = wilson_interval(nm_hit, nm_tot)
        lift_lo = (f_lo / b_hi) if b_hi else None
        lift_hi = (f_hi / b_lo) if b_lo else None
    else:
        lift_lo = lift_hi = None
    return {
        "señal": signal,
        "empresas_flag": n_f,
        "sancionadas_despues": n_hit,
        "tasa_flag_x10k": round(1e4 * rate_f, 1) if rate_f is not None else None,
        "tasa_flag_ic95": (f"{1e4 * f_lo:.0f}–{1e4 * f_hi:.0f}"
                           if f_lo is not None else None),
        "base_empresas": nm_tot,
        "base_sancionadas": nm_hit,
        "tasa_base_x10k": round(1e4 * rate_b, 1) if rate_b is not None else None,
        "lift": (rate_f / rate_b) if (rate_f is not None and rate_b) else None,
        "lift_ic95": (f"{lift_lo:.1f}–{lift_hi:.1f}"
                      if lift_lo is not None and lift_hi is not None else None),
        "p_fisher": round(p_fisher, 4) if p_fisher is not None else None,
        "mediana_dias_a_sancion": int(days.median()) if len(days) else None,
    }


def signal_flags(con) -> dict[str, pd.DataFrame]:
    """rfc_norm + flag_date per predictive signal."""
    # Los criterios SON los de los detectores — importados, no copiados:
    # ajustar un umbral en d02/d04 ajusta la tabla de precisión a la vez.
    d04 = young_winner_flags(con)
    d02 = direct_concentration_flags(con)

    splits = same_day_splits(con)
    d06_split = (splits.groupby("rfc_norm", as_index=False)["dia"].min()
                 .rename(columns={"dia": "flag_date"})
                 if len(splits) else pd.DataFrame(columns=["rfc_norm", "flag_date"]))

    rings = incorporation_cluster_members(con)
    d06_ring = (rings.groupby("rfc_norm", as_index=False)["primer_contrato"].min()
                .rename(columns={"primer_contrato": "flag_date"})
                if len(rings) else pd.DataFrame(columns=["rfc_norm", "flag_date"]))

    rot = rotation_members(con)
    d06_rot = (rot.groupby("rfc_norm", as_index=False)["primer_contrato"].min()
               .rename(columns={"primer_contrato": "flag_date"})
               if len(rot) else pd.DataFrame(columns=["rfc_norm", "flag_date"]))

    conv = inflated_modifications(con)
    d07 = (conv.assign(flag_date=pd.to_datetime(conv["fecha_contrato"]))
           .groupby("rfc", as_index=False)["flag_date"].min()
           .rename(columns={"rfc": "rfc_norm"})
           if len(conv) else pd.DataFrame(columns=["rfc_norm", "flag_date"]))

    return {
        "d04_joven_y_grande": d04,
        "d02_concentracion_directas": d02,
        "d06_fraccionamiento": d06_split,
        "d06_anillo_constitucion": d06_ring,
        "d06_rotacion": d06_rot,
        "d07_convenio_inflado": d07,
    }


def composite_flags(individuales: dict[str, pd.DataFrame],
                    min_senales: int = 2) -> pd.DataFrame:
    """rfc_norm + primera flag_date para proveedores que disparan al menos
    `min_senales` señales DISTINTAS. La fecha es la más temprana entre sus
    señales: el momento en que el apilamiento ya era visible."""
    largo = []
    for df in individuales.values():
        if df is not None and len(df):
            largo.append(df[["rfc_norm", "flag_date"]].dropna(
                subset=["rfc_norm"]))
    if not largo:
        return pd.DataFrame(columns=["rfc_norm", "flag_date"])
    cat = pd.concat(largo, ignore_index=True)
    cat["flag_date"] = pd.to_datetime(cat["flag_date"])
    # cuenta señales distintas por rfc: cada df aporta a lo más una; concatenar
    # ya las hace una por (rfc, señal) tras el groupby min de cada señal
    n = cat.groupby("rfc_norm").size()
    elegidos = n[n >= min_senales].index
    sub = cat[cat["rfc_norm"].isin(elegidos)]
    return (sub.groupby("rfc_norm", as_index=False)["flag_date"].min())


def main():
    con = duckdb.connect()
    load_views(con, sys.argv[1:] or None)
    load_sfp_views(con)

    sanctions = sanction_dates(con)
    universe = supplier_universe(con)
    individuales = signal_flags(con)
    señales = dict(individuales)
    # el ensamble: proveedores con >=2 señales distintas (ver d09)
    señales["compuesto_2+"] = composite_flags(individuales, min_senales=2)
    rows = [evaluate(name, flags, universe, sanctions)
            for name, flags in señales.items()]
    df = pd.DataFrame(rows).sort_values("lift", ascending=False, na_position="last")
    df["lift"] = df["lift"].round(1)
    df.to_csv(OUT / "f08_backtest_precision.csv", index=False)
    print("== backtest: ¿las señales predicen sanciones posteriores? ==")
    print(df.to_string(index=False))
    print("\nlift = tasa de sanción posterior de las marcadas / tasa base "
          "(empresas NO marcadas).\nlift_ic95 = intervalo de Wilson de cada "
          "tasa propagado al cociente; si su extremo inferior supera 1, el "
          "enriquecimiento\nno es ruido. p_fisher = Fisher exacto de una cola "
          "(marcadas vs no marcadas).\nHorizonte abierto dentro de la "
          "cobertura; mediana a sanción ~600-950 días, así que flags recientes "
          "(d04 sobre 2023+) aún no maduran y un 0 no refuta la señal.")


if __name__ == "__main__":
    main()
