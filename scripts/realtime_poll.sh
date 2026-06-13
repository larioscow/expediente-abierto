#!/usr/bin/env bash
# Near-real-time poll: check ComprasMX live, score new procedures, rebuild and
# publish the site to Vercel SOLO si los datos exportados cambiaron (la
# mayoría de los polls no producen alertas nuevas -> ni build ni deploy).
# Programado vía launchd (scripts/install_launchd.sh) cada 30 min.
set -euo pipefail
cd "$(dirname "$0")/.."

# launchd corre con PATH mínimo: node/npm/vercel viven en el alias de fnm
command -v vercel >/dev/null 2>&1 || export PATH="$HOME/.local/share/fnm/aliases/default/bin:$PATH"

# One poll at a time: a slow run (headless browser) must not overlap the next
# cron firing and interleave writes to seen.json/alerts.jsonl. mkdir is the
# portable atomic lock (no flock on macOS). Stale locks (crashed run, >2h)
# are reclaimed.
LOCK=data/state/poll.lock
mkdir -p data/state
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then
    echo "WARN: reclaiming stale lock (>2h)"
    rmdir "$LOCK" 2>/dev/null || true
    mkdir "$LOCK" 2>/dev/null || { echo "poll already running, skipping"; exit 0; }
  else
    echo "poll already running, skipping"
    exit 0
  fi
fi
trap 'rmdir "$LOCK"' EXIT

.venv/bin/python -m realtime.poll --max-detail 40 --threshold 2 --pages 3
.venv/bin/python scripts/export_web_data.py

# Huella de los datos publicables: si no cambió nada, no hay que desplegar.
# (los nombres de archivo no llevan espacios; LC_ALL fija el orden)
web_data_sha () {
  find web/src/data web/public/datos -type f \( -name '*.json' -o -name '*.csv' \) \
    | LC_ALL=C sort | xargs shasum -a 256 | shasum -a 256 | cut -d' ' -f1
}
SHA_FILE=data/state/web_data.sha
NUEVO=$(web_data_sha)
ANTERIOR=$(cat "$SHA_FILE" 2>/dev/null || echo "")
if [ "$NUEVO" = "$ANTERIOR" ]; then
  echo "sin cambios en datos publicables; no se despliega"
  exit 0
fi

(
  cd web
  vercel pull --yes --environment=production > /dev/null
  vercel build --prod > /dev/null
  vercel deploy --prebuilt --prod
)
echo "$NUEVO" > "$SHA_FILE"
