#!/usr/bin/env bash
# Download raw source data with provenance (evidence chain: URL + retrieval time + sha256).
#
# - Años de contratos dinámicos: 2023..año en curso. El portal publica el CSV
#   anual con rezago: si el del año corriente aún no existe, AVISO fuerte y
#   sigue (check_freshness.py lo reporta como ausente, nunca silencio).
# - Descarga condicional (If-Modified-Since vía -z): si la fuente no cambió,
#   el servidor responde 304 y no se re-bajan ~470 MB.
# - MANIFEST.tsv solo crece cuando el contenido cambió (sha256 distinto):
#   es bitácora de evidencia, no log de ejecuciones.
# - Una respuesta de 0 bytes cuenta como fallo (endpoint muerto), jamás se
#   instala sobre datos buenos.
#
# Usage: scripts/download_data.sh
set -euo pipefail

RAW="$(cd "$(dirname "$0")/.." && pwd)/data/raw"
MANIFEST="$RAW/MANIFEST.tsv"
mkdir -p "$RAW"
[ -f "$MANIFEST" ] || printf "retrieved_at\tsha256\tbytes\tfile\turl\n" > "$MANIFEST"

FAILURES=0

last_sha () { awk -F'\t' -v f="$1" '$4==f {s=$2} END {print s}' "$MANIFEST"; }

fetch () {
  local url="$1" out="$2" optional="${3:-}"
  local dest="$RAW/$out" tmp="$RAW/.$out.part"
  local args=(-sSL --retry 3 -o "$tmp" -w "%{http_code}")
  [ -f "$dest" ] && args+=(-z "$dest")
  local code
  code=$(curl "${args[@]}" "$url") || code="000"
  case "$code" in
    304)
      echo "ok $out (sin cambios, 304)"
      rm -f "$tmp"; return 0 ;;
    200) ;;
    404)
      rm -f "$tmp"
      if [ -n "$optional" ]; then
        echo "AVISO: $out aún no publicado por la fuente ($url)"
        return 0
      fi
      echo "ERROR: $out -> HTTP 404 ($url)"
      FAILURES=$((FAILURES+1)); return 0 ;;
    *)
      rm -f "$tmp"
      echo "ERROR: $out -> HTTP $code ($url)"
      FAILURES=$((FAILURES+1)); return 0 ;;
  esac

  if [ ! -s "$tmp" ]; then
    echo "ERROR: $out -> respuesta de 0 bytes (endpoint muerto), se conserva lo anterior"
    rm -f "$tmp"; FAILURES=$((FAILURES+1)); return 0
  fi

  local sha
  sha=$(shasum -a 256 "$tmp" | cut -d' ' -f1)
  if [ -f "$dest" ] && [ "$sha" = "$(last_sha "$out")" ]; then
    # el servidor renovó Last-Modified sin cambiar el contenido; tocar el
    # archivo para que el próximo If-Modified-Since sí dé 304
    echo "ok $out (sin cambios, mismo sha)"
    rm -f "$tmp"; touch "$dest"; return 0
  fi

  mv "$tmp" "$dest"
  local bytes ts
  bytes=$(wc -c < "$dest" | tr -d ' ')
  ts=$(date -Iseconds)
  printf "%s\t%s\t%s\t%s\t%s\n" "$ts" "$sha" "$bytes" "$out" "$url" >> "$MANIFEST"
  echo "++ $out ($bytes bytes, contenido nuevo)"
}

# SAT 69-B (EFOS) — actualización mensual
fetch "https://wu1agsprosta001.blob.core.windows.net/agsc-publicaciones/Datos_abiertos/Documents_AGAFF/Listado_completo_69-B.csv" "sat_69b_completo.csv"

# ComprasMX, CSV anual de contratos: 2023..año en curso. 2023 es el piso del
# lote con RFC exacto (el histórico 2010-2023 es cruce por nombre).
YEAR=$(date +%Y)
y=2023
while [ "$y" -le "$YEAR" ]; do
  opt=""
  [ "$y" -eq "$YEAR" ] && opt="opcional"
  fetch "https://comprasmx.buengobierno.gob.mx/cnetassets/datos_abiertos_contratos_expedientes/Contratos_CompraNet${y}.csv" "contratos_${y}.csv" "$opt"
  y=$((y+1))
done

# CFE contratos adjudicados (ATDT) — CFE contrata fuera de ComprasMX
fetch "https://repodatos.atdt.gob.mx/api_update/cfe/contratos_adjudicados/contratos_adjudicados.csv" "cfe_contratos_adjudicados.csv"

# CompraNet histórico 2010-2023 (estático, 950 MB): solo si no está en disco,
# para que un checkout limpio (CI) pueda reproducir d01h.
if [ ! -f "$RAW/compranet_historico.csv" ]; then
  fetch "https://repodatos.atdt.gob.mx/api_update/sabg/contratos_expedientes_sistema_historico_compranet/compranet_historico.csv" "compranet_historico.csv"
fi

if [ "$FAILURES" -gt 0 ]; then
  echo "download_data: $FAILURES fuente(s) fallaron"
  exit 1
fi
echo "done"
