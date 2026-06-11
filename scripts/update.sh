#!/usr/bin/env bash
# One-command refresh: download sources -> run detectors -> rebuild site.
set -euo pipefail
cd "$(dirname "$0")/.."

scripts/download_data.sh
PY=.venv/bin/python
"$PY" scripts/fetch_sfp.py || echo "WARN: SFP refresh failed, using cached"
for d in detectors/d01_efos_contracts.py detectors/d01h_efos_historico.py \
         detectors/d02_direct_award_concentration.py detectors/d03_benford.py \
         detectors/d04_young_winners.py detectors/d05_sfp_sancionados.py; do
  echo "== $d"
  "$PY" "$d"
done
"$PY" scripts/build_site.py
echo "tracker updated: site/index.html"
