#!/usr/bin/env python
"""Genera web/src/components/mexico-puntos.ts: la silueta de México como
retícula regular de puntos, para el mapa de la portada.

Uso (una sola vez; el resultado se rastrea en git):
    curl -sL https://raw.githubusercontent.com/johan/world.geo.json/master/countries/MEX.geo.json -o /tmp/mex.geo.json
    python scripts/gen_mexico_puntos.py /tmp/mex.geo.json
"""
import json
import math
import sys
from pathlib import Path

COLS = 70  # columnas de la retícula a lo ancho del país

DESTINO = Path(__file__).resolve().parent.parent / "web" / "src" / "components" / "mexico-puntos.ts"


def dentro(lon: float, lat: float, anillo: list) -> bool:
    adentro = False
    for i in range(len(anillo)):
        x1, y1 = anillo[i - 1]
        x2, y2 = anillo[i]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            adentro = not adentro
    return adentro


def main(ruta_geojson: str) -> None:
    g = json.load(open(ruta_geojson))
    anillo = g["features"][0]["geometry"]["coordinates"][0]
    lons = [p[0] for p in anillo]
    lats = [p[1] for p in anillo]
    lon0, lon1 = min(lons), max(lons)
    lat0, lat1 = min(lats), max(lats)
    k = math.cos(math.radians((lat0 + lat1) / 2))  # equirectangular
    ancho = (lon1 - lon0) * k
    alto = lat1 - lat0
    paso = ancho / (COLS - 1)

    puntos = []
    filas = int(alto / paso) + 1
    for fi in range(filas):
        lat = lat0 + fi * paso
        for ci in range(COLS):
            lon = lon0 + ci * paso / k
            if dentro(lon, lat, anillo):
                puntos.append((ci * paso / ancho, 1 - fi * paso / alto))

    pares = ", ".join(f"{x:.3f}, {y:.3f}" for x, y in puntos)
    DESTINO.write_text(
        "// Generado por scripts/gen_mexico_puntos.py — no editar a mano.\n"
        "// Silueta de México como retícula de puntos, coordenadas [x, y]\n"
        "// normalizadas a [0, 1] (y crece hacia el sur, como en pantalla).\n"
        f"export const ASPECTO = {ancho / alto:.4f};\n"
        f"export const BBOX = {{ lon0: {lon0}, lon1: {lon1}, lat0: {lat0}, lat1: {lat1}, k: {k:.6f} }};\n"
        f"export const PUNTOS: number[] = [{pares}];\n",
        encoding="utf-8",
    )
    print(f"{len(puntos)} puntos -> {DESTINO}")


if __name__ == "__main__":
    main(sys.argv[1])
