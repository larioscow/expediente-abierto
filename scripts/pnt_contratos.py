#!/usr/bin/env python
"""Descarga masiva de la fr. XXVIII estatal (resultados de procedimientos de
adjudicación y licitación) de la PNT hacia data/raw/pnt/.

El export masivo de la PNT no trae el sujeto obligado en sus columnas, así
que se baja POR SUJETO OBLIGADO (una request por sujeto y formato, con el
block_size que usa el propio SPA) y se inyectan las columnas de atribución
al frente de cada fila: sin "quién contrató" no hay evidencia publicable.
Los ids de obligación y formato varían por órgano garante: se redescubren
por etiqueta en cada estado, junto con la faceta de sujetos obligados, en
una sola llamada. Reanudable: un (estado, ejercicio, formato) cuyo total
remoto no creció y sin sujetos fallidos se salta, así que puede correr bajo
launchd o repetirse sin costo. La ruta de red (Turnstile -> cf_clearance
reutilizada en curl_cffi) vive en scripts/pnt_muestra_rfc.py.

Uso:
    python -m scripts.pnt_contratos                          # 32 estados
    python -m scripts.pnt_contratos --estados Sonora,Sinaloa
    python -m scripts.pnt_contratos --ejercicios 2024
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.pnt_muestra_rfc import (FORMATO_ALTERNO_RE, FORMATO_RE,
                                     OBLIGACION_RE, SesionPNT)

# algunos sujetos meten blobs enormes en una celda (vimos >128 KB en
# Chihuahua); el límite default del módulo csv los rechaza
csv.field_size_limit(16_000_000)

ROOT = Path(__file__).resolve().parent.parent
DESTINO = ROOT / "data" / "raw" / "pnt"
MANIFIESTO = DESTINO / "manifiesto.json"

TAM_EXPORT = 300000  # block_size del propio SPA: un sujeto cabe en un bloque
COLS_ATRIBUCION = ["Entidad federativa", "Id entidad federativa",
                   "Id sujeto obligado", "Sujeto obligado"]


def carga_manifiesto(path: Path = MANIFIESTO) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"AVISO: manifiesto ilegible ({e}); se reconstruye", file=sys.stderr)
        return {}


def guarda_manifiesto(man: dict, path: Path = MANIFIESTO) -> None:
    """Escritura atómica: una corrida interrumpida no corrompe el estado."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(man, ensure_ascii=False, indent=1))
    tmp.replace(path)


def clave_entrega(id_ent: int, ejercicio: str, formato: str) -> str:
    return f"{id_ent:02d}_{ejercicio}_{formato}"


def nombre_archivo(id_ent: int, ejercicio: str, formato: str) -> str:
    return f"pnt_{id_ent:02d}_{ejercicio}_{formato}.csv"


def pendiente(man: dict, clave: str, total_remoto: int) -> bool:
    """Se repite si nunca se completó, si el remoto creció o si quedaron
    sujetos obligados fallidos en la corrida anterior."""
    previo = man.get(clave)
    if previo is None:
        return True
    return total_remoto > previo.get("filas", 0) or bool(
        previo.get("sujetos_fallidos"))


def parsea_facetas(d: dict) -> tuple[list[tuple[str, str, int]],
                                     list[tuple[str, str, int]]]:
    """Del agrupado con id_obligacion -> (formatos elegidos, sujetos).
    Formatos: prioriza los vigentes 'Resultados de procedimientos...' y cae
    a adjudicación/licitación, máximo 3, como el sondeo. Sujetos: todos los
    de la faceta, mayores primero."""
    hist = d.get("facets_hist") or {}

    def lista(faceta: dict) -> list[tuple[str, str, int]]:
        return [(k, v.get("label") or "", v.get("count") or 0)
                for k, v in (faceta or {}).items()]

    todos = lista(hist.get("id_formato"))
    formatos = [f for f in todos if FORMATO_RE.search(f[1])]
    if not formatos:
        formatos = [f for f in todos if FORMATO_ALTERNO_RE.search(f[1])]
    formatos.sort(key=lambda f: -f[2])
    sujetos = lista(hist.get("id_sujetoobligado"))
    sujetos.sort(key=lambda s: -s[2])
    return formatos[:3], sujetos


def facetas_obligacion(ses: SesionPNT, id_ent: int, ejercicio: str):
    """Descubre obligación fr. XXVIII + formatos + sujetos obligados del
    estado en dos llamadas al agrupado."""
    d = ses.get_json(
        "/api/search/unificado/agrupado?q=*:*"
        f"&id_entidadfederativa={id_ent}&ejercicio={ejercicio}"
        "&page=0&page_size=10")
    facetas = (d.get("facets_qa") or {}).get("id_obligacion") or {}
    candidatos = [(k, v.get("label") or "", v.get("count") or 0)
                  for k, v in facetas.items()
                  if OBLIGACION_RE.search(v.get("label") or "")]
    if not candidatos:
        return None, [], []
    candidatos.sort(key=lambda c: -c[2])
    id_ob = candidatos[0][0]
    d = ses.get_json(
        "/api/search/unificado/agrupado?q=*:*"
        f"&id_entidadfederativa={id_ent}&ejercicio={ejercicio}"
        f"&id_obligacion={id_ob}&page=0&page_size=10")
    formatos, sujetos = parsea_facetas(d)
    return id_ob, formatos, sujetos


def descarga_formato(ses: SesionPNT, estado: str, id_ent: int, ejercicio: str,
                     formato: str, sujetos: list[tuple[str, str, int]],
                     destino: Path) -> tuple[int, dict[str, int], list[str]]:
    """Baja el formato sujeto por sujeto a `destino` (tmp + rename),
    inyectando las columnas de atribución. Devuelve (filas, filas_por_sujeto,
    sujetos_fallidos)."""
    tmp = destino.with_suffix(".csv.tmp")
    filas_total = 0
    por_sujeto: dict[str, int] = {}
    fallidos: list[str] = []
    with open(tmp, "w", encoding="utf-8", newline="") as out:
        w = csv.writer(out)
        encabezado_escrito = False
        for so_id, so_nombre, _ in sujetos:
            try:
                status, ctype, body = ses.get(
                    f"/api/export/csv?q=*:*&fuente=solicitudes"
                    f"&formato={formato}"
                    f"&id_entidadfederativa={id_ent}&ejercicio={ejercicio}"
                    f"&id_sujetoobligado={so_id}&block=1"
                    f"&block_size={TAM_EXPORT}")
            except Exception as exc:  # un sujeto colgado no tira al estado
                print(f"    sujeto {so_id} ({so_nombre[:40]}): {exc!r}",
                      file=sys.stderr)
                fallidos.append(so_id)
                continue
            if status != 200 or "csv" not in ctype:
                print(f"    sujeto {so_id} ({so_nombre[:40]}): sin CSV "
                      f"({status} {ctype})", file=sys.stderr)
                fallidos.append(so_id)
                continue
            leidas = list(csv.reader(io.StringIO(body.lstrip("﻿"))))
            if len(leidas) < 2:
                continue  # solo encabezado: este sujeto no usa este formato
            if not encabezado_escrito:
                w.writerow(COLS_ATRIBUCION + leidas[0])
                encabezado_escrito = True
            extras = [estado, str(id_ent), so_id, so_nombre]
            w.writerows(extras + fila for fila in leidas[1:])
            n = len(leidas) - 1
            if n >= TAM_EXPORT:
                print(f"    AVISO: sujeto {so_id} llenó el bloque ({n}); "
                      "posible truncamiento", file=sys.stderr)
            por_sujeto[so_id] = n
            filas_total += n
    if not filas_total:
        tmp.unlink(missing_ok=True)
        return 0, {}, fallidos
    tmp.replace(destino)
    return filas_total, por_sujeto, fallidos


def procesa_estado(ses: SesionPNT, estado: str, id_ent: int,
                   ejercicios: list[str], man: dict) -> None:
    for ejercicio in ejercicios:
        id_ob, formatos, sujetos = facetas_obligacion(ses, id_ent, ejercicio)
        if not id_ob or not formatos:
            print(f"  {estado} {ejercicio}: sin fr. XXVIII en facetas",
                  file=sys.stderr)
            continue
        total_faceta = sum(n for _, _, n in sujetos)
        for formato, etiqueta, n_formato in formatos:
            clave = clave_entrega(id_ent, ejercicio, formato)
            if not pendiente(man, clave, n_formato):
                print(f"  {estado} {ejercicio} formato {formato}: al día "
                      f"({man[clave]['filas']} filas)", file=sys.stderr)
                continue
            print(f"  {estado} {ejercicio} formato {formato} "
                  f"\"{etiqueta[:45]}\": ~{n_formato} filas, "
                  f"{len(sujetos)} sujetos obligados", file=sys.stderr)
            destino = DESTINO / nombre_archivo(id_ent, ejercicio, formato)
            filas, por_sujeto, fallidos = descarga_formato(
                ses, estado, id_ent, ejercicio, formato, sujetos, destino)
            man[clave] = {
                "estado": estado, "id_entidad": id_ent,
                "ejercicio": ejercicio, "formato": formato,
                "etiqueta": etiqueta, "id_obligacion": id_ob,
                "archivo": destino.name if filas else None,
                "filas": filas, "total_remoto": n_formato,
                "total_obligacion": total_faceta,
                "sujetos": len(por_sujeto), "sujetos_fallidos": fallidos,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            guarda_manifiesto(man)


def ejercicios_default(hoy: date | None = None) -> str:
    """Año en curso y el anterior: los dos ejercicios que aún reciben
    reportes de contratos. Dinámico para que el batch diario siga bajando
    el año vigente sin tocar el código cada enero. Los años cerrados ya
    están en disco (y pendiente() los salta); para un backfill histórico se
    pasa --ejercicios explícito."""
    y = (hoy or date.today()).year
    return f"{y - 1},{y}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--estados", default="",
                    help="nombres separados por coma (default: los 32)")
    ap.add_argument("--ejercicios", default=None,
                    help="ejercicios separados por coma "
                         "(default: año en curso y el anterior)")
    args = ap.parse_args()
    ejercicios = [e.strip() for e in
                  (args.ejercicios or ejercicios_default()).split(",")
                  if e.strip()]

    print("resolviendo Turnstile (scrapling)...", file=sys.stderr)
    ses = SesionPNT()
    catalogo = ses.get_json("/api/catalogo/entidades")["entidades"]
    if args.estados:
        pedidos = [n.strip().casefold() for n in args.estados.split(",")
                   if n.strip()]
        catalogo = [e for e in catalogo
                    if any(p in e["nombre"].casefold() for p in pedidos)]
        if len(catalogo) < len(pedidos):
            sys.exit(f"estados sin resolver en el catálogo: {args.estados!r}")

    DESTINO.mkdir(parents=True, exist_ok=True)
    man = carga_manifiesto()
    inicio = time.time()
    for e in catalogo:
        print(f"== {e['nombre']} (id {e['id']}) ==", file=sys.stderr)
        try:
            procesa_estado(ses, e["nombre"], e["id"], ejercicios, man)
        except Exception as exc:  # un estado caído no tira la corrida
            print(f"  ERROR en {e['nombre']}: {exc!r}", file=sys.stderr)
    filas = sum(v["filas"] for v in man.values())
    print(f"manifiesto: {len(man)} entregas, {filas} filas totales "
          f"({time.time() - inicio:.0f}s)")


if __name__ == "__main__":
    main()
