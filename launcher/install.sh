#!/usr/bin/env bash
# Installs the Nexus user units and desktop shortcuts. Idempotent; nothing starts with the
# session: the units have no [Install] section, so they cannot be enabled by accident.
set -euo pipefail
WORK=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/openhands-nexus"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")

# Private keys: generated once, then kept (the agent's secrets.json is encrypted with OHN_SECRET_KEY).
umask 077
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/session.env" ]; then
  printf 'OHN_SESSION_KEY=%s\nOHN_SECRET_KEY=%s\n' "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" > "$CONFIG_DIR/session.env"
fi
umask 022

unit() { # name description extra-[Service]-lines
  cat > "$UNIT_DIR/ohn-$1.service" <<EOF
[Unit]
Description=Nexus: $2
PartOf=ohn.target
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=exec
EnvironmentFile=$CONFIG_DIR/session.env
ExecStart=/usr/bin/bash $WORK/launcher/run.sh $1
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
${3:-}
EOF
}
mkdir -p "$UNIT_DIR"
unit models "модели (llama-swap)"
# Loading a model pushes idle services into swap; paging the voice models back in made the
# first dictation take 12 s. The voice service and the agent are small, keep them in RAM.
unit voice "распознавание и синтез речи" "MemorySwapMax=0"
unit agent "агент OpenHands" "MemorySwapMax=0"
unit gateway "шлюз HTTPS для планшета"
unit watch "смотритель служб"
cat > "$UNIT_DIR/ohn.target" <<EOF
[Unit]
Description=Nexus: все службы (запуск ярлыком, не с системой)
Wants=ohn-models.service ohn-voice.service ohn-agent.service ohn-gateway.service ohn-watch.service
EOF
systemctl --user daemon-reload

shortcut() { # file name comment command icon
  local text="[Desktop Entry]
Type=Application
Name=$2
Comment=$3
Exec=$WORK/launcher/$4
Icon=$5
Terminal=false
Categories=Development;
"
  mkdir -p "$APP_DIR" "$DESKTOP_DIR"
  printf '%s' "$text" > "$APP_DIR/$1"
  printf '%s' "$text" > "$DESKTOP_DIR/$1"
  chmod +x "$DESKTOP_DIR/$1"
  # File managers that guard desktop launchers (Nemo, Nautilus) read this flag; others ignore it.
  gio set "$DESKTOP_DIR/$1" metadata::trusted true 2>/dev/null || true
}
chmod +x "$WORK/launcher/nexus-start" "$WORK/launcher/nexus-stop"
shortcut ohn-start.desktop "Запустить Nexus" "Модель, голос, агент и шлюз для планшета" nexus-start media-playback-start
shortcut ohn-stop.desktop "Остановить Nexus" "Остановить все службы Nexus и выгрузить модель" nexus-stop media-playback-stop
echo "Готово: ярлыки «Запустить Nexus» и «Остановить Nexus» на рабочем столе и в меню."
