#!/usr/bin/env bash
# Instala (o reinstala) los agentes launchd que mantienen el sitio vivo:
#   com.expedienteabierto.batch — diario 07:30: descarga fuentes -> detectores
#                                 -> exporta -> construye -> despliega a Vercel
#   com.expedienteabierto.poll  — cada 30 min: poll en vivo de ComprasMX ->
#                                 alertas -> despliega solo si algo cambió
# Idempotente. Desinstalar: launchctl bootout gui/$(id -u)/com.expedienteabierto.batch
#                           launchctl bootout gui/$(id -u)/com.expedienteabierto.poll
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$REPO/data/state/logs"
mkdir -p "$AGENTS" "$LOGS"

write_plist () {
  local label="$1" script="$2" schedule="$3"
  cat > "$AGENTS/$label.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$REPO/scripts/$script</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/share/fnm/aliases/default/bin</string>
    <key>HOME</key><string>$HOME</string>
  </dict>
  $schedule
  <key>StandardOutPath</key><string>$LOGS/${label##*.}.log</string>
  <key>StandardErrorPath</key><string>$LOGS/${label##*.}.log</string>
</dict>
</plist>
EOF
}

write_plist "com.expedienteabierto.batch" "publish.sh" \
  "<key>StartCalendarInterval</key><dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>30</integer></dict>"
write_plist "com.expedienteabierto.poll" "realtime_poll.sh" \
  "<key>StartInterval</key><integer>1800</integer><key>RunAtLoad</key><true/>"

UID_N=$(id -u)
for label in com.expedienteabierto.batch com.expedienteabierto.poll; do
  launchctl bootout "gui/$UID_N/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_N" "$AGENTS/$label.plist"
  launchctl enable "gui/$UID_N/$label"
  echo "instalado: $label"
done
launchctl list | grep expedienteabierto || true
echo "logs: $LOGS/{batch,poll}.log"
