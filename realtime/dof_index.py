"""Índice de circulares de inhabilitación del DOF — alerta temprana.

Una inhabilitación surte efectos al publicarse en el DOF; el directorio de
proveedores sancionados puede tardar días en reflejarla. Este módulo baja del
API abierto del DOF las circulares "...deberán abstenerse de aceptar
propuestas o celebrar contratos con...", extrae del título a la persona
inhabilitada (las circulares rara vez traen RFC) y deja un índice por nombre
normalizado para que el monitoreo marque a un ganador recién inhabilitado
que todavía no aparece en el directorio.

Refresco (lo corre el batch diario; conserva lo acumulado):
    python -m realtime.dof_index --dias 14
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from shared.fechas import parse_fecha
from shared.normalizacion import normalize

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "dof_circulares.json"
API_DIA = "https://sidofqa.segob.gob.mx/dof/sidof/notas/{fecha}"  # dd-mm-yyyy
API_NOTA = "https://sidofqa.segob.gob.mx/dof/sidof/notas/nota/{cod}"
URL_PUBLICA = "https://dof.gob.mx/nota_detalle.php?codigo={cod}&fecha={fecha}"

# variantes reales del DOF: "aceptar propuestas y/o celebrar", "participar
# en procedimientos de contratación o celebrar", "la persona moral
# denominada X", "la moral X", "la empresa X"
RE_TITULO = re.compile(
    r"abstenerse de .{0,90}?celebrar contratos? con\s+"
    r"(?P<prefijo>la empresa|las empresas|"
    r"la(?:s)? (?:persona(?:s)? )?moral(?:es)?|"
    r"la persona f[ií]sica(?: con actividad empresarial)?|"
    r"las personas f[ií]sicas(?: con actividad empresarial)?|"
    r"el C\.|la C\.|el ciudadano|la ciudadana)?\s*(?:denominad[ao]s?\s+)?"
    r"(?P<quien>.+?)\s*\.?\s*$",
    re.I)
_PLURALES = re.compile(r"^las\b", re.I)
RE_RFC = re.compile(r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b")
RE_PLAZO = re.compile(
    r"(?:INHABILITACI[ÓO]N TEMPORAL[^.;]{0,40}?(?:periodo|plazo) de|"
    r"por el plazo de)\s+([^.;]{3,90})", re.I)
# vigencia del índice: pasados ~6 meses el directorio ya la reflejó de sobra
DIAS_RELEVANTE = 180


def parse_titulo(titulo: str) -> list[str]:
    """'CIRCULAR ... con la empresa Garza Gas, S. A. de C.V.' -> nombres.

    Con prefijo plural ('las empresas X y Y') separa en varias; un nombre
    con ' y ' interno solo se parte cuando la circular anuncia varias."""
    m = RE_TITULO.search((titulo or "").strip())
    if not m:
        return []
    quien = m.group("quien").strip()
    if m.group("prefijo") and _PLURALES.match(m.group("prefijo")):
        partes = re.split(r"\s+y\s+|\s+e\s+|;\s*", quien)
        return [p.strip(" ,") for p in partes if p.strip(" ,")]
    return [quien]


def _abre_json(url: str, abre=None):
    abre = abre or urllib.request.urlopen
    with abre(url, timeout=30) as r:
        return json.load(r)


def fetch_dia(fecha_ddmmyyyy: str, abre=None) -> list[dict]:
    """Circulares de inhabilitación publicadas ese día (todas las ediciones)."""
    d = _abre_json(API_DIA.format(fecha=fecha_ddmmyyyy), abre)
    out = []
    for grupo in ("NotasMatutinas", "NotasVespertinas", "NotasExtraordinarias"):
        for n in d.get(grupo) or []:
            titulo = n.get("titulo") or ""
            if "abstenerse" not in titulo.lower():
                continue
            dia, mes, anio = fecha_ddmmyyyy.split("-")
            quienes = parse_titulo(titulo) or [None]
            for quien in quienes:
                out.append({
                    "cod_nota": n.get("codNota"),
                    "fecha_dof": f"{anio}-{mes}-{dia}",
                    "titulo": titulo.strip(),
                    "quien": quien,
                    "url": URL_PUBLICA.format(cod=n.get("codNota"),
                                              fecha=f"{dia}/{mes}/{anio}"),
                })
    return out


def enriquece(rec: dict, abre=None) -> dict:
    """Mejor esfuerzo: RFC y plazo desde el cuerpo de la nota (1 request)."""
    try:
        d = _abre_json(API_NOTA.format(cod=rec["cod_nota"]), abre)
        cuerpo = re.sub(r"\s+", " ", re.sub(
            r"<[^>]+>", " ", (d.get("Nota") or {}).get("cadenaContenido") or ""))
        rfc = RE_RFC.search(cuerpo)
        plazo = RE_PLAZO.search(cuerpo)
        rec["rfc"] = rfc.group(0) if rfc else None
        rec["plazo_txt"] = plazo.group(1).strip() if plazo else None
    except Exception as e:  # la circular vale aunque el cuerpo no baje
        print(f"WARN: cuerpo de nota {rec['cod_nota']} no bajó: {e}",
              file=sys.stderr)
        rec.setdefault("rfc", None)
        rec.setdefault("plazo_txt", None)
    return rec


def refresh(dias: int = 14, path: Path = RAW, abre=None,
            hoy: date | None = None) -> list[dict]:
    """Baja los últimos `dias` y fusiona con lo acumulado (dedupe por nota)."""
    previos = []
    if path.exists():
        try:
            previos = json.loads(path.read_text())["circulares"]
        except (json.JSONDecodeError, KeyError):
            print(f"WARN: {path} ilegible; se reconstruye", file=sys.stderr)
    vistos = {(r["cod_nota"], r.get("quien")) for r in previos}
    hoy = hoy or date.today()
    nuevos = []
    for i in range(dias):
        f = hoy - timedelta(days=i)
        try:
            dia = fetch_dia(f.strftime("%d-%m-%Y"), abre)
        except Exception as e:  # un día caído no tira el refresh
            print(f"WARN: DOF {f} no respondió: {e}", file=sys.stderr)
            continue
        for rec in dia:
            if (rec["cod_nota"], rec.get("quien")) not in vistos:
                nuevos.append(enriquece(rec, abre))
                vistos.add((rec["cod_nota"], rec.get("quien")))
        if abre is None:
            time.sleep(0.6)  # cortesía con el API público
    todas = sorted(previos + nuevos, key=lambda r: r["fecha_dof"], reverse=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(
        {"generado": datetime.now(timezone.utc).isoformat(),
         "circulares": todas}, ensure_ascii=False, indent=1))
    tmp.replace(path)
    print(f"DOF: {len(nuevos)} circulares nuevas, {len(todas)} acumuladas")
    return todas


class DofIndex:
    """Búsqueda por nombre normalizado (y RFC cuando la circular lo trae) de
    inhabilitaciones publicadas en el DOF recientemente."""

    def __init__(self, path: Path = RAW, hoy: date | None = None):
        self.by_name: dict[str, dict] = {}
        self.by_rfc: dict[str, dict] = {}
        hoy = hoy or date.today()
        if not path.exists():
            print(f"WARN: {path} no existe — índice DOF vacío; "
                  "corre python -m realtime.dof_index", file=sys.stderr)
            return
        try:
            circulares = json.loads(path.read_text())["circulares"]
        except (json.JSONDecodeError, KeyError):
            print(f"WARN: {path} ilegible — índice DOF vacío", file=sys.stderr)
            return
        for r in circulares:
            f = parse_fecha(r.get("fecha_dof"))
            if not f or (hoy - f).days > DIAS_RELEVANTE:
                continue
            if not r.get("quien") and not r.get("rfc"):
                continue  # circular sin nombre parseado ni RFC: inutilizable
            r = {**r, "fecha": f}
            key = normalize(r.get("quien") or "")
            if len(key) >= 8:
                self.by_name.setdefault(key, r)
            if r.get("rfc"):
                self.by_rfc.setdefault(r["rfc"].upper(), r)

    def match_name(self, name: str) -> dict | None:
        return self.by_name.get(normalize(name or ""))

    def match_rfc(self, rfc: str) -> dict | None:
        return self.by_rfc.get((rfc or "").strip().upper())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dias", type=int, default=14,
                    help="días hacia atrás a revisar (default: %(default)s)")
    args = ap.parse_args()
    refresh(args.dias)


if __name__ == "__main__":
    main()
