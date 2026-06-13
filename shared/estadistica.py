"""Estadística forense compartida — sin dependencias (math puro), probada en
lockstep con tests/test_estadistica.py.

Un hallazgo publicable necesita decir no solo "la tasa marcada es 4× la base"
sino "y el intervalo de confianza no toca a la base": el punto sin error es
una media verdad. Aquí viven los intervalos y pruebas que respaldan eso.
"""
from __future__ import annotations

import math

# z de la normal estándar para los niveles de confianza usuales
Z = {0.90: 1.6448536269514722, 0.95: 1.959963984540054,
     0.99: 2.5758293035489004}


def wilson_interval(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Intervalo de Wilson para una proporción k/n. Mejor que el normal
    (Wald) con n chico o tasas extremas, que es justo nuestro caso
    (pocas empresas marcadas, sanción rara). Devuelve (low, high) en [0,1]."""
    if n <= 0:
        return (0.0, 0.0)
    z = Z.get(conf) or _z_from_conf(conf)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centro = (p + z2 / (2 * n)) / denom
    margen = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (max(0.0, centro - margen), min(1.0, centro + margen))


def _z_from_conf(conf: float) -> float:
    """z = Phi^{-1}((1+conf)/2) por bisección sobre erf — para niveles fuera
    de la tabla."""
    objetivo = (1 + conf) / 2
    lo, hi = 0.0, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if 0.5 * (1 + math.erf(mid / math.sqrt(2))) < objetivo:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _log_choose(n: int, k: int) -> float:
    if k < 0 or k > n:
        return -math.inf
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1))


def fisher_exact_greater(a: int, b: int, c: int, d: int) -> float:
    """p-value de Fisher exacto, cola derecha, para la tabla 2×2
        [[a, b],   marcadas: sancionadas-después (a) vs no (b)
         [c, d]]   no marcadas: sancionadas-después (c) vs no (d)
    H1: las marcadas se sancionan MÁS. Suma la prob. hipergeométrica de todas
    las tablas con a' >= a y los mismos márgenes. math puro (lgamma)."""
    a, b, c, d = int(a), int(b), int(c), int(d)
    if min(a, b, c, d) < 0:
        raise ValueError("conteos negativos")
    n = a + b + c + d
    if n == 0:
        return 1.0
    fila1, col1 = a + b, a + c
    log_denom = _log_choose(n, col1)
    lo = max(0, col1 - (c + d))          # a' no puede dejar la fila 2 negativa
    hi = min(fila1, col1)                # ni exceder su fila/columna
    total = 0.0
    for ap in range(a, hi + 1):
        if ap < lo:
            continue
        logp = (_log_choose(fila1, ap)
                + _log_choose(n - fila1, col1 - ap) - log_denom)
        total += math.exp(logp)
    return min(1.0, total)


def benford_first() -> dict[int, float]:
    """P(primer dígito = d) = log10(1 + 1/d), d ∈ 1..9."""
    return {d: math.log10(1 + 1 / d) for d in range(1, 10)}


def benford_second() -> dict[int, float]:
    """P(segundo dígito = d) = Σ_{k=1..9} log10(1 + 1/(10k+d)), d ∈ 0..9.
    El segundo dígito es más sensible al amañado de cifras que el primero."""
    return {d: sum(math.log10(1 + 1 / (10 * k + d)) for k in range(1, 10))
            for d in range(10)}


def z_digito(obs: int, n: int, p_esp: float) -> float:
    """Z de Nigrini para una proporción de dígito, con corrección de
    continuidad: (|obs/n - p| - 1/2n) / sqrt(p(1-p)/n). |Z|>1.96 ~ p<.05."""
    if n <= 0:
        return 0.0
    p_obs = obs / n
    cc = 1 / (2 * n)
    num = abs(p_obs - p_esp) - (cc if cc < abs(p_obs - p_esp) else 0.0)
    return num / math.sqrt(p_esp * (1 - p_esp) / n)


def mad_benford(frecuencias: dict[int, int], n: int,
                esperado: dict[int, float]) -> float:
    """Desviación media absoluta entre proporciones observadas y esperadas."""
    if n <= 0:
        return 0.0
    return sum(abs(frecuencias.get(d, 0) / n - p)
               for d, p in esperado.items()) / len(esperado)


def binomial_sf_half(k: int, n: int) -> float:
    """P(X >= k) con X ~ Binomial(n, 1/2), exacto vía lgamma.

    Es la prueba de signo local para amontonamiento bajo un umbral: si la
    densidad fuera suave, los contratos en una ventana angosta alrededor del
    corte caerían a cada lado como volados justos."""
    if n < 0 or k < 0:
        raise ValueError("conteos negativos")
    if k > n:
        return 0.0
    if k == 0:
        return 1.0
    log_half_n = n * math.log(0.5)
    total = 0.0
    for i in range(k, n + 1):
        total += math.exp(_log_choose(n, i) + log_half_n)
    return min(1.0, total)


def benjamini_hochberg(pvalues: list[float], q: float = 0.05) -> list[bool]:
    """Control de tasa de falso descubrimiento (FDR) de Benjamini-Hochberg.

    Con N pruebas simultáneas (p. ej. Benford sobre 129 instituciones), usar
    p<0.05 en cada una infla los falsos positivos. BH devuelve, para cada
    p-value EN EL ORDEN DE ENTRADA, si se rechaza la nula al nivel de FDR q.
    Rechaza todo p ordenado p_(i) <= q*i/N hasta el mayor i que cumple."""
    n = len(pvalues)
    if n == 0:
        return []
    orden = sorted(range(n), key=lambda i: pvalues[i])
    k_max = -1
    for rango, i in enumerate(orden, start=1):
        if pvalues[i] <= q * rango / n:
            k_max = rango
    rechaza = [False] * n
    for rango, i in enumerate(orden, start=1):
        if rango <= k_max:
            rechaza[i] = True
    return rechaza
