"""Ramos presupuestarios 60-91: los 32 estados en ComprasMX.

Cuando un estado o municipio contrata con cargo a recursos federales por
convenio (LAASSP art. 1 fr. V), el procedimiento entra a ComprasMX con
'Orden de gobierno' = GEM y el ramo de su entidad federativa. La tabla
reproduce los pares (Clave Ramo, Descripción Ramo) observados en los CSV
anuales 2023-2025 — los 32 estados, alfabéticos. El número de procedimiento
trae el ramo como segundo segmento: 'AA-60-N68-901024986-N-32-2023' -> 60.
"""
import re

RAMO_ESTADO = {
    60: "AGUASCALIENTES",
    61: "BAJA CALIFORNIA",
    62: "BAJA CALIFORNIA SUR",
    63: "CAMPECHE",
    64: "COAHUILA DE ZARAGOZA",
    65: "COLIMA",
    66: "CHIAPAS",
    67: "CHIHUAHUA",
    68: "CIUDAD DE MÉXICO",
    69: "DURANGO",
    70: "GUANAJUATO",
    71: "GUERRERO",
    72: "HIDALGO",
    73: "JALISCO",
    74: "MÉXICO",
    75: "MICHOACÁN DE OCAMPO",
    76: "MORELOS",
    77: "NAYARIT",
    78: "NUEVO LEÓN",
    79: "OAXACA",
    80: "PUEBLA",
    81: "QUERÉTARO",
    82: "QUINTANA ROO",
    83: "SAN LUIS POTOSÍ",
    84: "SINALOA",
    85: "SONORA",
    86: "TABASCO",
    87: "TAMAULIPAS",
    88: "TLAXCALA",
    89: "VERACRUZ DE IGNACIO DE LA LLAVE",
    90: "YUCATÁN",
    91: "ZACATECAS",
}

_NUMERO = re.compile(r"^[A-Z]{2}-(\d{1,3})-")


def estado_de_ramo(clave) -> str | None:
    """Estado para una clave de ramo GEM; None para ramos federales."""
    try:
        return RAMO_ESTADO.get(int(clave))
    except (TypeError, ValueError):
        return None


def estado_de_numero(numero: str | None) -> str | None:
    """Estado a partir del número de procedimiento ('LA-66-014-…' -> CHIAPAS).

    Los procedimientos de la administración federal (ramos 1-59) y los
    números que no siguen el formato devuelven None.
    """
    m = _NUMERO.match(numero or "")
    return estado_de_ramo(m.group(1)) if m else None
