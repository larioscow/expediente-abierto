#!/usr/bin/env python
"""Detector 09 — riesgo compuesto por proveedor (ensamble de señales).

Una sola señal es un cribado; varias señales INDEPENDIENTES sobre el mismo
proveedor son una pista. Este detector apila, por RFC, cuántas de las señales
predictivas dispararon (concentración de directas, joven-y-grande,
fraccionamiento, anillo de constitución, rotación, convenio inflado) y rankea
por número de señales distintas, monto y antigüedad de la primera marca.

Las definiciones SON las de los detectores — se importan vía
backtest.signal_flags(), así que ajustar un umbral mueve el ensamble a la vez.
El 69-B y la inhabilitación SFP se anexan como contexto confirmado (no suman
al puntaje predictivo: ya son la sanción, no un pronóstico de ella).

La validación vive en su backtest: la tasa de sanción POSTERIOR debe subir
con el número de señales — si apilar no predice mejor, el ensamble no sirve.
Eso se mide en detectors/backtest.py (tabla por número de señales) con IC de
Wilson y Fisher; aquí solo se construye y rankea el ranking publicable.

Usage: python -m detectors.d09_riesgo_proveedor [contracts.csv ...]
"""
import sys

import duckdb
import pandas as pd

from detectors.backtest import signal_flags
from detectors.common import MXN_OK, OUT, load_sfp_views, load_views

# nombre legible por señal, para la columna "señales" del ranking
ETIQUETA = {
    "d02_concentracion_directas": "concentración de adjudicaciones directas",
    "d04_joven_y_grande": "empresa joven con contrato grande",
    "d06_fraccionamiento": "fraccionamiento el mismo día",
    "d06_anillo_constitucion": "constituidas casi al mismo tiempo",
    "d06_rotacion": "rotación de ganadores",
    "d07_convenio_inflado": "convenio por encima del tope legal",
}


def riesgo_proveedor(con) -> pd.DataFrame:
    """Una fila por RFC con >=1 señal predictiva: cuántas y cuáles, primera
    marca, monto total y dependencias, más el contexto de sanción."""
    flags = signal_flags(con)
    largo = []
    for senal, df in flags.items():
        if df is None or df.empty:
            continue
        d = df[["rfc_norm", "flag_date"]].dropna(subset=["rfc_norm"]).copy()
        d["flag_date"] = pd.to_datetime(d["flag_date"], errors="coerce")
        d["senal"] = senal
        largo.append(d)
    if not largo:
        return pd.DataFrame(columns=[
            "rfc", "proveedor", "n_senales", "senales", "primera_marca",
            "contratos", "monto_mxn_millones", "dependencias",
            "en_69b", "situacion_69b", "inhabilitado_sfp"])
    largo = pd.concat(largo, ignore_index=True)

    por_rfc = largo.groupby("rfc_norm").agg(
        n_senales=("senal", "nunique"),
        senales_raw=("senal", lambda s: sorted(set(s))),
        primera_marca=("flag_date", "min"),
    ).reset_index()
    por_rfc["senales"] = por_rfc["senales_raw"].apply(
        lambda ss: "; ".join(ETIQUETA.get(s, s) for s in ss))

    # contexto del proveedor desde los contratos (nombre, monto, alcance)
    ctx = con.execute(f"""
        SELECT rfc_norm,
          any_value(proveedor) AS proveedor,
          count(*) AS contratos,
          round(sum(importe) FILTER {MXN_OK} / 1e6, 2) AS monto_mxn_millones,
          count(DISTINCT institucion) AS dependencias
        FROM contracts WHERE rfc_norm IS NOT NULL GROUP BY 1
    """).fetchdf()
    # sanciones confirmadas: 69-B y ventana SFP (contexto, no puntúa)
    s69 = con.execute("""
        SELECT rfc_norm, max(situacion) AS situacion_69b FROM efos GROUP BY 1
    """).fetchdf()
    try:
        sfp = con.execute("""
            SELECT DISTINCT rfc_norm, TRUE AS inhabilitado_sfp FROM sfp
        """).fetchdf()
    except duckdb.CatalogException:
        sfp = pd.DataFrame(columns=["rfc_norm", "inhabilitado_sfp"])

    out = (por_rfc.merge(ctx, on="rfc_norm", how="left")
           .merge(s69, on="rfc_norm", how="left")
           .merge(sfp, on="rfc_norm", how="left"))
    out["en_69b"] = out["situacion_69b"].notna()
    out["inhabilitado_sfp"] = out["inhabilitado_sfp"].fillna(False)
    out = out.rename(columns={"rfc_norm": "rfc"})
    out = out.sort_values(
        ["n_senales", "monto_mxn_millones"], ascending=[False, False])
    return out[["rfc", "proveedor", "n_senales", "senales", "primera_marca",
                "contratos", "monto_mxn_millones", "dependencias",
                "en_69b", "situacion_69b", "inhabilitado_sfp"]].reset_index(
        drop=True)


def main():
    con = duckdb.connect()
    load_views(con, sys.argv[1:] or None)
    load_sfp_views(con)
    df = riesgo_proveedor(con)
    df.to_csv(OUT / "f12_riesgo_proveedor.csv", index=False)

    print(f"proveedores con >=1 señal predictiva: {len(df)}")
    print("\n== distribución por número de señales ==")
    dist = (df.groupby("n_senales")
            .agg(proveedores=("rfc", "size"),
                 ya_sancionados=("en_69b", "sum"))
            .reset_index().sort_values("n_senales", ascending=False))
    dist["pct_ya_sancionado"] = (
        100 * dist["ya_sancionados"] / dist["proveedores"]).round(1)
    print(dist.to_string(index=False))
    print("\n== top 20 proveedores por número de señales ==")
    cols = ["proveedor", "n_senales", "monto_mxn_millones", "dependencias",
            "en_69b", "inhabilitado_sfp", "senales"]
    print(df[cols].head(20).to_string(index=False, max_colwidth=46))
    print(f"\nwrote {len(df)} -> findings/f12_riesgo_proveedor.csv")
    print("La validación (¿apilar señales predice más sanciones?) está en "
          "detectors/backtest.py, fila 'compuesto_2+'.")


if __name__ == "__main__":
    main()
