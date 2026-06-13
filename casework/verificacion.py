"""Verificación determinista de un caso — sin RAG, sin embeddings.

Dos ayudas para el triaje, ambas exactas y reproducibles (lo que un documento
legal exige; un cruce probabilístico no):

  cross_match_name  para un renglón estatal SIN RFC válido, propone los RFC
                    candidatos cotejando el nombre normalizado contra el
                    índice 69-B (EFOS) y el directorio de sancionados (SFP).
                    Es ADVISORIO: solo un humano confirma el RFC.

  footprint         para un RFC o razón social, reúne TODOS sus contratos y
                    señales a lo largo de los hallazgos —federales y de los 32
                    estados— para armar la huella de la entidad en una sola
                    tabla con cita a su archivo de origen.

Esto cubre, de forma determinista, justo lo que un RAG aportaría aquí (cruce
difuso por nombre y huella entre estados) reutilizando los índices del propio
proyecto — más correcto y sin infraestructura nueva.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from shared.normalizacion import normalize

ROOT = Path(__file__).resolve().parent.parent
FINDINGS = ROOT / "findings"


def cross_match_name(razon_social: str, *, efos=None, sfp=None) -> list[dict]:
    """RFC candidatos para un nombre, por coincidencia de nombre normalizado.
    Los índices se inyectan en pruebas; en producción se cargan perezosamente
    y, si faltan los insumos crudos, se devuelve [] sin lanzar."""
    nombre = (razon_social or "").strip()
    if not nombre:
        return []
    if efos is None and sfp is None:
        efos, sfp = _lazy_indices()
    out: list[dict] = []
    if efos is not None:
        hit = efos.match_name(nombre)
        if hit:
            out.append({"rfc": hit.get("rfc"), "fuente": "69-B (EFOS)",
                        "situacion": hit.get("situacion"),
                        "nombre": hit.get("nombre")})
    if sfp is not None:
        for rec in sfp.match_name(nombre):
            out.append({"rfc": rec.get("rfc"), "fuente": "SFP sancionados",
                        "situacion": rec.get("plazo_txt"),
                        "inicio": str(rec.get("inicio")),
                        "fin": str(rec.get("fin")), "nombre": rec.get("nombre")})
    return out


def _lazy_indices():
    try:
        from realtime.efos_index import EfosIndex
        efos = EfosIndex()
    except Exception:
        efos = None
    try:
        from realtime.sfp_index import SfpIndex
        sfp = SfpIndex()
    except Exception:
        sfp = None
    return efos, sfp


# (archivo, ámbito, [columnas rfc], col_institución, col_proveedor,
#  col_fecha, col_importe, factor_importe, col_estado)
_SRC = [
    ("f05_durante_inhabilitacion.csv", "federal", ["rfc"], "institucion",
     "proveedor", "fecha_contrato", "importe", 1, None),
    ("f01_detalle_completo.csv", "federal", ["rfc"], "institucion",
     "proveedor", "fecha_contrato", "importe", 1, None),
    ("f07_convenios_inflados.csv", "federal", ["rfc"], "institucion",
     "proveedor", "fecha_contrato", "monto_ultimo_convenio", 1, None),
    ("f12_riesgo_proveedor.csv", "federal", ["rfc"], None, "proveedor",
     None, "monto_mxn_millones", 1_000_000, None),
    ("f10_inhabilitados_estatal.csv", "estatal", ["rfc_norm", "rfc"],
     "sujeto_obligado", "proveedor", "fecha_efectiva", "importe", 1,
     "estado_comprador"),
    ("f10_efos_estatal.csv", "estatal", ["rfc"], "sujeto_obligado",
     "proveedor", "fecha_contrato", "importe", 1, "estado_comprador"),
    ("f10_jovenes_estatal.csv", "estatal", ["rfc"], "sujeto_obligado",
     "proveedor", "fecha_contrato", "importe", 1, "estado_comprador"),
    ("f10_concentracion_estatal.csv", "estatal", [], "sujeto_obligado",
     "proveedor", None, "monto_mxn_millones", 1_000_000, "estado_comprador"),
]


def footprint(rfc: str | None = None, razon_social: str | None = None,
              findings_dir: Path = FINDINGS) -> pd.DataFrame:
    """Todos los contratos/señales de una entidad a lo largo de los hallazgos
    (federal + estatal). Coincide por RFC exacto o por nombre normalizado.
    Una sola tabla: origen, ámbito, estado, institución, proveedor, rfc,
    fecha, importe."""
    rfc_n = (rfc or "").strip().upper() or None
    nom_n = normalize(razon_social) if razon_social else None
    rows = []
    for (name, ambito, rfc_cols, inst_c, prov_c, fecha_c, imp_c, factor,
         est_c) in _SRC:
        p = Path(findings_dir) / name
        if not p.exists():
            continue
        df = pd.read_csv(p)
        mask = pd.Series(False, index=df.index)
        if rfc_n:
            for rc in rfc_cols:
                if rc in df.columns:
                    mask |= df[rc].astype(str).str.strip().str.upper() == rfc_n
        if nom_n and prov_c in df.columns:
            mask |= df[prov_c].map(lambda v: normalize(v) == nom_n)
        if not mask.any():
            continue
        for _, r in df[mask].iterrows():
            imp = r.get(imp_c)
            try:
                imp = float(imp) * factor if pd.notna(imp) else None
            except (TypeError, ValueError):
                imp = None
            rfc_val = None
            for rc in rfc_cols:
                if rc in df.columns and str(r.get(rc) or "").strip():
                    rfc_val = str(r.get(rc)).strip().upper()
                    break
            rows.append({
                "origen": name, "ambito": ambito,
                "estado": r.get(est_c) if est_c else None,
                "institucion": r.get(inst_c) if inst_c else None,
                "proveedor": r.get(prov_c) if prov_c in df.columns else None,
                "rfc": rfc_val,
                "fecha": r.get(fecha_c) if fecha_c and fecha_c in df.columns
                else None,
                "importe": imp})
    return pd.DataFrame(rows, columns=["origen", "ambito", "estado",
                                       "institucion", "proveedor", "rfc",
                                       "fecha", "importe"])
