#!/usr/bin/env bash
# Download raw source data with provenance (evidence chain: URL + retrieval time + sha256).
# Usage: scripts/download_data.sh
set -euo pipefail

RAW="$(cd "$(dirname "$0")/.." && pwd)/data/raw"
MANIFEST="$RAW/MANIFEST.tsv"
mkdir -p "$RAW"
[ -f "$MANIFEST" ] || printf "retrieved_at\tsha256\tbytes\tfile\turl\n" > "$MANIFEST"

fetch () {
  local url="$1" out="$2"
  echo ">> $out"
  curl -sSL --fail --retry 3 -o "$RAW/$out" "$url"
  local sha bytes ts
  sha=$(shasum -a 256 "$RAW/$out" | cut -d' ' -f1)
  bytes=$(stat -f%z "$RAW/$out")
  ts=$(date -Iseconds)
  printf "%s\t%s\t%s\t%s\t%s\n" "$ts" "$sha" "$bytes" "$out" "$url" >> "$MANIFEST"
}

fetch "https://wu1agsprosta001.blob.core.windows.net/agsc-publicaciones/Datos_abiertos/Documents_AGAFF/Listado_completo_69-B.csv" "sat_69b_completo.csv"
fetch "https://comprasmx.buengobierno.gob.mx/cnetassets/datos_abiertos_contratos_expedientes/Contratos_CompraNet2025.csv" "contratos_2025.csv"
fetch "https://comprasmx.buengobierno.gob.mx/cnetassets/datos_abiertos_contratos_expedientes/Contratos_CompraNet2024.csv" "contratos_2024.csv"
fetch "https://comprasmx.buengobierno.gob.mx/cnetassets/datos_abiertos_contratos_expedientes/Contratos_CompraNet2023.csv" "contratos_2023.csv"

echo "done"
