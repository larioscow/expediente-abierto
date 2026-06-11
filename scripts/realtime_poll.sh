#!/usr/bin/env bash
# Near-real-time poll: check ComprasMX live, score new procedures, rebuild site.
# Cron example (every 30 min):
#   */30 * * * * /Users/larioscow/Dev/mx-corruption-detector/scripts/realtime_poll.sh >> /tmp/mx-poll.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m realtime.poll --max-detail 40 --threshold 2
.venv/bin/python scripts/build_site.py
