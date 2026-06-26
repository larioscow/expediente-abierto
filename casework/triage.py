"""Triaje de hallazgos a denuncias — federal y estatal, en un solo libro.

Lee TODOS los hallazgos de los detectores (federales y de los estados),
normaliza cada uno a un caso, le asigna un tier de "denunciabilidad" y una
puntuación, lo coteja contra lo ya presentado (denuncias_publicas.json) y
contra el propio libro de casos, y persiste la decisión humana para no volver
a revisar un caso ya resuelto — el patrón de "libro de vistos" de reaper-deals.

NUNCA presenta una denuncia: triaja, puntúa y ordena. Un humano presenta.
Los casos con evidencia incompleta o implausible quedan en CUARENTENA, no se
filtran en silencio ni se proponen para presentar.

Granularidad = unidad de denuncia:
  inhabilitado     -> un caso por (proveedor, institución/sujeto obligado)
  efos             -> un caso por (proveedor[, sujeto])
  convenio         -> un caso por contrato
  rotación/anillo  -> un caso por unidad compradora
  fraccionamiento  -> un caso por (proveedor, UC, día)
  riesgo/joven/concentración -> un caso por proveedor o (sujeto, proveedor)

Tablas (data/cases.duckdb, aditivas — no tocan el dashboard en marcha):
  triage            un renglón por caso, con estado humano que scan jamás pisa
  triage_runs       una corrida por scan (auditoría/diferencia)
  triage_emissions  qué casos se emitieron (nuevo|cambiado) en cada corrida

Uso:
    python -m casework.triage scan [--json]
    python -m casework.triage list [--estado E] [--ambito A] [--tier T] [--json]
    python -m casework.triage show <case_id> [--json]
    python -m casework.triage review <case_id> <estado> [nota...] [--folio F]
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from casework.denuncias import (denuncia_efos_post_definitivo,
                                denuncia_inhabilitado_estatal,
                                denuncia_inhabilitado_multi, extract_uuid,
                                portal_url)
from realtime.store import ESTADOS
from shared.fechas import parse_fecha
from shared.manifiesto import read_manifest, safe_filename
from shared.normalizacion import normalize

ROOT = Path(__file__).resolve().parent.parent
FINDINGS = ROOT / "findings"
DB = ROOT / "data" / "cases.duckdb"
DENUNCIAS = FINDINGS / "denuncias"

# RFC de persona moral (12) o física (13); cribado de forma, no de existencia.
_RFC_RE = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")

# pattern -> (tier, ámbito por omisión). El ámbito real se decide por renglón
# para f05 (orden_gobierno) y siempre 'estatal' para los f10_*.
TIER = {
    "inhabilitado": "T1", "efos": "T2", "convenio": "T2",
    "rotacion": "T3", "anillo": "T3", "fraccionamiento": "T3",
    "riesgo": "T3", "concentracion": "T3", "joven": "T3",
}

# pattern, ámbito -> (autoridad, fundamento). Estatal enruta al OIC del estado,
# nunca al SIDEC federal.
_RUTA = {
    ("inhabilitado", "federal"): ("SIDEC + OIC de la institución contratante",
                                  "LGRA arts. 59 y 67; LAASSP art. 50 fr. IV"),
    ("inhabilitado", "estatal"): ("OIC / Contraloría del sujeto obligado estatal",
                                  "LGRA arts. 59 y 67 (servidores estatales); "
                                  "ley estatal de adquisiciones"),
    ("efos", "federal"): ("SAT (procedimiento art. 69-B) y FGR",
                          "CFF art. 69-B; CPF art. 113-bis"),
    ("efos", "estatal"): ("SAT y FGR; con copia al OIC del estado",
                          "CFF art. 69-B; CPF art. 113-bis"),
    ("convenio", "federal"): ("Auditoría Superior de la Federación",
                              "LAASSP art. 52 / LOPSRM art. 59"),
    ("convenio", "estatal"): ("Entidad de Fiscalización Superior del estado",
                              "ley estatal de obra/adquisiciones"),
    ("rotacion", "federal"): ("COFECE / Comisión Nacional Antimonopolio",
                              "LFCE art. 53 (prácticas monopólicas absolutas)"),
    ("anillo", "federal"): ("OIC — solicitud de investigación",
                            "indicio estructural; requiere expediente"),
    ("anillo", "estatal"): ("OIC del estado — solicitud de investigación",
                            "indicio estructural; requiere expediente"),
    ("fraccionamiento", "federal"): ("OIC — solicitud de investigación",
                                     "LAASSP art. 42 (fraccionamiento)"),
    ("riesgo", "federal"): ("OIC — línea de investigación",
                            "señales agregadas; no es violación por sí sola"),
    ("concentracion", "estatal"): ("OIC / EFS del estado — línea de investigación",
                                   "concentración; requiere expediente"),
    ("joven", "estatal"): ("OIC del estado — línea de investigación",
                           "empresa joven con contrato grande; indicio"),
}


def routing(pattern: str, ambito: str) -> tuple[str, str]:
    return _RUTA.get((pattern, ambito), _RUTA.get((pattern, "federal"),
                     ("OIC competente", "requiere análisis")))


def rfc_valido(rfc) -> bool:
    return bool(_RFC_RE.match((str(rfc or "")).strip().upper()))


# Marcadores de "sin proveedor real" que la captura estatal deja en el campo
# del proveedor: no son concentración de un particular, son ruido de agregado.
_PLACEHOLDERS = {
    "CONTRATISTA", "PERSONA FISICA", "FISICA", "PERSONAS FISICAS", "MORAL",
    "PERSONA MORAL", "NO DATO", "NO APLICA", "NO SE GENERA INFORMACION",
    "ADMINISTRADOR UNICO", "ADMINSTRADOR UNICO", "PROVEEDOR", "SIN DATO",
}


def _es_placeholder(nombre) -> bool:
    n = normalize(nombre)
    if len(n) < 4 or n.startswith("LAS PERSONAS") or n.startswith("NO SE") \
            or str(nombre or "").strip().startswith("[["):
        return True
    return n in _PLACEHOLDERS or rfc_valido(nombre)  # RFC suelto como nombre


def case_id(*parts) -> str:
    """Id estable de 32 hex sobre una clave normalizada. Misma salida de los
    detectores -> mismo id; corridas idempotentes."""
    key = "|".join(normalize(str(p)) if p is not None else "" for p in parts)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:32]


def _f(v) -> float:
    """Importe numérico seguro: NaN/None/'' -> 0.0."""
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class Candidato:
    case_id: str
    scope: str            # contrato | proveedor | institucion | estatal
    pattern: str          # inhabilitado | efos | convenio | ...
    ambito: str           # federal | estatal
    estado_geo: str | None
    rfc: str | None
    sujeto: str | None        # nombre del proveedor o de la unidad compradora
    institucion: str | None   # institución (federal) o sujeto_obligado (estatal)
    procedure_uuid: str | None
    source_file: str
    monto: float
    n_contratos: int
    fecha: date | None
    evidencia: dict = field(default_factory=dict)
    # se completan en score():
    tier: str = ""
    score: int = 0
    gates: dict = field(default_factory=dict)
    cuarentena: list = field(default_factory=list)
    auto_ok: bool = False
    already_filed: bool = False
    recomendacion: str = "revisar"

    @property
    def evidence_uuids(self) -> list[str]:
        return [c["uuid"] for c in self.evidencia.get("contratos", [])
                if c.get("uuid")]

    def content_hash(self) -> str:
        payload = {
            "scope": self.scope, "pattern": self.pattern, "rfc": self.rfc,
            "institucion": normalize(self.institucion),
            "monto": round(self.monto, 2), "n": self.n_contratos,
            "uuids": sorted(self.evidence_uuids),
            "ventanas": sorted(self.evidencia.get("ventanas", [])),
        }
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _ambito_orden(orden) -> str:
    o = normalize(orden)
    if any(k in o for k in ("ESTATAL", "ENTIDAD FEDERATIVA", "MUNICIPAL",
                            "GOBIERNO DEL ESTADO")):
        return "estatal"
    return "federal"


def _read(findings_dir: Path, name: str) -> pd.DataFrame | None:
    p = Path(findings_dir) / name
    if not p.exists():
        return None
    df = pd.read_csv(p)
    return df if len(df) else None


def _acc_ventana(c: Candidato, desde, hasta, fc: date | None) -> bool:
    """Acumula la ventana de inhabilitación de un contrato en el caso.
    Un proveedor puede tener VARIAS inhabilitaciones; cada contrato se coteja
    contra la SUYA. Devuelve si este contrato cae dentro de su propia ventana.
    ventana_ok del caso = todos sus contratos dentro de su respectiva ventana."""
    d, h = parse_fecha(str(desde)), parse_fecha(str(hasta))
    en = bool(d and h and fc and d <= fc <= h)
    ev = c.evidencia
    ev["ventana_ok"] = ev.get("ventana_ok", True) and en
    ev.setdefault("ventanas", [])
    par = [str(desde), str(hasta)]
    if par not in ev["ventanas"]:
        ev["ventanas"].append(par)
    # rango global para el encabezado del borrador (mín desde, máx hasta)
    if d and (ev.get("desde") is None or d < parse_fecha(str(ev["desde"]))):
        ev["desde"] = str(desde)
    if h and (ev.get("hasta") is None or h > parse_fecha(str(ev["hasta"]))):
        ev["hasta"] = str(hasta)
    return en


def adapt_inhabilitado_federal(findings_dir: Path) -> list[Candidato]:
    df = _read(findings_dir, "f05_durante_inhabilitacion.csv")
    if df is None:
        return []
    out: dict[str, Candidato] = {}
    for _, r in df.iterrows():
        rfc = str(r.get("rfc") or "").strip().upper()
        ambito = _ambito_orden(r.get("orden_gobierno"))
        inst = r.get("institucion")
        cid = case_id("fed", "inhabilitado", rfc, inst) if ambito == "federal" \
            else case_id("est", "inhabilitado", r.get("estado_comprador"),
                         inst, rfc)
        c = out.get(cid)
        uuid = extract_uuid(r.get("direccion_anuncio"))
        if c is None:
            c = Candidato(
                case_id=cid, scope="contrato" if ambito == "federal" else "estatal",
                pattern="inhabilitado", ambito=ambito,
                estado_geo=(r.get("estado_comprador") if ambito == "estatal"
                            else None),
                rfc=rfc, sujeto=r.get("proveedor"), institucion=inst,
                procedure_uuid=uuid, source_file="f05_durante_inhabilitacion.csv",
                monto=0.0, n_contratos=0, fecha=None,
                evidencia={"desde": None, "hasta": None, "contratos": []})
            out[cid] = c
        imp = _f(r.get("importe"))
        c.monto += imp
        c.n_contratos += 1
        fc = parse_fecha(str(r.get("fecha_contrato")))
        if fc and (c.fecha is None or fc > c.fecha):
            c.fecha = fc
        if uuid and not c.procedure_uuid:
            c.procedure_uuid = uuid
        en = _acc_ventana(c, r.get("inhabilitado_desde"), r.get("hasta"), fc)
        c.evidencia["contratos"].append({
            "fecha": str(r.get("fecha_contrato")), "importe": imp,
            "institucion": inst, "uuid": uuid,
            "desde": str(r.get("inhabilitado_desde")), "hasta": str(r.get("hasta")),
            "en_ventana": en, "url": portal_url(r.get("direccion_anuncio")),
            "tipo_procedimiento": r.get("tipo_procedimiento")})
    return list(out.values())


def adapt_inhabilitado_estatal(findings_dir: Path) -> list[Candidato]:
    df = _read(findings_dir, "f10_inhabilitados_estatal.csv")
    if df is None:
        return []
    df = df[df["durante_inhabilitacion"] == True]  # noqa: E712
    out: dict[str, Candidato] = {}
    for _, r in df.iterrows():
        rfc = str(r.get("rfc_norm") or "").strip().upper()
        estado = r.get("estado_comprador")
        sujeto = r.get("sujeto_obligado")
        cid = case_id("est", "inhabilitado", estado, sujeto, rfc)
        c = out.get(cid)
        if c is None:
            c = Candidato(
                case_id=cid, scope="estatal", pattern="inhabilitado",
                ambito="estatal", estado_geo=estado, rfc=rfc,
                sujeto=r.get("proveedor"), institucion=sujeto,
                procedure_uuid=None,
                source_file="f10_inhabilitados_estatal.csv",
                monto=0.0, n_contratos=0, fecha=None,
                evidencia={"desde": None, "hasta": None,
                           "rfc_valido": bool(r.get("rfc_valido")),
                           "nombre_sfp": r.get("nombre_sfp"),
                           "institucion_sancionadora":
                               r.get("institucion_sancionadora"),
                           "contratos": []})
            out[cid] = c
        imp = _f(r.get("importe"))
        c.monto += imp
        c.n_contratos += 1
        fc = parse_fecha(str(r.get("fecha_efectiva")))
        if fc and (c.fecha is None or fc > c.fecha):
            c.fecha = fc
        en = _acc_ventana(c, r.get("inicio"), r.get("fin"), fc)
        c.evidencia["contratos"].append({
            "fecha": str(r.get("fecha_efectiva")), "importe": imp,
            "institucion": sujeto, "uuid": None,
            "desde": str(r.get("inicio")), "hasta": str(r.get("fin")),
            "en_ventana": en,
            "url": (r.get("url_fallo") or r.get("direccion_anuncio") or ""),
            "expediente": r.get("expediente")})
    return list(out.values())


def adapt_efos_federal(findings_dir: Path) -> list[Candidato]:
    df = _read(findings_dir, "f01_detalle_completo.csv")
    if df is None:
        return []
    df = df[(df["situacion"] == "Definitivo")
            & (df["firmado_despues_definitivo"] == True)]  # noqa: E712
    out: dict[str, Candidato] = {}
    for _, r in df.iterrows():
        rfc = str(r.get("rfc") or "").strip().upper()
        cid = case_id("fed", "efos", rfc)
        c = out.get(cid)
        uuid = extract_uuid(r.get("direccion_anuncio"))
        if c is None:
            c = Candidato(
                case_id=cid, scope="proveedor", pattern="efos", ambito="federal",
                estado_geo=None, rfc=rfc, sujeto=r.get("proveedor"),
                institucion=r.get("institucion"), procedure_uuid=uuid,
                source_file="f01_detalle_completo.csv", monto=0.0, n_contratos=0,
                fecha=None, evidencia={"definitivo_dof": r.get("definitivo_dof"),
                                       "contratos": []})
            out[cid] = c
        imp = _f(r.get("importe"))
        c.monto += imp
        c.n_contratos += 1
        fc = parse_fecha(str(r.get("fecha_contrato")))
        if fc and (c.fecha is None or fc > c.fecha):
            c.fecha = fc
        if uuid and not c.procedure_uuid:
            c.procedure_uuid = uuid
        c.evidencia["contratos"].append({
            "fecha": str(r.get("fecha_contrato")), "importe": imp,
            "institucion": r.get("institucion"), "uuid": uuid,
            "url": portal_url(r.get("direccion_anuncio")),
            "definitivo_dof": r.get("definitivo_dof")})
    return list(out.values())


def adapt_efos_estatal(findings_dir: Path) -> list[Candidato]:
    df = _read(findings_dir, "f10_efos_estatal.csv")
    if df is None:
        return []
    df = df[(df["firmado_despues_definitivo"] == True)  # noqa: E712
            & (df["importe_plausible"] == True)]        # noqa: E712
    out: dict[str, Candidato] = {}
    for _, r in df.iterrows():
        rfc = str(r.get("rfc") or "").strip().upper()
        estado = r.get("estado_comprador")
        sujeto = r.get("sujeto_obligado")
        cid = case_id("est", "efos", estado, sujeto, rfc)
        c = out.get(cid)
        if c is None:
            c = Candidato(
                case_id=cid, scope="estatal", pattern="efos", ambito="estatal",
                estado_geo=estado, rfc=rfc, sujeto=r.get("proveedor"),
                institucion=sujeto, procedure_uuid=None,
                source_file="f10_efos_estatal.csv", monto=0.0, n_contratos=0,
                fecha=None, evidencia={"definitivo_dof": r.get("definitivo_dof"),
                                       "contratos": []})
            out[cid] = c
        imp = _f(r.get("importe"))
        c.monto += imp
        c.n_contratos += 1
        fc = parse_fecha(str(r.get("fecha_contrato")))
        if fc and (c.fecha is None or fc > c.fecha):
            c.fecha = fc
        c.evidencia["contratos"].append({
            "fecha": str(r.get("fecha_contrato")), "importe": imp,
            "institucion": sujeto, "uuid": None,
            "url": (r.get("direccion_anuncio") or ""),
            "definitivo_dof": r.get("definitivo_dof")})
    return list(out.values())


def adapt_convenios(findings_dir: Path) -> list[Candidato]:
    df = _read(findings_dir, "f07_convenios_inflados.csv")
    if df is None:
        return []
    out = []
    for _, r in df.iterrows():
        rfc = str(r.get("rfc") or "").strip().upper()
        uuid = extract_uuid(r.get("direccion_anuncio"))
        cod = r.get("codigo_contrato") or r.get("num_contrato")
        cid = case_id("fed", "convenio", rfc, cod)
        imp = _f(r.get("monto_ultimo_convenio"))
        out.append(Candidato(
            case_id=cid, scope="contrato", pattern="convenio", ambito="federal",
            estado_geo=None, rfc=rfc, sujeto=r.get("proveedor"),
            institucion=r.get("institucion"), procedure_uuid=uuid,
            source_file="f07_convenios_inflados.csv", monto=imp, n_contratos=1,
            fecha=parse_fecha(str(r.get("fecha_contrato"))),
            evidencia={"monto_original": _f(r.get("monto_original")),
                       "monto_ultimo_convenio": imp,
                       "pct_incremento": _f(r.get("pct_incremento")),
                       "tope_legal_pct": _f(r.get("tope_legal_pct")),
                       "ley": r.get("ley"),
                       "contratos": [{"fecha": str(r.get("fecha_contrato")),
                                      "importe": imp, "uuid": uuid,
                                      "url": portal_url(r.get("direccion_anuncio"))}]}))
    return out


def adapt_rotacion(findings_dir: Path) -> list[Candidato]:
    df = _read(findings_dir, "f06_rotacion_licitaciones.csv")
    if df is None:
        return []
    out = []
    for _, r in df.iterrows():
        cid = case_id("fed", "rotacion", r.get("institucion"), r.get("nombre_uc"))
        out.append(Candidato(
            case_id=cid, scope="institucion", pattern="rotacion", ambito="federal",
            estado_geo=None, rfc=None, sujeto=r.get("nombre_uc"),
            institucion=r.get("institucion"), procedure_uuid=None,
            source_file="f06_rotacion_licitaciones.csv",
            monto=_f(r.get("monto_mxn_millones")) * 1e6,
            n_contratos=int(_f(r.get("contratos"))), fecha=None,
            evidencia={"evenness": _f(r.get("evenness")),
                       "n_proveedores": int(_f(r.get("n_proveedores"))),
                       "proveedores": r.get("proveedores"), "contratos": []}))
    return out


def adapt_riesgo(findings_dir: Path, min_senales: int = 4) -> list[Candidato]:
    df = _read(findings_dir, "f12_riesgo_proveedor.csv")
    if df is None:
        return []
    df = df[pd.to_numeric(df["n_senales"], errors="coerce") >= min_senales]
    out = []
    for _, r in df.iterrows():
        rfc = str(r.get("rfc") or "").strip().upper()
        out.append(Candidato(
            case_id=case_id("fed", "riesgo", rfc), scope="proveedor",
            pattern="riesgo", ambito="federal", estado_geo=None, rfc=rfc,
            sujeto=r.get("proveedor"), institucion=None, procedure_uuid=None,
            source_file="f12_riesgo_proveedor.csv",
            monto=_f(r.get("monto_mxn_millones")) * 1e6,
            n_contratos=int(_f(r.get("contratos"))), fecha=None,
            evidencia={"n_senales": int(_f(r.get("n_senales"))),
                       "senales": r.get("senales"),
                       "en_69b": bool(r.get("en_69b")),
                       "inhabilitado_sfp": bool(r.get("inhabilitado_sfp")),
                       "contratos": []}))
    return out


def adapt_concentracion_estatal(findings_dir: Path) -> list[Candidato]:
    df = _read(findings_dir, "f10_concentracion_estatal.csv")
    if df is None:
        return []
    out = []
    for _, r in df.iterrows():
        estado, sujeto = r.get("estado_comprador"), r.get("sujeto_obligado")
        if _es_placeholder(r.get("proveedor")):
            continue   # captura estatal sin proveedor real -> no es un caso
        out.append(Candidato(
            case_id=case_id("est", "concentracion", estado, sujeto,
                            r.get("proveedor")),
            scope="estatal", pattern="concentracion", ambito="estatal",
            estado_geo=estado, rfc=None, sujeto=r.get("proveedor"),
            institucion=sujeto, procedure_uuid=None,
            source_file="f10_concentracion_estatal.csv",
            monto=_f(r.get("monto_mxn_millones")) * 1e6,
            n_contratos=int(_f(r.get("contratos"))), fecha=None,
            evidencia={"pct_del_gasto_directo": _f(r.get("pct_del_gasto_directo")),
                       "contratos": []}))
    return out


ADAPTERS = [
    adapt_inhabilitado_federal, adapt_inhabilitado_estatal,
    adapt_efos_federal, adapt_efos_estatal, adapt_convenios,
    adapt_rotacion, adapt_riesgo, adapt_concentracion_estatal,
]


@dataclass
class FiledIndex:
    uuids: set
    pares: set        # (rfc, normalize(institucion))
    folios: set

    def is_filed(self, c: Candidato) -> bool:
        if c.procedure_uuid and c.procedure_uuid in self.uuids:
            return True
        if c.rfc and c.institucion and \
                (c.rfc, normalize(c.institucion)) in self.pares:
            return True
        ev = set(c.evidence_uuids)
        if ev and ev <= self.uuids:
            return True
        return False


def load_filed_index(denuncias_dir: Path = DENUNCIAS) -> FiledIndex:
    pub = Path(denuncias_dir) / "denuncias_publicas.json"
    fol = Path(denuncias_dir) / "folios_publicos.json"
    uuids: set = set()
    pares: set = set()
    if pub.exists():
        for e in json.loads(pub.read_text()):
            rfc = str(e.get("rfc") or "").strip().upper()
            for c in e.get("contratos", []):
                u = extract_uuid(c.get("url"))
                if u:
                    uuids.add(u)
                pares.add((rfc, normalize(c.get("institucion"))))
    folios = set(json.loads(fol.read_text())) if fol.exists() else set()
    return FiledIndex(uuids=uuids, pares=pares, folios=folios)


def _cobertura(findings_dir: Path) -> dict:
    """(estado, ejercicio) -> pct_rfc_valido (0..1) para descontar estados de
    baja calidad de captura."""
    df = _read(findings_dir, "f10_cobertura_estatal.csv")
    if df is None:
        return {}
    out = {}
    for _, r in df.iterrows():
        pct = _f(r.get("pct_rfc_valido"))
        out[normalize(r.get("estado_comprador"))] = max(
            out.get(normalize(r.get("estado_comprador")), 0.0), pct)
    return out


def score(c: Candidato, *, hoy: date, filed: FiledIndex,
          cobertura: dict, corrobora: int = 0) -> Candidato:
    """Compuerta + puntaje. Las compuertas DURAS fallidas mandan a cuarentena;
    already_filed manda a 'suppress'. El estado humano lo decide el skill."""
    c.tier = TIER.get(c.pattern, "T3")
    c.already_filed = filed.is_filed(c)

    g: dict[str, bool] = {}
    hard_fail: list[str] = []

    # compuerta universal: ya presentado
    if c.already_filed:
        c.recomendacion = "suppress"

    monto_ok = c.monto > 0
    fecha_ok = c.fecha is not None
    no_futura = c.fecha is not None and c.fecha <= hoy
    rfc_ok = (rfc_valido(c.rfc) if c.ambito == "federal"
              else bool(c.evidencia.get("rfc_valido", rfc_valido(c.rfc))))
    fuente = bool(c.procedure_uuid) or any(
        ct.get("url") for ct in c.evidencia.get("contratos", []))

    if c.pattern == "inhabilitado":
        # cada contrato ya se cotejó contra SU PROPIA ventana en el adaptador
        # (un proveedor puede tener varias inhabilitaciones); el caso es válido
        # si todos sus contratos caen dentro de la suya.
        ventana_ok = bool(c.evidencia.get("ventana_ok"))
        g = {"fecha_presente": fecha_ok, "no_futura": no_futura,
             "monto_positivo": monto_ok, "ventana_ok": ventana_ok,
             "rfc_valido": rfc_ok, "fuente_citable": fuente}
        for k in ("fecha_presente", "no_futura", "monto_positivo", "ventana_ok"):
            if not g[k]:
                hard_fail.append(k)
    elif c.pattern == "efos":
        dof = parse_fecha(str(c.evidencia.get("definitivo_dof")))
        post_ok = bool(dof and c.fecha and c.fecha > dof)
        g = {"fecha_presente": fecha_ok, "no_futura": no_futura,
             "monto_positivo": monto_ok, "post_definitivo": post_ok,
             "rfc_valido": rfc_ok, "fuente_citable": fuente}
        for k in ("fecha_presente", "no_futura", "monto_positivo",
                  "post_definitivo"):
            if not g[k]:
                hard_fail.append(k)
    elif c.pattern == "convenio":
        sobre = c.evidencia.get("pct_incremento", 0) > \
            c.evidencia.get("tope_legal_pct", 0)
        g = {"monto_positivo": monto_ok, "sobre_tope": sobre,
             "rfc_valido": rfc_ok, "fuente_citable": fuente}
        for k in ("monto_positivo", "sobre_tope"):
            if not g[k]:
                hard_fail.append(k)
    else:  # líneas de investigación (T3): se registran, no se cuarentenan
        g = {"monto_positivo": monto_ok, "rfc_valido": rfc_ok,
             "fuente_citable": fuente}

    c.gates = g
    c.cuarentena = hard_fail
    soft_ok = g.get("rfc_valido", True) and g.get("fuente_citable", True)
    c.auto_ok = (not hard_fail) and soft_ok

    if not c.already_filed:
        if hard_fail:
            c.recomendacion = "cuarentena"
        else:
            c.recomendacion = "revisar"

    # puntaje 0..100 para ordenar dentro de su categoría
    E = sum(1 for k in ("rfc_valido", "fuente_citable") if g.get(k)) / 2.0
    if c.pattern in ("inhabilitado", "efos"):
        E = (E + (1 if not hard_fail else 0)) / 2.0
    A = min(1.0, math.log10(max(c.monto, 1)) / 7.0)
    Af = 0.6 + 0.4 * A
    R = 1.0
    if c.fecha:
        dias = (hoy - c.fecha).days
        R = 1.0 if dias <= 365 else max(0.3, 1 - (dias - 365) / 1825)
    Rf = 0.7 + 0.3 * R
    Q = 1.0
    if c.ambito == "estatal":
        cob = cobertura.get(normalize(c.estado_geo), 0.6)
        Q = 0.7 + 0.3 * cob
    if c.tier == "T3":
        # las líneas de investigación rara vez traen RFC/URL; se ordenan por
        # magnitud (y señales), no por completitud documental.
        lead = 30 + 50 * A
        if c.pattern == "riesgo":
            lead += 5 * min(c.evidencia.get("n_senales", 4) - 3, 4)
        s = lead * Q * (1 + 0.05 * min(corrobora, 3))
    else:
        base = {"T1": 100, "T2": 80}[c.tier]
        s = base * E * Q * Af * Rf * (1 + 0.05 * min(corrobora, 3))
    if c.already_filed or hard_fail:
        s *= 0.0 if c.already_filed else 0.4   # cuarentena se ordena al fondo
    c.score = int(round(min(100, s)))
    return c


def iter_candidatos(findings_dir: Path = FINDINGS,
                    denuncias_dir: Path = DENUNCIAS,
                    hoy: date | None = None) -> list[Candidato]:
    hoy = hoy or date.today()
    filed = load_filed_index(denuncias_dir)
    cobertura = _cobertura(findings_dir)
    cands: list[Candidato] = []
    for adapt in ADAPTERS:
        cands.extend(adapt(findings_dir))
    # corroboración: RFCs que aparecen en >1 patrón refuerzan el caso
    from collections import Counter
    veces = Counter(c.rfc for c in cands if c.rfc)
    for c in cands:
        score(c, hoy=hoy, filed=filed, cobertura=cobertura,
              corrobora=(veces.get(c.rfc, 1) - 1) if c.rfc else 0)
    return cands


_SCHEMA = """
CREATE TABLE IF NOT EXISTS triage (
  case_id VARCHAR PRIMARY KEY, scope VARCHAR, pattern VARCHAR, ambito VARCHAR,
  estado_geo VARCHAR, rfc VARCHAR, sujeto VARCHAR, institucion VARCHAR,
  procedure_uuid VARCHAR, source_file VARCHAR, monto DOUBLE, n_contratos INTEGER,
  tier VARCHAR, score INTEGER, recomendacion VARCHAR, auto_ok BOOLEAN,
  already_filed BOOLEAN, cuarentena VARCHAR, evidence_json JSON, content_hash VARCHAR,
  estado VARCHAR DEFAULT 'nuevo', nota VARCHAR, folio VARCHAR,
  first_seen VARCHAR, last_seen VARCHAR, last_changed VARCHAR, decided_at VARCHAR
);
CREATE TABLE IF NOT EXISTS triage_runs (
  run_id BIGINT PRIMARY KEY, started_at VARCHAR, finished_at VARCHAR,
  scanned INTEGER, nuevos INTEGER, cambiados INTEGER, suprimidos INTEGER,
  notes VARCHAR
);
CREATE TABLE IF NOT EXISTS triage_emissions (
  run_id BIGINT, case_id VARCHAR, reason VARCHAR
);
"""

_ENGINE_COLS = ("scope", "pattern", "ambito", "estado_geo", "rfc", "sujeto",
                "institucion", "procedure_uuid", "source_file", "monto",
                "n_contratos", "tier", "score", "recomendacion", "auto_ok",
                "already_filed", "cuarentena", "evidence_json", "content_hash")


class TriageStore:
    def __init__(self, path: Path = DB):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(str(path))
        self._con.execute(_SCHEMA)

    def _engine_values(self, c: Candidato) -> list:
        return [c.scope, c.pattern, c.ambito, c.estado_geo, c.rfc, c.sujeto,
                c.institucion, c.procedure_uuid, c.source_file, c.monto,
                c.n_contratos, c.tier, c.score, c.recomendacion, c.auto_ok,
                c.already_filed, ",".join(c.cuarentena),
                json.dumps(c.evidencia, ensure_ascii=False, default=str),
                c.content_hash()]

    def upsert(self, c: Candidato, now: str) -> tuple[bool, bool]:
        """Inserta nuevos; refresca campos volátiles de los existentes sin pisar
        NUNCA estado/nota/folio/first_seen. Devuelve (es_nuevo, cambió)."""
        row = self._con.execute(
            "SELECT content_hash FROM triage WHERE case_id = ?",
            [c.case_id]).fetchone()
        ch = c.content_hash()
        if row is None:
            cols = ", ".join(("case_id", *_ENGINE_COLS, "first_seen",
                              "last_seen", "last_changed"))
            ph = ", ".join(["?"] * (len(_ENGINE_COLS) + 4))
            self._con.execute(
                f"INSERT INTO triage ({cols}) VALUES ({ph})",
                [c.case_id, *self._engine_values(c), now, now, now])
            return True, False
        changed = row[0] != ch
        sets = ", ".join(f"{k} = ?" for k in _ENGINE_COLS)
        vals = self._engine_values(c)
        self._con.execute(
            f"UPDATE triage SET {sets}, last_seen = ?, "
            f"last_changed = CASE WHEN ? THEN ? ELSE last_changed END "
            f"WHERE case_id = ?",
            [*vals, now, changed, now, c.case_id])
        return False, changed

    def set_estado(self, case_id: str, estado: str, nota: str | None = None,
                   folio: str | None = None):
        if estado not in ESTADOS:
            raise ValueError(f"estado inválido {estado!r}; usa {ESTADOS}")
        if not self._con.execute("SELECT 1 FROM triage WHERE case_id = ?",
                                 [case_id]).fetchone():
            raise ValueError(f"caso desconocido: {case_id}")
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        fields, vals = ["estado = ?", "decided_at = ?"], [estado, now]
        if nota is not None:
            fields.append("nota = ?")
            vals.append(nota)
        if folio is not None:
            fields.append("folio = ?")
            vals.append(folio)
        vals.append(case_id)
        self._con.execute(
            f"UPDATE triage SET {', '.join(fields)} WHERE case_id = ?", vals)

    def rows(self, estado: str | None = None, ambito: str | None = None,
             tier: str | None = None, recomendacion: str | None = None,
             incluir_filed: bool = False) -> pd.DataFrame:
        q, args = "SELECT * FROM triage WHERE 1=1", []
        if not incluir_filed:
            q += " AND already_filed = FALSE"
        for col, val in (("estado", estado), ("ambito", ambito),
                         ("tier", tier), ("recomendacion", recomendacion)):
            if val:
                q += f" AND {col} = ?"
                args.append(val)
        return self._con.execute(q + " ORDER BY score DESC", args).fetchdf()

    def get(self, case_id: str) -> dict | None:
        df = self._con.execute("SELECT * FROM triage WHERE case_id = ?",
                               [case_id]).fetchdf()
        return None if df.empty else df.iloc[0].to_dict()

    def start_run(self) -> int:
        from datetime import datetime, timezone
        run_id = int(time.time() * 1000)
        self._con.execute(
            "INSERT INTO triage_runs (run_id, started_at) VALUES (?, ?)",
            [run_id, datetime.now(timezone.utc).isoformat()])
        return run_id

    def emit(self, run_id: int, case_id: str, reason: str):
        self._con.execute(
            "INSERT INTO triage_emissions VALUES (?, ?, ?)",
            [run_id, case_id, reason])

    def finish_run(self, run_id: int, scanned: int, nuevos: int,
                   cambiados: int, suprimidos: int):
        from datetime import datetime, timezone
        self._con.execute(
            "UPDATE triage_runs SET finished_at = ?, scanned = ?, nuevos = ?, "
            "cambiados = ?, suprimidos = ? WHERE run_id = ?",
            [datetime.now(timezone.utc).isoformat(), scanned, nuevos,
             cambiados, suprimidos, run_id])


def scan(findings_dir: Path = FINDINGS, denuncias_dir: Path = DENUNCIAS,
         db: Path = DB, hoy: date | None = None) -> dict:
    """Corre todos los adaptadores, puntúa, coteja y persiste. Devuelve un
    reporte con los casos NUEVOS o CAMBIADOS que ameritan atención."""
    from datetime import datetime, timezone
    hoy = hoy or date.today()
    store = TriageStore(db)
    run_id = store.start_run()
    now = datetime.now(timezone.utc).isoformat()
    cands = iter_candidatos(findings_dir, denuncias_dir, hoy)
    nuevos, cambiados, suprimidos, emitidos = 0, 0, 0, []
    for c in cands:
        es_nuevo, cambio = store.upsert(c, now)
        if c.already_filed:
            suprimidos += 1
            continue
        # un caso resurge si es nuevo, o si cambió su evidencia y nadie lo ha
        # resuelto todavía (estado nuevo/verificando)
        estado_actual = (store.get(c.case_id) or {}).get("estado", "nuevo")
        surge = es_nuevo or (cambio and estado_actual in ("nuevo", "verificando"))
        if es_nuevo:
            nuevos += 1
        if cambio:
            cambiados += 1
        if surge:
            store.emit(run_id, c.case_id, "nuevo" if es_nuevo else "cambiado")
            emitidos.append(c)
    store.finish_run(run_id, len(cands), nuevos, cambiados, suprimidos)
    return {"run_id": run_id, "scanned": len(cands), "nuevos": nuevos,
            "cambiados": cambiados, "suprimidos": suprimidos,
            "emitidos": emitidos}


# estados en los que el documento sale presentable (no borrador)
_PRESENTABLE = ("verificado", "denunciado", "publicado")

# patrones con generador de denuncia per-caso (los demás van por expediente
# consolidado: convenios -> ASF, colusión -> COFECE, vía casework.denuncias)
GENERABLES = {"inhabilitado", "efos"}


def nombre_documento(pattern, ambito, rfc, estado_geo, case_id) -> str:
    """Nombre base del documento de un caso — único punto de verdad para el
    generador y el dashboard, así la liga 'Ver PDF' siempre apunta al archivo."""
    return safe_filename(
        f"{ambito}_{pattern}_{rfc or normalize(estado_geo)}_{case_id[:8]}")


def _grupo_de(row: dict, ev: dict) -> dict:
    """Arma el `grupo` que esperan los generadores de denuncias.py a partir de
    un renglón del libro de triaje."""
    return {"proveedor": row.get("sujeto"), "rfc": row.get("rfc"),
            "institucion": row.get("institucion"),
            "estado": row.get("estado_geo"),
            "inhabilitado_desde": ev.get("desde"), "hasta": ev.get("hasta"),
            "rfc_valido": ev.get("rfc_valido", True),
            "definitivo_dof": ev.get("definitivo_dof"),
            "contratos": ev.get("contratos", [])}


def generar(case_id: str, verificado: str | None = None,
            out_dir: Path = DENUNCIAS, render_pdf: bool = True,
            db: Path = DB) -> Path:
    """Caso del libro -> borrador (o denuncia presentable si está verificado) en
    .md y, salvo render_pdf=False, su PDF listo para presentar.
    NUNCA presenta: solo produce el documento."""
    row = TriageStore(db).get(case_id)
    if not row:
        raise ValueError(f"caso desconocido: {case_id}")
    ev = {}
    if row.get("evidence_json"):
        try:
            ev = json.loads(row["evidence_json"])
        except (TypeError, json.JSONDecodeError):
            ev = {}
    if verificado is None and row.get("estado") in _PRESENTABLE:
        verificado = (row.get("decided_at") or "")[:10] or date.today().isoformat()
    manifest = read_manifest()
    grupo = _grupo_de(row, ev)
    pattern, ambito = row.get("pattern"), row.get("ambito")
    if pattern == "inhabilitado" and ambito == "estatal":
        md = denuncia_inhabilitado_estatal(grupo, manifest, verificado)
    elif pattern == "inhabilitado":   # federal: reusa el generador vigente
        for c in grupo["contratos"]:
            c.setdefault("direccion_anuncio", c.get("url"))
            c.setdefault("fecha_contrato", c.get("fecha"))
        md = denuncia_inhabilitado_multi(grupo, manifest, verificado)
    elif pattern == "efos":
        md = denuncia_efos_post_definitivo(grupo, manifest, verificado)
    else:
        raise ValueError(
            f"generación per-caso no soportada para {pattern}/{ambito}; "
            "los convenios y la colusión usan el expediente consolidado "
            "(casework.denuncias.build_all)")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = nombre_documento(pattern, ambito, row.get("rfc"),
                            row.get("estado_geo"), case_id)
    p = out_dir / f"{base}.md"
    p.write_text(md, encoding="utf-8")
    if render_pdf:
        from casework.pdf import md_to_html, render_pdf as _render
        _render(md_to_html(md), p.with_suffix(".pdf"))
    return p


def to_dict(c: Candidato) -> dict:
    aut, fund = routing(c.pattern, c.ambito)
    return {"case_id": c.case_id, "tier": c.tier, "pattern": c.pattern,
            "ambito": c.ambito, "estado_geo": c.estado_geo, "rfc": c.rfc,
            "sujeto": c.sujeto, "institucion": c.institucion,
            "monto": round(c.monto, 2), "n_contratos": c.n_contratos,
            "fecha": str(c.fecha) if c.fecha else None, "score": c.score,
            "recomendacion": c.recomendacion, "auto_ok": c.auto_ok,
            "already_filed": c.already_filed, "cuarentena": c.cuarentena,
            "gates": c.gates, "autoridad": aut, "fundamento": fund,
            "source_file": c.source_file, "procedure_uuid": c.procedure_uuid,
            "evidencia": c.evidencia}


def _print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str]):
    cmd = argv[0] if argv else "list"
    if cmd == "scan":
        as_json = "--json" in argv
        rep = scan()
        casos = sorted((to_dict(c) for c in rep["emitidos"]),
                       key=lambda d: (-_tier_rank(d["tier"]), -d["score"]))
        if as_json:
            _print_json({k: rep[k] for k in
                         ("run_id", "scanned", "nuevos", "cambiados",
                          "suprimidos")} | {"casos": casos})
        else:
            print(f"escaneados {rep['scanned']} · nuevos {rep['nuevos']} · "
                  f"cambiados {rep['cambiados']} · ya presentados (omitidos) "
                  f"{rep['suprimidos']}")
            for d in casos:
                print(f"  [{d['tier']}] {d['recomendacion']:10} "
                      f"score {d['score']:3} · {d['ambito']:8} · "
                      f"{(d['estado_geo'] or 'FEDERAL'):24} · "
                      f"{str(d['sujeto'])[:40]:40} · ${d['monto']:,.0f} · "
                      f"{d['case_id'][:10]}")
    elif cmd == "list":
        as_json = "--json" in argv
        kw = _flagmap(argv[1:])
        df = TriageStore().rows(estado=kw.get("estado"), ambito=kw.get("ambito"),
                                tier=kw.get("tier"),
                                recomendacion=kw.get("recomendacion"),
                                incluir_filed="--filed" in argv)
        if as_json:
            _print_json(json.loads(df.to_json(orient="records")))
        else:
            cols = ["tier", "recomendacion", "score", "ambito", "estado_geo",
                    "sujeto", "monto", "estado", "case_id"]
            cols = [c for c in cols if c in df.columns]
            print(df[cols].to_string(index=False) if len(df) else "(sin casos)")
    elif cmd == "show":
        if len(argv) < 2:
            sys.exit("uso: show <case_id>")
        row = TriageStore().get(argv[1])
        if not row:
            sys.exit(f"caso desconocido: {argv[1]}")
        if row.get("evidence_json"):
            try:
                row["evidencia"] = json.loads(row["evidence_json"])
            except (TypeError, json.JSONDecodeError):
                pass
        aut, fund = routing(row.get("pattern"), row.get("ambito"))
        row["autoridad"], row["fundamento"] = aut, fund
        _print_json(row)
    elif cmd == "review":
        if len(argv) < 3:
            sys.exit("uso: review <case_id> <estado> [nota...] [--folio F]")
        cid, estado = argv[1], argv[2]
        rest = argv[3:]
        folio = None
        if "--folio" in rest:
            i = rest.index("--folio")
            folio = rest[i + 1] if i + 1 < len(rest) else None
            rest = rest[:i] + rest[i + 2:]
        nota = " ".join(rest) if rest else None
        TriageStore().set_estado(cid, estado, nota, folio)
        print(f"{cid} -> {estado}" + (f" (folio {folio})" if folio else ""))
    elif cmd == "generate":
        if len(argv) < 2:
            sys.exit("uso: generate <case_id> [--verificado FECHA] [--no-pdf]")
        kw = _flagmap(argv[2:])
        p = generar(argv[1], verificado=kw.get("verificado"),
                    render_pdf="--no-pdf" not in argv)
        print(f"escrito: {p}" + ("" if "--no-pdf" in argv else f" (+ {p.with_suffix('.pdf').name})"))
    else:
        sys.exit(f"comando desconocido: {cmd}")


def _tier_rank(t: str) -> int:
    return {"T1": 3, "T2": 2, "T3": 1}.get(t, 0)


def _flagmap(args: list[str]) -> dict:
    out = {}
    for i, a in enumerate(args):
        if a.startswith("--") and i + 1 < len(args) and \
                not args[i + 1].startswith("--"):
            out[a[2:]] = args[i + 1]
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
