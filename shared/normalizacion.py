"""Normalización de nombres de empresa — única fuente para el tier Python
(realtime) y el tier SQL (batch); el lockstep lo exige tests/test_normalize.py."""
import re
import unicodedata

# Sufijos de forma legal como quedan TRAS sustituir puntuación por espacios
# ("S.A. de C.V." -> "S A DE C V"). Solo se recortan al final del nombre.
LEGAL_SUFFIXES = [
    "SA DE CV", "S A DE C V", "S DE RL DE CV", "S DE R L DE C V",
    "SAPI DE CV", "S A P I DE C V", "SAB DE CV", "S A B DE C V",
    "SAS", "S A S", "SRL", "S R L", "S DE RL", "S DE R L",
    "SC", "S C", "AC", "A C", "SOFOM ENR", "SOFOM E N R", "SOFOM",
]

_SUFFIX_ALT = "|".join(sorted(LEGAL_SUFFIXES, key=len, reverse=True))
_SUFFIX_RE = re.compile(rf"( (?:{_SUFFIX_ALT}))+$")


def normalize(name: str | None) -> str:
    """Normaliza para cruce: sin acentos, mayúsculas, sin puntuación,
    sin sufijos legales al final."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Z0-9 ]", " ", s.upper())
    s = re.sub(r"\s+", " ", s).strip()
    return _SUFFIX_RE.sub("", s)


def sql_name_norm(col: str) -> str:
    """Expresión DuckDB equivalente a normalize() — en lockstep por test."""
    return (
        "regexp_replace(trim(regexp_replace(regexp_replace("
        f"upper(strip_accents({col})), '[^A-Z0-9 ]', ' ', 'g'), ' +', ' ', 'g')), "
        f"'( ({_SUFFIX_ALT}))+$', '')"
    )
