"""Esquema del listado 69-B del SAT — vocabulario compartido entre el tier
batch (vista DuckDB) y el realtime (EfosIndex)."""
EFOS_COLS = [
    "no", "rfc", "nombre", "situacion",
    "oficio_presuncion_sat", "pub_sat_presuntos", "oficio_presuncion_dof", "pub_dof_presuntos",
    "oficio_desvirtuaron_sat", "pub_sat_desvirtuados", "oficio_desvirtuaron_dof", "pub_dof_desvirtuados",
    "oficio_definitivos_sat", "pub_sat_definitivos", "oficio_definitivos_dof", "pub_dof_definitivos",
    "oficio_sentencia_sat", "pub_sat_sentencia", "oficio_sentencia_dof", "pub_dof_sentencia",
]
