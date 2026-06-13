"""Una sola forma de leer fechas de fuentes de gobierno en todo el proyecto."""
from datetime import date, datetime

_FECHA_FORMATOS = ("%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y")


def parse_fecha(s) -> date | None:
    """ISO (con o sin hora) y dd/mm/yyyy (con o sin hora).
    Devuelve date o None — nunca lanza."""
    if not isinstance(s, str) or not s.strip():
        return None
    s = s.strip()
    try:
        return datetime.fromisoformat(s[:19].rstrip("Z")).date()
    except ValueError:
        pass
    for fmt in _FECHA_FORMATOS:
        try:
            return datetime.strptime(s[:16], fmt).date()
        except ValueError:
            continue
    return None
