"use client";

import { useMemo } from "react";
import { useLienzo } from "@/lib/useLienzo";
import { ASPECTO, BBOX, PUNTOS } from "./mexico-puntos";

// México como matriz de puntos blancos en perspectiva 3D: la retícula
// generada por scripts/gen_mexico_puntos.py, inclinada y con una banda de
// barrido que recorre el país; las entidades con procedimientos bajo
// observación se marcan en rojo. Canvas 2D puro, sin dependencias.

const CENTROIDES: Record<string, [number, number]> = {
  AGUASCALIENTES: [21.88, -102.29],
  "BAJA CALIFORNIA SUR": [25.0, -111.7],
  "BAJA CALIFORNIA": [30.0, -115.0],
  CAMPECHE: [18.9, -90.4],
  CHIAPAS: [16.5, -92.5],
  CHIHUAHUA: [28.8, -106.4],
  "CIUDAD DE MEXICO": [19.36, -99.15],
  COAHUILA: [27.3, -102.0],
  COLIMA: [19.1, -104.0],
  DURANGO: [24.5, -104.9],
  GUANAJUATO: [21.0, -101.0],
  GUERRERO: [17.6, -99.9],
  HIDALGO: [20.5, -98.9],
  JALISCO: [20.6, -103.6],
  MEXICO: [19.3, -99.65],
  MICHOACAN: [19.2, -101.9],
  MORELOS: [18.75, -99.07],
  NAYARIT: [21.8, -105.0],
  "NUEVO LEON": [25.6, -100.0],
  OAXACA: [17.0, -96.5],
  PUEBLA: [19.0, -97.9],
  QUERETARO: [20.8, -99.9],
  "QUINTANA ROO": [19.6, -88.05],
  "SAN LUIS POTOSI": [22.6, -100.4],
  SINALOA: [25.0, -107.5],
  SONORA: [29.6, -110.9],
  TABASCO: [17.9, -92.6],
  TAMAULIPAS: [24.3, -98.6],
  TLAXCALA: [19.4, -98.16],
  VERACRUZ: [19.4, -96.7],
  YUCATAN: [20.8, -89.0],
  ZACATECAS: [23.3, -102.6],
};
const LLAVES = Object.keys(CENTROIDES).sort((a, b) => b.length - a.length);

const TILT = 0.72; // inclinación del plano (rad)
const FOCO = 1.9;

function normaliza(lat: number, lon: number): [number, number] {
  return [
    (lon - BBOX.lon0) / (BBOX.lon1 - BBOX.lon0),
    1 - (lat - BBOX.lat0) / (BBOX.lat1 - BBOX.lat0),
  ];
}

function centroide(entidad: string): [number, number] | null {
  const n = entidad
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .trim();
  const llave = LLAVES.find((c) => n.startsWith(c));
  return llave ? normaliza(...CENTROIDES[llave]) : null;
}

export function MapaMatriz({ entidades }: { entidades: string[] }) {
  const marcas = useMemo(
    () =>
      [...new Set(
        entidades
          .map(centroide)
          .filter(Boolean)
          .map((m) => (m as [number, number]).join(",")),
      )].map((s) => s.split(",").map(Number) as [number, number]),
    [entidades],
  );

  const reducir =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const ref = useLienzo(
    (ctx, w, h, t) => {
      ctx.clearRect(0, 0, w, h);
      const S = Math.min(w / (ASPECTO * 1.06), h / 0.98);
      const giro = 0.09 * Math.sin(t * 0.22);
      const barrido = ((t * 0.14) % 1.45) * (ASPECTO + 0.7) - (ASPECTO + 0.7) / 2;
      const grosor = Math.max(1.1, w / 300);

      // proyecta coordenadas normalizadas del mapa a pantalla
      const proyecta = (nx: number, ny: number) => {
        const wx = (nx - 0.5) * ASPECTO;
        const wy = ny - 0.5;
        const rx = wx * Math.cos(giro) - wy * Math.sin(giro);
        const ry = wx * Math.sin(giro) + wy * Math.cos(giro);
        const s = FOCO / (FOCO - ry * Math.sin(TILT));
        return {
          x: w / 2 + rx * s * S,
          y: h / 2 + ry * Math.cos(TILT) * s * S,
          s,
          rx,
        };
      };

      for (let i = 0; i < PUNTOS.length; i += 2) {
        const p = proyecta(PUNTOS[i], PUNTOS[i + 1]);
        const luz = Math.exp(-(((p.rx - barrido) * 6.5) ** 2));
        const brillo = 0.92 + 0.08 * Math.sin(t * 1.7 + i * 1.2);
        const a = Math.min(1, (0.42 + 0.5 * (p.s - 0.8)) * 1.6 * brillo + luz * 0.5);
        const r = grosor * p.s * (1 + luz * 0.7);
        ctx.fillStyle = `rgba(235, 238, 246, ${a.toFixed(3)})`;
        ctx.fillRect(p.x - r / 2, p.y - r / 2, r, r);
      }

      for (const [nx, ny] of marcas) {
        const p = proyecta(nx, ny);
        const r = grosor * 2.4 * p.s;
        ctx.save();
        ctx.shadowColor = "rgba(255, 45, 69, .9)";
        ctx.shadowBlur = r * 5;
        ctx.fillStyle = "#ff2d45";
        ctx.beginPath();
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
        if (!reducir) {
          const fase = (t % 2.6) / 2.6;
          ctx.strokeStyle = `rgba(255, 45, 69, ${(0.55 * (1 - fase)).toFixed(3)})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.arc(p.x, p.y, r + fase * r * 6, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
    },
    [marcas, reducir],
  );

  return <canvas ref={ref} aria-hidden="true" />;
}
