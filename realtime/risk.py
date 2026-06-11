"""Procedure-level and award-level realtime risk scoring.

Screens, not verdicts. Each flag is a transparent, named rule with a weight;
the score is the sum of fired weights. Designed to be read by a journalist: the
`reasons` list explains exactly why a procedure surfaced.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from datetime import datetime

from .comprasmx_client import Award, Procedure
from .efos_index import EfosIndex
from .sfp_index import SfpIndex


@dataclass
class Flag:
    code: str
    weight: int
    detail: str


@dataclass
class Assessment:
    uuid: str
    numero: str
    nombre: str
    siglas: str
    estatus: str
    score: int = 0
    flags: list[Flag] = field(default_factory=list)
    awards_flagged: list[dict] = field(default_factory=list)

    def add(self, code, weight, detail):
        self.flags.append(Flag(code, weight, detail))
        self.score += weight

    @property
    def reasons(self):
        return [f"{f.code} (+{f.weight}): {f.detail}" for f in self.flags]


def _is_direct(tp: str) -> bool:
    return "ADJUDICACI" in (tp or "").upper() and "DIRECTA" in (tp or "").upper()


def assess_procedure(p: Procedure, registro: dict | None) -> Assessment:
    a = Assessment(p.uuid, p.numero, p.nombre, p.siglas, p.estatus)
    reg = registro or {}

    if _is_direct(p.tipo_procedimiento):
        a.add("DIRECTA", 2, f"adjudicación directa ({p.tipo_procedimiento[:60]})")

    plazo = (reg.get("plazo_proc_contratacion") or "").lower()
    if "recort" in plazo:
        a.add("PLAZO_RECORTADO", 2, "plazo de contratación recortado")

    if (reg.get("contratacion_emergencia") or "").upper() == "SI":
        a.add("EMERGENCIA", 2, "marcada como contratación de emergencia")

    exc = reg.get("excepcion_fraccion") or reg.get("descripcion_corta")
    if exc and _is_direct(p.tipo_procedimiento):
        a.add("EXCEPCION", 1, f"excepción: {str(exc)[:60]}")

    if str(reg.get("anticipo")) == "1":
        pct = reg.get("porcentaje_anticipo")
        a.add("ANTICIPO", 1, f"anticipo{f' {pct}%' if pct else ''}")

    return a


def _award_date(aw: Award):
    for s in (aw.fecha_inicio, aw.fecha_publicacion):
        try:
            return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
    return None


def assess_awards(a: Assessment, awards: list[Award], efos: EfosIndex,
                  sfp: SfpIndex | None = None, big_mxn: float = 50_000_000) -> Assessment:
    for aw in awards:
        amt = aw.importe_max or aw.importe
        is_mxn = (aw.moneda or "MXN").upper() == "MXN"
        when = _award_date(aw)

        hit = efos.match(aw.licitante)
        if hit:
            w = 6 if hit["situacion"] == "Definitivo" else 2
            a.add("EFOS_69B", w,
                  f"{aw.licitante} en lista 69-B ({hit['situacion']}, RFC {hit['rfc']})")
            a.awards_flagged.append({
                "licitante": aw.licitante, "lista": "69-B", "match": hit["nombre"],
                "rfc": hit["rfc"], "situacion": hit["situacion"],
                "importe_max": amt, "moneda": aw.moneda,
                "institucion": aw.institucion, "cod_drc": aw.cod_drc,
                "match_method": "name", "needs_verification": True,
            })

        if sfp:
            s = sfp.match_name(aw.licitante)
            if s:
                durante = SfpIndex.debarred_on(s, when)
                w = 8 if durante else 3
                tag = "DURANTE inhabilitación" if durante else "proveedor sancionado SFP"
                a.add("SFP_SANCION", w, f"{aw.licitante}: {tag} (RFC {s['rfc']})")
                a.awards_flagged.append({
                    "licitante": aw.licitante, "lista": "SFP", "match": s["nombre"],
                    "rfc": s["rfc"], "inhabilitado_desde": str(s.get("inicio")),
                    "inhabilitado_hasta": str(s.get("fin")), "durante_inhabilitacion": durante,
                    "importe_max": amt, "moneda": aw.moneda,
                    "institucion": aw.institucion, "cod_drc": aw.cod_drc,
                    "match_method": "name", "needs_verification": True,
                })

        if amt and is_mxn and amt >= big_mxn:
            a.add("MONTO_ALTO", 1, f"contrato grande: {aw.licitante} ${amt/1e6:.1f}M MXN")
    return a
