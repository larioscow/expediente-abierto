"use client";

import { useMemo } from "react";
import { useLienzo } from "@/lib/useLienzo";

// Las últimas 24 horas del monitor como tira de pulso: una retícula de
// puntos (el mismo lenguaje del mapa) y una espiga roja por cada alerta,
// con la altura proporcional a su riesgo. El cursor de la derecha es
// "ahora". Canvas 2D puro, sin dependencias.

type Evento = { ts?: string; score: number };

const ALTO_EJE = 16; // franja inferior reservada al eje y sus etiquetas

export function PulsoAlertas({ alertas }: { alertas: Evento[] }) {
  const eventos = useMemo(
    () =>
      alertas
        .map((a) => ({ t: Date.parse(a.ts ?? ""), score: a.score }))
        .filter((e) => Number.isFinite(e.t))
        .sort((a, b) => a.t - b.t),
    [alertas],
  );

  const reducir =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const ref = useLienzo(
    (ctx, w, h, t) => {
      ctx.clearRect(0, 0, w, h);
      const fin = Date.now();
      const hora = 3600_000;
      const inicio = Math.min(fin - 24 * hora, eventos[0]?.t ?? Infinity);
      const horas = Math.round((fin - inicio) / hora);
      const ax = (ms: number) => 1 + ((ms - inicio) / (fin - inicio)) * (w - 2);
      const base = h - ALTO_EJE;

      // retícula: tres hileras de puntos, la de la base más viva, y un
      // punto mayor por cada hora cumplida
      for (let fila = 0; fila < 3; fila++) {
        const y = base - fila * 9;
        ctx.fillStyle = `rgba(235, 238, 246, ${(0.2 - fila * 0.06).toFixed(2)})`;
        for (let px = 0; px <= w; px += 9) ctx.fillRect(px, y, 1.2, 1.2);
      }
      for (let m = Math.ceil(inicio / hora) * hora; m <= fin; m += hora) {
        ctx.fillStyle = "rgba(235, 238, 246, .5)";
        ctx.fillRect(ax(m) - 1, base - 1, 2.2, 2.2);
      }

      // espigas: una por alerta, altura = riesgo
      let xPrevia = -10;
      let corrimiento = 0;
      eventos.forEach((e, i) => {
        let px = ax(e.t);
        if (px - xPrevia < 4) {
          corrimiento += 4;
          px += corrimiento;
        } else {
          corrimiento = 0;
        }
        xPrevia = px;
        const alto = Math.min(base - 10, 22 + e.score * 7);
        ctx.strokeStyle = "rgba(255, 45, 69, .85)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(px, base);
        ctx.lineTo(px, base - alto);
        ctx.stroke();

        ctx.save();
        ctx.shadowColor = "rgba(255, 45, 69, .9)";
        ctx.shadowBlur = 11;
        ctx.fillStyle = "#ff2d45";
        ctx.beginPath();
        ctx.arc(px, base - alto, 2.4, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        if (i === eventos.length - 1 && !reducir) {
          const fase = (t % 2.6) / 2.6;
          ctx.strokeStyle = `rgba(255, 45, 69, ${(0.55 * (1 - fase)).toFixed(3)})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.arc(px, base - alto, 2.4 + fase * 15, 0, Math.PI * 2);
          ctx.stroke();
        }
      });

      // cursor "ahora" en el borde derecho
      const guiño = reducir ? 0.55 : 0.35 + 0.3 * (0.5 + 0.5 * Math.sin(t * 2.4));
      ctx.fillStyle = `rgba(235, 238, 246, ${guiño.toFixed(3)})`;
      ctx.fillRect(w - 1.5, base - 34, 1.5, 34);

      // etiquetas del eje, en canvas para no depender de la hidratación
      const fam = getComputedStyle(ctx.canvas).fontFamily || "ui-monospace, monospace";
      ctx.font = `9.5px ${fam}`;
      ctx.fillStyle = "rgba(235, 238, 246, .55)";
      ctx.textBaseline = "bottom";
      ctx.textAlign = "left";
      ctx.fillText(`hace ${horas} h`, 0, h - 1);
      ctx.textAlign = "right";
      ctx.fillText("ahora", w, h - 1);
    },
    [eventos, reducir],
  );

  return (
    <div className="pulso">
      <canvas ref={ref} aria-hidden="true" />
    </div>
  );
}
