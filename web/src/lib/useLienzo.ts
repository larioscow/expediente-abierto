"use client";

import { useEffect, useRef } from "react";

type Dibujo = (
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  t: number,
) => void;

// Ciclo de vida común de los lienzos del sitio: escala por devicePixelRatio,
// rAF pausado fuera de pantalla o con la pestaña oculta, repintado en cada
// resize (también con el rAF suspendido, para que el bitmap nunca quede en
// blanco) y un solo cuadro estático cuando el lector pide menos movimiento.
export function useLienzo(dibuja: Dibujo, deps: unknown[], tEstatico = 0.4) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    let w = 0;
    let h = 0;
    let raf = 0;
    let t = tEstatico;
    let ultimo = 0;
    let enPantalla = true;
    const reducir = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const ajusta = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const pinta = () => dibuja(ctx, w, h, t);

    const cuadro = (ahora: number) => {
      t += Math.min((ahora - ultimo) / 1000, 0.05);
      ultimo = ahora;
      pinta();
      raf = requestAnimationFrame(cuadro);
    };

    const arranca = () => {
      cancelAnimationFrame(raf);
      ultimo = performance.now();
      raf = requestAnimationFrame(cuadro);
    };

    const redimensiona = () => {
      ajusta();
      pinta();
    };

    ajusta();
    pinta();

    if (reducir) {
      window.addEventListener("resize", redimensiona);
      return () => window.removeEventListener("resize", redimensiona);
    }

    const visibilidad = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden && enPantalla) arranca();
    };

    const observador = new IntersectionObserver(([e]) => {
      enPantalla = e.isIntersecting;
      cancelAnimationFrame(raf);
      if (enPantalla && !document.hidden) arranca();
    });

    arranca();
    observador.observe(canvas);
    window.addEventListener("resize", redimensiona);
    document.addEventListener("visibilitychange", visibilidad);
    return () => {
      cancelAnimationFrame(raf);
      observador.disconnect();
      window.removeEventListener("resize", redimensiona);
      document.removeEventListener("visibilitychange", visibilidad);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return ref;
}
