#!/usr/bin/env python
"""Export findings/ to web/src/data/*.json and copy the CSVs to
web/public/datos/.

The Next.js site (web/) is intentionally dumb: every figure it publishes is
computed here, from the findings, at export time — nothing is hand-written
into the frontend. Run after the detectors; the web build consumes the JSON.
"""
import hashlib
import io
import json
import re
import sys
from csv import reader as csv_reader
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from realtime.packets import load_alerts as _load_alerts  # noqa: E402

FINDINGS = ROOT / "findings"
WEB = ROOT / "web"


def read_csv(name, base=None):
    p = (base or FINDINGS) / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def denuncias_folios(base=None) -> list[str]:
    """Folios de denuncias presentadas.

    Fuente primaria: los acuses PDF archivados (solo locales: contienen datos
    personales y no se publican). Cuando existen, se regenera el listado
    público de folios (rastreado en git) para que CI construya con la cifra
    correcta; sin acuses, se lee ese listado.
    """
    dir_denuncias = (base or FINDINGS) / "denuncias"
    publicos = dir_denuncias / "folios_publicos.json"
    folios = sorted(p.stem.removeprefix("acuse_")
                    for p in (dir_denuncias / "acuses").glob("acuse_*.pdf"))
    if folios:
        publicos.parent.mkdir(parents=True, exist_ok=True)
        publicos.write_text(json.dumps(folios, indent=1), encoding="utf-8")
        return folios
    if publicos.exists():
        return json.loads(publicos.read_text())
    return []


# ------------------------------------------------- denuncias con su caso

_FOLIO = re.compile(r"SIDEC folio (\d+)/(\d{4})")
_RFC_EN_NOMBRE = re.compile(r"\(([A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3})\)")


def parse_folio(nota) -> str | None:
    """'SIDEC folio 83017/2026 clave …' -> '83017-2026'. La clave de
    seguimiento jamás sale de aquí: con ella se accede al expediente."""
    m = _FOLIO.search(str(nota or ""))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def casos_denunciados(store_rows: list[dict], f05: pd.DataFrame) -> list[dict]:
    """Une cada contrato de f05 con el folio de su denuncia.

    El store guarda los casos f05 con numero = nombre del borrador
    (inhabilitado_RFC_FECHA[-N], mismo orden que nombres_f05); los casos que
    nacieron de una alerta solo traen el RFC en el nombre y se asignan a los
    contratos de ese RFC que quedaron sin folio. Devuelve un grupo por
    empresa, listo para publicarse (folio sí, clave no).
    """
    from casework.denuncias import nombres_f05

    if f05.empty:
        return []
    filas = [r for _, r in f05.iterrows()]
    nombre_a_fila = dict(zip(nombres_f05(filas), filas))
    folio_por_idx: dict[int, str] = {}
    pendientes: list[tuple[str, str]] = []  # (rfc, folio) de casos-alerta

    for row in store_rows:
        folio = parse_folio(row.get("nota"))
        if not folio or row.get("estado") != "denunciado":
            continue
        numero = str(row.get("numero") or "")
        if numero.startswith("inhabilitado_") and numero in nombre_a_fila:
            folio_por_idx[id(nombre_a_fila[numero])] = folio
        else:
            m = _RFC_EN_NOMBRE.search(str(row.get("nombre") or ""))
            if m:
                pendientes.append((m.group(1), folio))

    for rfc, folio in pendientes:
        for fila in filas:
            if fila["rfc"] == rfc and id(fila) not in folio_por_idx:
                folio_por_idx[id(fila)] = folio
                break

    # Cada denuncia es consolidada por (rfc, institución): su folio ampara
    # todos los contratos de ese grupo, aunque el store registre uno solo.
    folio_por_grupo = {
        (fila["rfc"], fila["institucion"]): folio_por_idx[id(fila)]
        for fila in filas if id(fila) in folio_por_idx}
    for fila in filas:
        clave_grupo = (fila["rfc"], fila["institucion"])
        if id(fila) not in folio_por_idx and clave_grupo in folio_por_grupo:
            folio_por_idx[id(fila)] = folio_por_grupo[clave_grupo]

    grupos: dict[str, dict] = {}
    for fila in filas:
        folio = folio_por_idx.get(id(fila))
        if not folio:
            continue
        g = grupos.setdefault(fila["rfc"], {
            "empresa": fila["proveedor"], "rfc": fila["rfc"],
            "inhabilitada_desde": fila["inhabilitado_desde"],
            "inhabilitada_hasta": fila["hasta"],
            "contratos": [], "folios": [],
        })
        importe = fila.get("importe")
        g["contratos"].append({
            "fecha": fila["fecha_contrato"], "institucion": fila["institucion"],
            "monto_mxn_millones": float(fila["monto_mxn_millones"]),
            "importe_mxn": (float(importe) if importe is not None
                            and not pd.isna(importe)
                            else float(fila["monto_mxn_millones"]) * 1e6),
            "url": fila.get("direccion_anuncio"), "folio": folio,
        })
        if folio not in g["folios"]:
            g["folios"].append(folio)
    return sorted(grupos.values(),
                  key=lambda g: -sum(c["importe_mxn"] for c in g["contratos"]))


def denuncias_publicas(base=None) -> list[dict]:
    """Casos denunciados con folio, para el sitio. Con el store local
    presente se regenera el archivo rastreado; sin él (CI) se lee."""
    dir_denuncias = (base or FINDINGS) / "denuncias"
    publicas = dir_denuncias / "denuncias_publicas.json"
    db = ROOT / "data" / "cases.duckdb"
    if db.exists():
        import duckdb
        con = duckdb.connect(str(db), read_only=True)
        cols = ["numero", "nombre", "estado", "nota"]
        store_rows = [dict(zip(cols, r)) for r in con.execute(
            f"SELECT {', '.join(cols)} FROM cases").fetchall()]
        con.close()
        casos = casos_denunciados(
            store_rows, read_csv("f05_durante_inhabilitacion.csv", base=base))
        if casos:
            publicas.parent.mkdir(parents=True, exist_ok=True)
            publicas.write_text(
                json.dumps(casos, ensure_ascii=False, indent=1), encoding="utf-8")
        return casos
    if publicas.exists():
        return json.loads(publicas.read_text())
    return []


def _monto_m(v) -> float:
    return round(float(v) / 1e6, 2) if v is not None and not pd.isna(v) else 0.0


def inhabilitadas_unidas(f05, f10_dur) -> list[dict]:
    """Contratos firmados durante una inhabilitación, federal y estatal en una
    sola lista, con el ámbito (federal o el estado) y el comprador unificado.
    Mismo cruce por RFC en ambos casos; ordenados por monto."""
    filas = []
    for r in records(f05):
        filas.append({
            "proveedor": r["proveedor"], "rfc": r["rfc"], "ambito": "federal",
            "desde": r["inhabilitado_desde"], "hasta": r["hasta"],
            "fecha_contrato": r["fecha_contrato"], "comprador": r["institucion"],
            "monto_mxn_millones": _monto_m(r["importe"]),
            "direccion_anuncio": r["direccion_anuncio"]})
    for r in records(f10_dur):
        filas.append({
            "proveedor": r["proveedor"], "rfc": r["rfc_norm"],
            "ambito": str(r["estado_comprador"]).title(),
            "desde": r["inicio"], "hasta": r["fin"],
            "fecha_contrato": r["fecha_efectiva"],
            "comprador": r["sujeto_obligado"],
            "monto_mxn_millones": _monto_m(r["importe"]),
            "direccion_anuncio": r["direccion_anuncio"]})
    return sorted(filas, key=lambda x: -x["monto_mxn_millones"])


def factureras_unidas(f01_def, f10_def) -> list[dict]:
    """Contratos a factureras 69-B confirmadas (definitivo), federal y estatal,
    verificados por RFC. Una lista con ámbito y comprador unificado."""
    def fila(prov, rfc, ambito, dof, fecha, comprador, monto, url):
        return {"proveedor": prov, "rfc": rfc, "ambito": ambito,
                "definitivo_dof": dof, "fecha_contrato": fecha,
                "comprador": comprador, "monto_mxn_millones": monto,
                "direccion_anuncio": url}
    filas = [fila(r["proveedor"], r["rfc"], "federal", r["definitivo_dof"],
                  r["fecha_contrato"], r["institucion"],
                  r["monto_mxn_millones"], r["direccion_anuncio"])
             for r in records(f01_def)]
    filas += [fila(r["proveedor"], r["rfc"], str(r["estado_comprador"]).title(),
                   r["definitivo_dof"], r["fecha_contrato"], r["sujeto_obligado"],
                   _monto_m(r["importe"]), r["direccion_anuncio"])
              for r in records(f10_def)]
    return sorted(filas, key=lambda x: -(x["monto_mxn_millones"] or 0))


def compute_cifras(f_dir=None) -> dict:
    """Todas las cifras escalares que publica el sitio — testeadas en
    tests/test_cifras_sitio.py; un error aquí es un error publicado."""
    rc = lambda n: read_csv(n, base=f_dir)
    r01 = rc("f01_resumen_por_situacion.csv")
    defin = r01[r01["situacion"] == "Definitivo"] if not r01.empty else r01
    r01h = rc("f01h_resumen_por_situacion.csv")
    dh = r01h[r01h["situacion"] == "Definitivo"] if not r01h.empty else r01h
    r04 = rc("f04_resumen.csv")
    r03 = rc("f03_benford_instituciones.csv")
    f08 = rc("f08_backtest_precision.csv")
    return {
        "d01_monto": defin["monto_mxn_millones"].sum() if not defin.empty else 0,
        "d01h_monto": dh["monto_mxn_millones"].sum() if not dh.empty else 0,
        "d01h_contratos": int(dh["contratos"].sum()) if not dh.empty else 0,
        "d01h_empresas": int(dh["empresas"].sum()) if not dh.empty else 0,
        "d04_monto": r04["monto_a_menores_1a_mxn_m"].sum() if not r04.empty else 0,
        "d05_gun": len(rc("f05_durante_inhabilitacion.csv")),
        "d03_noconf": int((r03["banda_nigrini"] == "NO CONFORME").sum()) if not r03.empty else 0,
        "d03_total": len(r03),
        "d07_n": len(rc("f07_convenios_inflados.csv")),
        "best_lift": f08["lift"].max() if not f08.empty else 0,
    }


def records(df, cols=None, n=None):
    """DataFrame -> list[dict] JSON-seguro (NaN -> None)."""
    if df.empty:
        return []
    if cols:
        df = df[[c for c in cols if c in df.columns]]
    if n:
        df = df.head(n)
    return json.loads(df.to_json(orient="records"))


def year_range(series: pd.Series) -> str:
    """'2010–2023' a partir de una columna de fechas ISO."""
    years = pd.to_datetime(series, errors="coerce").dt.year.dropna()
    if years.empty:
        return "—"
    lo, hi = int(years.min()), int(years.max())
    return str(lo) if lo == hi else f"{lo}–{hi}"


def csv_rows(data: bytes) -> int:
    """Filas reales del CSV (los campos pueden traer saltos de línea)."""
    return max(0, sum(1 for _ in csv_reader(io.StringIO(data.decode("utf-8")))) - 1)


def publicar_csvs(destino: Path, f_dir=None) -> list[dict]:
    """Copia los findings CSV y devuelve nombre + sha256 + filas."""
    destino.mkdir(parents=True, exist_ok=True)
    publicados = []
    for f in sorted((f_dir or FINDINGS).glob("f*.csv")):
        data = f.read_bytes()
        (destino / f.name).write_bytes(data)
        publicados.append({
            "nombre": f.name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "filas": csv_rows(data),
        })
    return publicados


def main(out_dir=None):
    out = Path(out_dir) if out_dir else WEB
    data_dir = out / "src" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    c = compute_cifras()
    f05 = read_csv("f05_durante_inhabilitacion.csv")
    f01 = read_csv("f01_detalle_completo.csv")
    f01_def = (f01[f01["situacion"] == "Definitivo"]
               .sort_values("importe", ascending=False)
               if not f01.empty else f01)
    f01h_top = read_csv("f01h_top25_post_definitivo.csv")
    f04 = read_csv("f04_top30_jovenes_grandes.csv")
    f06rot = read_csv("f06_rotacion_licitaciones.csv")
    f06ring = read_csv("f06_anillos_constitucion.csv")
    f06split = read_csv("f06_fraccionamiento_mismo_dia.csv")
    f07 = read_csv("f07_convenios_inflados.csv")
    f02inst = read_csv("f02_instituciones_pct_directas.csv")
    f02dep = read_csv("f02_dependencia_proveedor_unico.csv")
    alerts = _load_alerts(FINDINGS / "alerts.jsonl", limit=40)
    casos = denuncias_publicas()
    folios = sorted(set(denuncias_folios())
                    | {f for c in casos for f in c["folios"]})

    # capa estatal (PNT, los 32 estados) — solo los cruces por RFC, que son
    # la misma vara de evidencia que las páginas federales; las pantallas
    # (jóvenes, concentración, anillos) quedan como descarga
    f10_inh = read_csv("f10_inhabilitados_estatal.csv")
    f10_dur = (f10_inh[f10_inh["durante_inhabilitacion"]]
               .sort_values("importe", ascending=False)
               if not f10_inh.empty else f10_inh)
    f10_efos = read_csv("f10_efos_estatal.csv")
    # solo definitivos con monto plausible: los montos absurdos de captura no
    # entran a la tabla ni a las sumas
    f10_def = (f10_efos[(f10_efos["situacion"] == "Definitivo")
                        & (f10_efos["importe_plausible"])]
               .sort_values("importe", ascending=False)
               if not f10_efos.empty else f10_efos)
    if not f10_dur.empty:
        f10_dur = f10_dur.assign(
            monto_mxn_millones=(f10_dur["importe"] / 1e6).round(2))
    if not f10_def.empty:
        f10_def = f10_def.assign(
            monto_mxn_millones=(f10_def["importe"] / 1e6).round(2))
    f10_jov = read_csv("f10_jovenes_estatal.csv")
    f10_conc = read_csv("f10_concentracion_estatal.csv")
    f10_anillos = read_csv("f10_anillos_estatal.csv")
    f10_cob = read_csv("f10_cobertura_estatal.csv")

    if not f01_def.empty:
        f01_def = f01_def.assign(
            monto_mxn_millones=(f01_def["importe"] / 1e6).round(2))

    cifras = {
        **{k: (round(float(v), 1) if isinstance(v, float) else v)
           for k, v in c.items()},
        "inhabilitadas_n": int(len(f05) + len(f10_dur)),
        "facturera_rfc_monto": round(float(c["d01_monto"]) + (
            f10_def["importe"].sum() / 1e6 if not f10_def.empty else 0), 1),
        "facturera_rfc_contratos": int(len(f01_def) + len(f10_def)),
        "facturera_rfc_rango": year_range(f01_def["fecha_contrato"]) if not f01_def.empty else "—",
        "facturera_hist_monto": round(float(c["d01h_monto"]), 1),
        "facturera_hist_contratos": c["d01h_contratos"],
        "facturera_hist_empresas": c["d01h_empresas"],
        "sobrecostos_n": c["d07_n"],
        "jovenes_monto": round(float(c["d04_monto"]), 1),
        "alertas_n": len(alerts),
        "denuncias_n": len(folios),
        "estatal_durante_n": int(len(f10_dur)),
        "estatal_facturera_n": int(len(f10_def)),
        "estatal_estados_n": int(f10_cob["estado_comprador"].nunique())
        if not f10_cob.empty else 0,
    }

    exports = {
        "meta.json": {
            "corte": date.today().isoformat(),
            "alertas_ultima": max((a["ts"] for a in alerts), default=None),
        },
        "cifras.json": cifras,
        "denuncias.json": {"folios": folios, "casos": casos},
        "inhabilitadas.json": {"contratos": inhabilitadas_unidas(f05, f10_dur)},
        "factureras.json": {
            "confirmadas_rfc": factureras_unidas(f01_def, f10_def),
            "historico_nombre": records(f01h_top, n=25),
        },
        "sobrecostos.json": {"contratos": records(f07, cols=[
            "proveedor", "institucion", "monto_original",
            "monto_ultimo_convenio", "pct_incremento", "tope_legal_pct",
            "fecha_contrato", "direccion_anuncio"])},
        "colusion.json": {
            "rotacion": records(f06rot, cols=[
                "institucion", "nombre_uc", "contratos", "n_proveedores",
                "monto_mxn_millones", "proveedores"]),
            "anillos": records(f06ring, cols=[
                "institucion", "nombre_uc", "empresas",
                "dias_entre_constituciones", "contratos",
                "monto_mxn_millones"], n=20),
            "fraccionamiento": records(f06split, cols=[
                "institucion", "nombre_uc", "proveedor", "dia", "contratos",
                "total_mxn"], n=20),
            # totales del hallazgo completo: el sitio publica muestras de 20
            # filas, pero los titulares deben salir de los CSV íntegros
            "resumen": {
                "rotacion_total": len(f06rot),
                "anillos_total": len(f06ring),
                "fraccionamiento_total": len(f06split),
                "oficinas_total": int(pd.concat(
                    [df[["institucion", "nombre_uc"]]
                     for df in (f06rot, f06ring, f06split) if not df.empty]
                ).drop_duplicates().shape[0]) if not (
                    f06rot.empty and f06ring.empty and f06split.empty) else 0,
            },
        },
        "recien_creadas.json": {
            "contratos": records(f04, cols=[
                "proveedor", "constituida", "fecha_contrato", "edad_dias",
                "institucion", "tipo_procedimiento", "monto_mxn_millones",
                "tipo_monto", "direccion_anuncio"]),
            "resumen": {
                "jovenes_grandes_total": int(
                    read_csv("f04_resumen.csv")["jovenes_y_grandes"].sum())
                if not read_csv("f04_resumen.csv").empty else 0,
                "top_monto_mxn_m": round(
                    float(f04["monto_mxn_millones"].sum()), 1)
                if not f04.empty else 0,
            },
        },
        "sin_competencia.json": {
            "instituciones": records(f02inst, n=15),
            "proveedor_unico": records(f02dep, n=10),
            # el dinero directo se calcula sobre las 40 instituciones del
            # hallazgo, no solo las 15 publicadas, y solo la parte directa
            "resumen": {
                "instituciones_total": len(f02inst),
                "monto_directas_mxn_m": round(float(
                    (f02inst["monto_mxn_millones"]
                     * f02inst["pct_directas_monto"] / 100).sum()), 1)
                if not f02inst.empty else 0,
                "contratos_total": int(f02inst["contratos"].sum())
                if not f02inst.empty else 0,
            },
        },
        "alertas.json": {"alertas": alerts},
        "estados.json": {
            "durante": records(f10_dur, cols=[
                "estado_comprador", "sujeto_obligado", "proveedor", "rfc_norm",
                "inicio", "fin", "fecha_efectiva", "monto_mxn_millones",
                "direccion_anuncio"]),
            "factureras": records(f10_def, cols=[
                "estado_comprador", "sujeto_obligado", "proveedor", "rfc",
                "definitivo_dof", "fecha_contrato", "monto_mxn_millones",
                "direccion_anuncio"], n=40),
            "resumen": {
                "estados": int(f10_cob["estado_comprador"].nunique())
                if not f10_cob.empty else 0,
                "durante_total": int(len(f10_dur)),
                "facturera_total": int(len(f10_def)),
                "jovenes_total": int(len(f10_jov)),
                "concentracion_total": int(len(f10_conc)),
                "anillos_total": int(len(f10_anillos)),
                "facturera_monto_mxn_m": round(
                    float(f10_def["importe"].sum()) / 1e6, 1)
                if not f10_def.empty else 0,
            },
        },
    }

    datos = publicar_csvs(out / "public" / "datos")
    situaciones = {}
    for nombre, df in (("f01_detalle_completo.csv", f01),
                       ("f01h_detalle_completo.csv",
                        read_csv("f01h_detalle_completo.csv"))):
        if not df.empty and "situacion" in df.columns:
            situaciones[nombre] = df["situacion"].value_counts().to_dict()
    exports["datos.json"] = {"archivos": datos, "situaciones": situaciones}

    for name, payload in exports.items():
        (data_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(exports)} JSON + {len(datos)} CSVs -> {out}")


if __name__ == "__main__":
    main()
