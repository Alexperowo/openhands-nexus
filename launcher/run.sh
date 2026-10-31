#!/usr/bin/env bash
# One Nexus service in the foreground for its ohn-*.service user unit.
# Logs: journalctl --user -u ohn-<name>. The key comes from the unit's EnvironmentFile.
set -euo pipefail
WORK=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export PATH="$HOME/.local/bin:$PATH"

# The tablet reaches the PC by its LAN address: take it from a local interface, not from the
# internet route (missing offline, a VPN tunnel when one is on).
lan_ip() {
  ip -4 -o addr show scope global |
    awk '$2 !~ /^(tun|tap|wg|docker|br-|virbr|veth)/ { sub(/\/.*/, "", $4); print $4 }' |
    grep -m1 -E '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)'
}

case "${1:-}" in
  models)
    # llama-swap.yaml names files of this folder relatively.
    cd -- "$WORK/models"
    exec ./llama-swap -config llama-swap.yaml -listen 127.0.0.1:18030
    ;;
  voice)
    cd -- "$WORK/voice"
    exec .venv/bin/uvicorn service:app --host 127.0.0.1 --port 18020
    ;;
  agent)
    : "${OHN_SESSION_KEY:?missing in session.env}" "${OHN_SECRET_KEY:?missing in session.env}"
    cd -- "$WORK/agent"
    export PORT=8010 OH_BIND_HOST=127.0.0.1 OH_CANVAS_SAFE_BACKEND_PORT=18010 \
      OH_CANVAS_SAFE_AUTOMATION_PORT=18011 OH_CANVAS_SAFE_VITE_PORT=3011 \
      OH_CANVAS_SAFE_STATE_DIR="$PWD/state/agent-canvas" OH_PERSISTENCE_DIR="$PWD/state" \
      LOCAL_BACKEND_API_KEY="$OHN_SESSION_KEY" OH_SECRET_KEY="$OHN_SECRET_KEY"
    # Canvas passes its environment on to agent-server: an SDK fix it loads at startup.
    export PYTHONPATH="$PWD/sdk-patch${PYTHONPATH:+:$PYTHONPATH}"
    # The agent's terminal gets the desktop commands (screen/); Holo4 and the Qwen-based models
    # point in 0-1000 of the screen.
    export PATH="$WORK/screen/bin:$PATH" COORDINATE_SYSTEM=0-1000
    mkdir -p "$OH_CANVAS_SAFE_STATE_DIR" state/skills
    # Nexus skills (agent/skills) reach the agent as user skills: agent-server reads them from
    # $OH_PERSISTENCE_DIR/skills, and only this agent, not other programs, looks there.
    for skill in skills/*/; do
      ln -sfn "../../${skill%/}" "state/skills/$(basename -- "$skill")"
    done
    # Canvas only logs it when its agent-server child dies and keeps running, so the unit would stay
    # "active" without an agent. Leave once 18010 stops answering (1 min) or never answers after
    # the start (5 min), and systemd restarts the stack.
    node node_modules/@openhands/agent-canvas/bin/agent-canvas.mjs -p 8010 -H 127.0.0.1 &
    canvas=$!
    trap 'kill -TERM "$canvas" 2>/dev/null; wait "$canvas"; exit 0' TERM INT
    answered=0 misses=0
    while kill -0 "$canvas" 2>/dev/null; do
      sleep 10 & wait $!
      if curl -fs -m 5 -o /dev/null http://127.0.0.1:18010/ready; then
        answered=1 misses=0
      elif ((++misses >= (answered ? 6 : 30))); then
        echo "agent-server on 18010 is not answering; exiting for a restart" >&2
        exit 1
      fi
    done
    wait "$canvas"
    ;;
  gateway)
    : "${OHN_SESSION_KEY:?missing in session.env}"
    D="$WORK/gateway"
    LAN_IP=${OHN_LAN_IP:-$(lan_ip || true)}
    [ -n "$LAN_IP" ] || { echo "no private LAN address; set OHN_LAN_IP in session.env" >&2; exit 1; }
    # nexus-start shows the tablet this same address.
    echo "$LAN_IP" >"${XDG_RUNTIME_DIR:-/tmp}/ohn-lan-ip"
    export LAN_IP XDG_DATA_HOME="$D/data" XDG_CONFIG_HOME="$D/config" CA_DIR="$D/ca" LOG_DIR="$D" \
      SHELL_DIST="$WORK/ui/dist"
    [ -f "$SHELL_DIST/index.html" ] || { echo "no ui/dist: run npm run build in ui" >&2; exit 1; }
    exec "$D/caddy" run --config "$D/Caddyfile" --adapter caddyfile
    ;;
  watch)
    # Outside the agent: restarts a running service that stopped answering (launcher/watch.py).
    exec python3 -I "$WORK/launcher/watch.py"
    ;;
  *) echo "usage: run.sh models|voice|agent|gateway|watch" >&2; exit 2 ;;
esac
