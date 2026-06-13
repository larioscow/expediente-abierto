"use client";

import { useMemo } from "react";
import { useLienzo } from "@/lib/useLienzo";

// La violación, dibujada: cada empresa es una pista sobre un eje común de
// años; su ventana de inhabilitación se tiende como hilera de puntos
// blancos y cada contrato firmado adentro es un punto rojo cuyo tamaño
// crece con el importe. Canvas 2D puro, sin dependencias.

export type Ventana = {
  etiqueta: string;
  desde: string; // YYYY-MM-DD
  hasta: string;
  contratos: { fecha: string; importe: number }[];
};

const FILA = 36; // alto por empresa
const EJE = 20; // franja inferior del eje de años
const ARRIBA = 4;

export function VentanaSancion({ ventanas }: { ventanas: Ventana[] }) {
  const pistas = useMemo(() => {
    const vs = ventanas
      .map((v) => ({
        etiqueta: v.etiqueta.toLowerCase(),
        d: Date.parse(v.desde),
        h: Date.parse(v.hasta),
        c: v.contratos
          .map((c) => ({ t: Date.parse(c.fecha), m: c.importe }))
          .filter((c) => Number.isFinite(c.t)),
      }))
      .filter((v) => Number.isFinite(v.d) && Number.isFinite(v.h))
      .sort((a, b) => a.d - b.d);
    if (!vs.length) return null;
    const mes = 30 * 24 * 3600_000;
    const t0 = Math.min(...vs.map((v) => v.d)) - 3 * mes;
    const t1 = Math.max(...vs.map((v) => v.h)) + 3 * mes;
    return { vs, t0, t1 };
  }, [ventanas]);

  const reducir =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const alto = pistas ? ARRIBA + pistas.vs.length * FILA + EJE : 0;

  const ref = useLienzo(
    (ctx, w, h, t) => {
      if (!pistas) return;
      ctx.clearRect(0, 0, w, h);
      const { vs, t0, t1 } = pistas;
      const ax = (ms: number) => ((ms - t0) / (t1 - t0)) * (w - 2) + 1;
      const fam = getComputedStyle(ctx.canvas).fontFamily || "ui-monospace, monospace";

      // eje de años: columna de puntos tenues y etiqueta por enero
      const a0 = new Date(t0).getUTCFullYear() + 1;
      const a1 = new Date(t1).getUTCFullYear();
      ctx.font = `9.5px ${fam}`;
      ctx.textBaseline = "bottom";
      for (let año = a0; año <= a1; año++) {
        const px = ax(Date.UTC(año, 0, 1));
        ctx.fillStyle = "rgba(235, 238, 246, .12)";
        for (let y = ARRIBA + 6; y < h - EJE; y += 8) ctx.fillRect(px, y, 1, 1);
        ctx.fillStyle = "rgba(235, 238, 246, .55)";
        ctx.textAlign = "center";
        ctx.fillText(String(año), px, h - 4);
      }

      vs.forEach((v, i) => {
        const y = ARRIBA + i * FILA + 24;

        // etiqueta de la pista: anclada al inicio de la ventana, o al final
        // (alineada a la derecha) cuando la ventana arranca tarde, y siempre
        // recortada al espacio que de verdad queda hasta el borde
        ctx.font = `10px ${fam}`;
        ctx.textBaseline = "alphabetic";
        ctx.fillStyle = "rgba(235, 238, 246, .8)";
        const x0 = ax(v.d);
        const alaDerecha = x0 > w * 0.55;
        const ancla = alaDerecha ? Math.min(ax(v.h), w - 2) : x0;
        const espacio = (alaDerecha ? ancla : w - x0) - 4;
        ctx.textAlign = alaDerecha ? "right" : "left";
        let nombre = v.etiqueta;
        while (nombre.length > 4 && ctx.measureText(nombre).width > espacio) {
          nombre = nombre.slice(0, -2);
        }
        ctx.fillText(nombre === v.etiqueta ? nombre : `${nombre}…`, ancla, y - 9);

        // la ventana de inhabilitación: hilera de puntos blancos
        const x1 = ax(v.h);
        for (let px = x0; px <= x1; px += 7) {
          const brillo = 0.45 + 0.1 * Math.sin(t * 1.6 + px * 0.7);
          ctx.fillStyle = `rgba(235, 238, 246, ${brillo.toFixed(3)})`;
          ctx.fillRect(px, y, 1.6, 1.6);
        }
        // bordes de la ventana
        ctx.fillStyle = "rgba(235, 238, 246, .85)";
        ctx.fillRect(x0, y - 3, 1.6, 8);
        ctx.fillRect(x1, y - 3, 1.6, 8);

        // contratos firmados adentro: puntos rojos, área según importe
        v.c.forEach((c, j) => {
          const px = ax(c.t);
          const r = Math.min(6, 1.8 + Math.log10(Math.max(c.m, 10)) * 0.55);
          ctx.save();
          ctx.shadowColor = "rgba(255, 45, 69, .9)";
          ctx.shadowBlur = r * 3;
          ctx.fillStyle = "#ff2d45";
          ctx.beginPath();
          ctx.arc(px, y + 1, r, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
          if (!reducir) {
            const fase = ((t + i * 0.7 + j * 0.31) % 3.2) / 3.2;
            ctx.strokeStyle = `rgba(255, 45, 69, ${(0.45 * (1 - fase)).toFixed(3)})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(px, y + 1, r + fase * 10, 0, Math.PI * 2);
            ctx.stroke();
          }
        });
      });
    },
    [pistas, reducir],
  );

  if (!pistas) return null;
  return (
    <figure className="ventanas">
      <canvas ref={ref} style={{ height: alto }} aria-hidden="true" />
    </figure>
  );
}
