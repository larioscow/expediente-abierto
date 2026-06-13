#!/usr/bin/env python
"""Sondeo de calidad del campo RFC en la fr. XXVIII del art. 70 (resultados de
procedimientos de adjudicacion y licitacion) de la PNT, para sujetos obligados
estatales. Decide si un pipeline batch sobre la PNT puede cruzar adjudicados
por RFC (EFOS/sancionados) o si hay que planear fallback por razon social.

Ruta verificada (2026-06-12), todo same-origin en
https://consultapublicamx.plataformadetransparencia.org.mx:

  1. scrapling StealthyFetcher(solve_cloudflare=True) pasa el Turnstile de
     Cloudflare; la cookie cf_clearance + el mismo User-Agent se reutilizan
     despues en curl_cffi (HTTP plano, sin navegador -- verificado que el
     borde de Cloudflare lo acepta).
  2. GET /api/catalogo/entidades -> ids de estados (orden INEGI: Sinaloa 25,
     Sonora 26, Zacatecas 32).
  3. GET /api/search/unificado/agrupado?q=*:*&id_entidadfederativa=N&ejercicio=A
     -> facets_qa.id_obligacion. La fr. XXVIII estatal aparece etiquetada
     "CONTRATOS DE OBRAS, BIENES Y SERVICIOS"; el id se redescubre por
     etiqueta en cada estado (no se asume fijo).
  4. El mismo endpoint + id_obligacion=<id> -> facets_hist.id_formato. Los
     formatos vigentes se llaman "Resultados de procedimientos de
     adjudicacion directa, licitacion publica e invitacion restringida"
     (p.ej. 59747/59748 en Sonora; los ids varian por organo garante).
  5. GET /api/export/csv?q=*:*&fuente=solicitudes&formato=<id_formato>
         &id_entidadfederativa=N&ejercicio=A&block=B&block_size=K
     -> CSV con las ~80 columnas del formato, incluida "Registro Federal de
     Contribuyentes (RFC) de la persona fisica o moral contratista o
     proveedora ganadora...". block_size es libre (el SPA usa 300000);
     /api/export/csv/info da el total y permite muestrear bloques dispersos.

  /api/search/unificado/detalle tambien trae los campos (clave `datos`) pero
  pagina de 10 en 10; el CSV es la via de volumen.

Uso:
    python scripts/pnt_muestra_rfc.py                 # Sonora, Sinaloa, Zacatecas
    python scripts/pnt_muestra_rfc.py --estados Sonora --objetivo 100
    python scripts/pnt_muestra_rfc.py --json /tmp/muestra_rfc.json

No escribe en findings/ ni data/: el resumen sale por stdout; --json vuelca
la muestra cruda en la ruta indicada.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import random
import re
import sys
import time
from datetime import date

BASE = "https://consultapublicamx.plataformadetransparencia.org.mx"
DOMINIO = BASE.split("//")[1]
ESTADOS_DEFAULT = "Sonora,Sinaloa,Zacatecas"
# año en curso primero, luego el anterior (donde hay datos más recientes);
# dinámico para que el sondeo no caduque al cambiar de año
EJERCICIOS = (str(date.today().year), str(date.today().year - 1))

RFC_RE = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")
# RFC genericos del SAT: pasan la regex pero no sirven para cruzar identidad
GENERICOS = {"XAXX010101000", "XEXX010101000"}
OBLIGACION_RE = re.compile(r"CONTRATOS DE OBRAS|RESULTADOS DE ADJUDICACI", re.I)
FORMATO_RE = re.compile(r"resultados de procedimientos", re.I)
FORMATO_ALTERNO_RE = re.compile(r"adjudicaci|licitaci", re.I)

PAUSA = (2.0, 4.0)       # segundos de cortesia entre requests
PRESUPUESTO_SOLVE = 900  # segundos maximos peleando con Turnstile
MAX_FALLOS_RED = 5       # reintentos ante caida de red transitoria (DNS/timeout)


class SesionPNT:
    """Una pasada de Turnstile con scrapling; despues HTTP plano con
    curl_cffi reutilizando cf_clearance + User-Agent. Si la clearance
    caduca (403), se vuelve a resolver dentro del presupuesto."""

    def __init__(self) -> None:
        self._gastado = 0.0
        self._sesion = None
        self._resolver()

    def _resolver(self) -> None:
        from curl_cffi import requests as creq  # dependencia de scrapling
        from scrapling.fetchers import StealthyFetcher

        while True:
            t0 = time.time()
            err = ""
            try:
                page = StealthyFetcher.fetch(
                    BASE + "/", solve_cloudflare=True, network_idle=True,
                    timeout=120000,
                )
                cookies = {c["name"]: c["value"] for c in page.cookies}
                if page.status == 200 and "cf_clearance" in cookies:
                    ua = (page.request_headers or {}).get("user-agent", "")
                    s = creq.Session(impersonate="chrome",
                                     headers={"User-Agent": ua})
                    for k, v in cookies.items():
                        s.cookies.set(k, v, domain=DOMINIO)
                    self._sesion = s
                    return
                err = f"status={page.status} cookies={sorted(cookies)}"
            except Exception as e:  # camoufox/red: reintentable
                err = repr(e)[:200]
            self._gastado += time.time() - t0
            if self._gastado > PRESUPUESTO_SOLVE:
                raise RuntimeError(f"Turnstile no cedio en "
                                   f"{PRESUPUESTO_SOLVE}s: {err}")
            print(f"  turnstile sin resolver ({err}); reintento en 30 s",
                  file=sys.stderr)
            time.sleep(30)
            self._gastado += 30

    def get(self, path: str) -> tuple[int, str, str]:
        """GET con pausa de cortesía -> (status, content_type, body).

        Reintenta ante caídas de red transitorias (DNS, timeout, conexión —
        p. ej. un corte de internet a mitad de la descarga) con espera
        creciente, en vez de abandonar el sujeto a la primera. Un 403
        re-resuelve Turnstile. Tras MAX_FALLOS_RED caídas seguidas levanta la
        excepción para que el llamador la registre y siga (la re-corrida la
        retoma gracias al manifiesto)."""
        url = BASE + path
        fallos_red = 0
        re_resuelto = False
        while True:
            time.sleep(random.uniform(*PAUSA))
            try:
                r = self._sesion.get(url, timeout=120)
            except Exception as exc:
                fallos_red += 1
                if fallos_red > MAX_FALLOS_RED:
                    raise
                espera = 10 * fallos_red
                print(f"  red caída ({exc!r}); reintento "
                      f"{fallos_red}/{MAX_FALLOS_RED} en {espera}s",
                      file=sys.stderr)
                time.sleep(espera)
                continue
            fallos_red = 0
            if r.status_code == 403 and not re_resuelto:
                print("  403: clearance caducada, re-resolviendo Turnstile",
                      file=sys.stderr)
                self._resolver()
                re_resuelto = True
                continue
            return r.status_code, r.headers.get("content-type", ""), r.text

    def get_json(self, path: str) -> dict:
        status, ctype, body = self.get(path)
        if status != 200 or "json" not in ctype:
            raise RuntimeError(f"GET {path} -> {status} {ctype}: {body[:150]}")
        return json.loads(body)


def ids_entidades(ses: SesionPNT, nombres: list[str]) -> dict[str, int]:
    """Resuelve nombre de estado -> id de la PNT via el catalogo oficial."""
    cat = ses.get_json("/api/catalogo/entidades")["entidades"]
    out = {}
    for nombre in nombres:
        n = nombre.strip().casefold()
        hit = next((e for e in cat if n in e["nombre"].casefold()), None)
        if not hit:
            raise SystemExit(f"estado desconocido en el catalogo: {nombre!r}")
        out[nombre.strip()] = hit["id"]
    return out


def descubre_obligacion(ses: SesionPNT, id_ent: int,
                        ejercicio: str) -> tuple[str, str] | None:
    """Encuentra el id de la obligacion fr. XXVIII en las facetas del estado.
    Si varias etiquetas matchean, gana la de mas registros."""
    d = ses.get_json(
        "/api/search/unificado/agrupado?q=*:*"
        f"&id_entidadfederativa={id_ent}&ejercicio={ejercicio}"
        "&page=0&page_size=10"
    )
    facetas = (d.get("facets_qa") or {}).get("id_obligacion") or {}
    candidatos = [(k, v.get("label") or "", v.get("count") or 0)
                  for k, v in facetas.items()
                  if OBLIGACION_RE.search(v.get("label") or "")]
    if not candidatos:
        return None
    candidatos.sort(key=lambda c: -c[2])
    return candidatos[0][0], candidatos[0][1]


def descubre_formatos(ses: SesionPNT, id_ent: int, ejercicio: str,
                      id_ob: str) -> list[tuple[str, str, int]]:
    """Formatos (id, etiqueta, n) de la obligacion; prioriza los vigentes
    'Resultados de procedimientos...' y cae a adjudicacion/licitacion."""
    d = ses.get_json(
        "/api/search/unificado/agrupado?q=*:*"
        f"&id_entidadfederativa={id_ent}&ejercicio={ejercicio}"
        f"&id_obligacion={id_ob}&page=0&page_size=10"
    )
    facetas = (d.get("facets_hist") or {}).get("id_formato") or {}
    todos = [(k, v.get("label") or "", v.get("count") or 0)
             for k, v in facetas.items()]
    elegidos = [f for f in todos if FORMATO_RE.search(f[1])]
    if not elegidos:
        elegidos = [f for f in todos if FORMATO_ALTERNO_RE.search(f[1])]
    elegidos.sort(key=lambda f: -f[2])
    return elegidos[:3]


def muestra_formato(ses: SesionPNT, id_ent: int, ejercicio: str, fmt: str,
                    cuota: int) -> tuple[list[str], list[list[str]], int]:
    """Baja hasta `cuota` filas del formato via export CSV: bloque inicial y,
    si el dataset da, un bloque a la mitad para no muestrear un solo sujeto
    obligado."""
    filtros = (f"q=*:*&fuente=solicitudes&formato={fmt}"
               f"&id_entidadfederativa={id_ent}&ejercicio={ejercicio}")
    info = ses.get_json(f"/api/export/csv/info?{filtros}")
    total = int(info.get("total") or 0)
    if not total:
        return [], [], 0
    tam = max(1, min(100, cuota))
    bloques = [1]
    n_bloques = math.ceil(total / tam)
    if cuota > tam and n_bloques >= 3:
        bloques.append(n_bloques // 2 + 1)
    headers: list[str] = []
    filas: list[list[str]] = []
    for b in bloques:
        if len(filas) >= cuota:
            break
        status, ctype, body = ses.get(
            f"/api/export/csv?{filtros}&block={b}&block_size={tam}")
        if status != 200 or "csv" not in ctype:
            print(f"  aviso: formato {fmt} bloque {b} sin CSV "
                  f"({status} {ctype})", file=sys.stderr)
            continue
        leidas = list(csv.reader(io.StringIO(body.lstrip("﻿"))))
        if not leidas:
            continue
        if not headers:
            headers = leidas[0]
        filas.extend(leidas[1:])
    return headers, filas[:cuota], total


def _col(headers: list[str], *fragmentos: str) -> int | None:
    """Indice de la primera columna que contiene todos los fragmentos."""
    for i, h in enumerate(headers):
        hl = h.casefold()
        if all(f.casefold() in hl for f in fragmentos):
            return i
    return None


def _celda(fila: list[str], i: int | None) -> str:
    return fila[i].strip() if i is not None and i < len(fila) else ""


def clasifica_rfc(crudo: str) -> tuple[str, str]:
    """-> (rfc_limpio, 'valido' | 'vacio' | 'basura')."""
    v = crudo.strip().upper().replace(" ", "")
    if not v:
        return v, "vacio"
    return v, ("valido" if RFC_RE.match(v) else "basura")


def mide_estado(headers: list[str], filas: list[list[str]],
                etiqueta_fmt: dict[int, str]) -> dict:
    """Clasifica el RFC de cada fila y arma estadistica + muestra cruda."""
    i_rfc = _col(headers, "registro federal") or _col(headers, "rfc")
    i_razon = _col(headers, "denominación o razón social")
    i_nom = _col(headers, "nombre(s) de la persona física ganadora")
    i_ap1 = _col(headers, "primer apellido")
    i_ap2 = _col(headers, "segundo apellido")
    i_monto = (_col(headers, "monto total del contrato")
               or _col(headers, "monto del contrato"))
    conteo = {"valido": 0, "vacio": 0, "basura": 0}
    genericos = 0
    muestra = []
    for n_fila, fila in enumerate(filas):
        rfc, clase = clasifica_rfc(_celda(fila, i_rfc))
        conteo[clase] += 1
        if rfc in GENERICOS:
            genericos += 1
        proveedor = _celda(fila, i_razon) or " ".join(
            p for p in (_celda(fila, i_nom), _celda(fila, i_ap1),
                        _celda(fila, i_ap2)) if p)
        muestra.append({
            "proveedor": proveedor,
            "rfc": rfc,
            "clase": clase,
            "monto": _celda(fila, i_monto),
            "formato": etiqueta_fmt.get(n_fila, ""),
        })
    return {"n": len(filas), "conteo": conteo, "genericos": genericos,
            "muestra": muestra}


def sondea_estado(ses: SesionPNT, estado: str, id_ent: int, objetivo: int,
                  ejercicios: tuple[str, ...]) -> dict:
    for ejercicio in ejercicios:
        ob = descubre_obligacion(ses, id_ent, ejercicio)
        if not ob:
            print(f"  {estado} {ejercicio}: sin obligacion fr. XXVIII en "
                  "facetas; pruebo siguiente ejercicio", file=sys.stderr)
            continue
        id_ob, etiqueta_ob = ob
        formatos = descubre_formatos(ses, id_ent, ejercicio, id_ob)
        if not formatos:
            print(f"  {estado} {ejercicio}: obligacion {id_ob} sin formatos",
                  file=sys.stderr)
            continue
        print(f"  {estado} {ejercicio}: obligacion {id_ob} "
              f"({etiqueta_ob}); formatos "
              + ", ".join(f"{f[0]} (n={f[2]})" for f in formatos),
              file=sys.stderr)
        cuota = max(1, objetivo // len(formatos))
        headers: list[str] = []
        filas: list[list[str]] = []
        etiqueta_fmt: dict[int, str] = {}
        usados = []
        for fmt, etiqueta, _ in formatos:
            h, fs, total = muestra_formato(ses, id_ent, ejercicio, fmt, cuota)
            if not fs:
                continue
            if not headers:
                headers = h
            for k in range(len(filas), len(filas) + len(fs)):
                etiqueta_fmt[k] = fmt
            filas.extend(fs)
            usados.append((fmt, etiqueta, total, len(fs)))
        if not filas:
            continue
        medida = mide_estado(headers, filas, etiqueta_fmt)
        medida.update(estado=estado, id_entidad=id_ent, ejercicio=ejercicio,
                      id_obligacion=id_ob, etiqueta_obligacion=etiqueta_ob,
                      formatos=usados, metodo="/api/export/csv")
        return medida
    return {"estado": estado, "id_entidad": id_ent, "n": 0,
            "error": "sin datos fr. XXVIII en " + "/".join(ejercicios)}


def imprime_informe(resultados: list[dict]) -> None:
    print("\n== Calidad del RFC, fr. XXVIII estatal (PNT) ==")
    print(f"{'estado':<12} {'n':>5} {'%valido':>8} {'%vacio':>7} "
          f"{'%basura':>8} {'ejercicio':>9}  metodo")
    for r in resultados:
        if not r.get("n"):
            print(f"{r['estado']:<12} {'0':>5}  FALLO: {r.get('error')}")
            continue
        c, n = r["conteo"], r["n"]
        print(f"{r['estado']:<12} {n:>5} {c['valido']/n:>8.0%} "
              f"{c['vacio']/n:>7.0%} {c['basura']/n:>8.0%} "
              f"{r['ejercicio']:>9}  {r['metodo']}")
    for r in resultados:
        if not r.get("n"):
            continue
        print(f"\n-- {r['estado']} (entidad {r['id_entidad']}, obligacion "
              f"{r['id_obligacion']} \"{r['etiqueta_obligacion']}\")")
        for fmt, etiqueta, total, usadas in r["formatos"]:
            print(f"   formato {fmt} \"{etiqueta}\": {total} registros "
                  f"totales, {usadas} muestreados")
        if r["genericos"]:
            print(f"   RFC genericos (XAXX/XEXX) dentro de validos: "
                  f"{r['genericos']}")
        print("   ejemplos:")
        # validos primero (mas informativos), luego el resto
        orden = sorted(r["muestra"], key=lambda m: m["clase"] != "valido")
        for m in orden[:5]:
            print(f"     {m['proveedor'][:46]:<46} {m['rfc']:<15} "
                  f"{m['monto'] or '-':<16} [{m['clase']}]")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--estados", default=ESTADOS_DEFAULT,
                    help="nombres separados por coma (default: %(default)s)")
    ap.add_argument("--ejercicio",
                    help="fija el ejercicio (default: prueba el año en curso "
                         "y cae al anterior)")
    ap.add_argument("--objetivo", type=int, default=200,
                    help="filas a muestrear por estado (default: %(default)s)")
    ap.add_argument("--json", metavar="RUTA",
                    help="vuelca la muestra cruda como JSON en RUTA")
    args = ap.parse_args()

    ejercicios = (args.ejercicio,) if args.ejercicio else EJERCICIOS
    nombres = [n for n in args.estados.split(",") if n.strip()]
    print("resolviendo Turnstile (scrapling)...", file=sys.stderr)
    ses = SesionPNT()
    ids = ids_entidades(ses, nombres)
    resultados = []
    for estado, id_ent in ids.items():
        print(f"sondeando {estado} (id {id_ent})...", file=sys.stderr)
        try:
            resultados.append(
                sondea_estado(ses, estado, id_ent, args.objetivo, ejercicios))
        except Exception as e:  # un estado caido no tira a los demas
            resultados.append({"estado": estado, "id_entidad": id_ent,
                               "n": 0, "error": repr(e)[:200]})
    imprime_informe(resultados)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=1)
        print(f"\nmuestra cruda -> {args.json}")


if __name__ == "__main__":
    main()
