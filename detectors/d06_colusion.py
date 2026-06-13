#!/usr/bin/env python
"""Detector 06 — collusion screens from winners-only contract data.

ComprasMX's bulk CSV exposes winners, not bidders, so these are structural
markers computable without participant lists:

  rotation  — inside one unidad compradora, a small CLOSED group of suppliers
              splits public-tender wins near-evenly. In open competition the
              winner set is broad and shares are uneven; a stable 2–5 supplier
              group with balanced shares is the classic bid-rotation footprint.
  ring      — winners in the same UC incorporated within days of each other
              (batch-created companies winning in the same buying office).
  split     — one supplier, one UC, one day, several direct awards
              (fraccionamiento: slicing to stay under approval thresholds).

Every output row is a SCREEN requiring human verification, never a verdict.

Usage: python detectors/d06_colusion.py [contracts.csv ...]
"""
import math
import sys

import pandas as pd

from detectors.common import MXN_OK as MXN, OUT, load_views


def _evenness(counts) -> float:
    """Normalized Shannon entropy of win shares: 1.0 = perfectly even split."""
    total = sum(counts)
    shares = [c / total for c in counts if c]
    if len(shares) < 2:
        return 0.0
    h = -sum(s * math.log(s) for s in shares)
    return h / math.log(len(shares))


def _rotation_base(con) -> pd.DataFrame:
    return con.execute(f"""
        SELECT institucion, nombre_uc, proveedor, rfc_norm,
               count(*) AS n,
               sum(importe) FILTER ({MXN}) AS monto,
               count(DISTINCT file_year) AS anios,
               min(fecha_efectiva)::DATE AS primer_contrato
        FROM contracts
        WHERE tipo_procedimiento ILIKE 'LICITACI%' AND nombre_uc IS NOT NULL
        GROUP BY 1, 2, 3, 4
    """).fetchdf()


def _rotation_groups(con, min_contracts, max_suppliers, min_evenness):
    """Yield (institucion, uc, group_df, evenness) for flagged UCs."""
    for (inst, uc), g in _rotation_base(con).groupby(["institucion", "nombre_uc"]):
        total = int(g["n"].sum())
        if total < min_contracts or not (2 <= len(g) <= max_suppliers):
            continue
        ev = _evenness(g["n"].tolist())
        if ev >= min_evenness:
            yield inst, uc, g, ev


def rotation_members(con, min_contracts=12, max_suppliers=5,
                     min_evenness=0.75) -> pd.DataFrame:
    """One row per supplier participating in a flagged rotation group."""
    rows = [{"institucion": inst, "nombre_uc": uc, "rfc_norm": r.rfc_norm,
             "proveedor": r.proveedor, "primer_contrato": r.primer_contrato}
            for inst, uc, g, _ in _rotation_groups(con, min_contracts,
                                                   max_suppliers, min_evenness)
            for r in g.itertuples()]
    return pd.DataFrame(rows, columns=["institucion", "nombre_uc", "rfc_norm",
                                       "proveedor", "primer_contrato"])


def rotation_candidates(con, min_contracts=12, max_suppliers=5,
                        min_evenness=0.75) -> pd.DataFrame:
    """UCs where 2..max_suppliers suppliers hold ALL public-tender wins,
    split near-evenly across at least min_contracts contracts."""
    rows = []
    for inst, uc, g, ev in _rotation_groups(con, min_contracts, max_suppliers,
                                            min_evenness):
        total = int(g["n"].sum())
        rows.append({
            "institucion": inst, "nombre_uc": uc,
            "contratos": total, "n_proveedores": len(g),
            "evenness": round(ev, 3),
            "anios_activos": int(g["anios"].max()),
            "monto_mxn_millones": round(float(g["monto"].sum() or 0) / 1e6, 1),
            "proveedores": " | ".join(
                f"{r.proveedor} ({r.n})" for r in
                g.sort_values("n", ascending=False).itertuples()),
        })
    return (pd.DataFrame(rows)
            .sort_values("monto_mxn_millones", ascending=False, ignore_index=True)
            if rows else pd.DataFrame(columns=[
                "institucion", "nombre_uc", "contratos", "n_proveedores",
                "evenness", "anios_activos", "monto_mxn_millones", "proveedores"]))


def widest_incorporation_run(base, group_cols, window_days=30,
                             min_companies=3) -> pd.DataFrame:
    """Por grupo, devuelve las empresas dentro de la ventana de constitución
    MÁS ANCHA (>= min_companies constituidas en <= window_days). Lógica pura
    reutilizada por la versión federal (contracts) y la estatal (contracts_pnt);
    base trae group_cols + rfc_norm + constituida (DATE) + lo demás a conservar."""
    out = []
    for _, g in base.groupby(group_cols):
        g = g.drop_duplicates("rfc_norm").sort_values(["constituida", "rfc_norm"])
        if len(g) < min_companies:
            continue
        dates = g["constituida"].tolist()
        best = None
        for i in range(len(dates)):
            j = i
            while j + 1 < len(dates) and (dates[j + 1] - dates[i]).days <= window_days:
                j += 1
            if j - i + 1 >= min_companies and (best is None or j - i > best[1] - best[0]):
                best = (i, j)
        if best is not None:
            out.append(g.iloc[best[0]:best[1] + 1])
    return pd.concat(out, ignore_index=True) if out else base.iloc[0:0]


def incorporation_cluster_members(con, window_days=30,
                                  min_companies=3) -> pd.DataFrame:
    """One row per company inside a flagged incorporation cluster."""
    base = con.execute(f"""
        SELECT institucion, nombre_uc, rfc_norm, any_value(proveedor) AS proveedor,
               fecha_constitucion_rfc::DATE AS constituida,
               min(fecha_efectiva)::DATE AS primer_contrato,
               count(*) AS contratos,
               sum(importe) FILTER ({MXN}) AS monto
        FROM contracts
        WHERE es_persona_moral AND fecha_constitucion_rfc IS NOT NULL
          AND nombre_uc IS NOT NULL
        GROUP BY 1, 2, 3, 5
    """).fetchdf()
    cols = ["institucion", "nombre_uc", "rfc_norm", "proveedor", "constituida",
            "primer_contrato", "contratos", "monto"]
    res = widest_incorporation_run(base, ["institucion", "nombre_uc"],
                                   window_days, min_companies)
    return res[cols] if len(res) else pd.DataFrame(columns=cols)


def incorporation_clusters(con, window_days=30, min_companies=3) -> pd.DataFrame:
    """Winners in the same UC whose RFC incorporation dates fall within a
    window_days span — batch-created companies selling to one buying office."""
    members = incorporation_cluster_members(con, window_days, min_companies)
    rows = []
    for (inst, uc), cluster in members.groupby(["institucion", "nombre_uc"]):
        rows.append({
            "institucion": inst, "nombre_uc": uc,
            "empresas": len(cluster),
            "dias_entre_constituciones":
                (cluster["constituida"].max() - cluster["constituida"].min()).days,
            "constituidas_desde": str(cluster["constituida"].min()),
            "constituidas_hasta": str(cluster["constituida"].max()),
            "contratos": int(cluster["contratos"].sum()),
            "monto_mxn_millones": round(float(cluster["monto"].sum() or 0) / 1e6, 1),
            "proveedores": " | ".join(
                f"{r.proveedor} ({r.rfc_norm}, {r.constituida})"
                for r in cluster.itertuples()),
        })
    return (pd.DataFrame(rows)
            .sort_values("monto_mxn_millones", ascending=False, ignore_index=True)
            if rows else pd.DataFrame(columns=[
                "institucion", "nombre_uc", "empresas", "dias_entre_constituciones",
                "constituidas_desde", "constituidas_hasta", "contratos",
                "monto_mxn_millones", "proveedores"]))


def same_day_splits(con, min_contracts=3, min_total=5_000_000) -> pd.DataFrame:
    """One supplier, one UC, one day, several direct awards — slicing."""
    return con.execute(f"""
        SELECT institucion, nombre_uc, proveedor, rfc_norm,
               fecha_efectiva::DATE AS dia,
               count(*) AS contratos,
               sum(importe) AS total_mxn,
               round(max(importe) / sum(importe), 2) AS pct_mayor
        FROM contracts
        WHERE tipo_procedimiento ILIKE 'ADJUDICACI%DIRECTA%'
          AND fecha_efectiva IS NOT NULL AND importe IS NOT NULL AND {MXN}
          AND nombre_uc IS NOT NULL
        GROUP BY 1, 2, 3, 4, 5
        HAVING count(*) >= {int(min_contracts)} AND sum(importe) >= {float(min_total)}
        ORDER BY total_mxn DESC, rfc_norm, dia
    """).fetchdf()


def main():
    import duckdb

    con = duckdb.connect()
    load_views(con, sys.argv[1:] or None)

    rot = rotation_candidates(con)
    rot.to_csv(OUT / "f06_rotacion_licitaciones.csv", index=False)
    print(f"== rotación: grupos cerrados repartiéndose licitaciones: {len(rot)} UCs ==")
    print(rot.head(15).to_string(index=False, max_colwidth=60))

    ring = incorporation_clusters(con)
    ring.to_csv(OUT / "f06_anillos_constitucion.csv", index=False)
    print(f"\n== anillos: ganadoras constituidas con días de diferencia: {len(ring)} UCs ==")
    print(ring.head(15).to_string(index=False, max_colwidth=60))

    splits = same_day_splits(con)
    splits.to_csv(OUT / "f06_fraccionamiento_mismo_dia.csv", index=False)
    print(f"\n== fraccionamiento: >=3 directas mismo día/proveedor/UC: {len(splits)} casos ==")
    print(splits.head(15).to_string(index=False, max_colwidth=50))


if __name__ == "__main__":
    main()
