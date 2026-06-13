#!/usr/bin/env bash
# Publica el portal: corre el pipeline completo, construye web/ y despliega a
# producción en Vercel (proyecto expediente-abierto, CLI ya autenticada).
# Con --sin-datos se salta la descarga y solo re-exporta + construye + publica.
set -euo pipefail
cd "$(dirname "$0")/.."

# launchd corre con PATH mínimo: node/npm/vercel viven en el alias de fnm
command -v vercel >/dev/null 2>&1 || export PATH="$HOME/.local/share/fnm/aliases/default/bin:$PATH"

if [ "${1:-}" != "--sin-datos" ]; then
  scripts/update.sh
else
  .venv/bin/python scripts/export_web_data.py
fi

(
  cd web
  vercel pull --yes --environment=production > /dev/null
  vercel build --prod > /dev/null
  vercel deploy --prebuilt --prod
)
