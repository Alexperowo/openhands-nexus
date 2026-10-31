---
name: nexus-repair
description: Use when Nexus itself misbehaves (no voice or speech, the tablet page fails, the model is slow or will not load, an update broke something, a Nexus service error). How to find the cause without stopping Nexus, what to fix yourself and what needs the owner's yes.
---

# Nexus: find and fix a fault

You run inside Nexus. Your terminal belongs to `ohn-agent` (agent-server 18010) and your model is served by
`ohn-models` (llama-swap 18030). Restarting either ends your own turn. The project is `~/Agents/OpenHands-Nexus`.

## Find the cause (safe while Nexus runs)

1. Services: `systemctl --user --no-pager status ohn-models ohn-agent ohn-voice ohn-gateway ohn-watch | grep -E '●|Active:'`
2. Their log: `journalctl --user -u ohn-<name> --since -30min --no-pager | tail -n 80`
3. Answers: `curl --noproxy '*' -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18020/health` (voice),
   `.../18010/ready` (agent); `curl --noproxy '*' -s http://127.0.0.1:18030/running` (the loaded model);
   the tablet page: `curl --noproxy '*' -sk -o /dev/null -w '%{http_code}\n' https://localhost:8443/`
4. Video cards: `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader`.
   Another program (ComfyUI, a game, another model) holding memory is the usual reason a model will not load
   or runs slowly. Name that program to the owner; do not close it yourself.
5. Project files: `git -C ~/Agents/OpenHands-Nexus status --short` (a changed file is a suspect) and
   `cd ~/Agents/OpenHands-Nexus && ./check` (about 3 minutes, processor only, safe while Nexus runs).
6. Updates: `~/Agents/OpenHands-Nexus/update/nexus-update check --offline`; the update journal is in
   `~/.local/state/ohn/`. A fault that began right after an update points at that component.

The watcher `ohn-watch` already restarts a silent service once and tells the owner; with a lost video card it
moves the model to the card that still works. Read its log before repeating what it did.

## Fix

- A project file: back it up first (git is the backup for tracked files), keep the change small, run
  `./check` after it. Never discard changes you did not make in this conversation: report them.
- A service restart or an update rollback (`update/nexus-update rollback canvas|ik-llama|caddy|llama-swap|voice`)
  only after the owner says yes. Voice and gateway restart without ending your turn. Anything that restarts
  `ohn-agent` or `ohn-models` (canvas, ik-llama, llama-swap rollbacks, `ohn.target`): first tell the owner that
  Nexus will be silent for about two minutes, then start it detached with a delay so your reply arrives:
  `systemd-run --user --collect --on-active=20 <command>`.
- Never read `~/.config/openhands-nexus/session.env`, `agent/state/settings.json` or other key files.
- Never start Nexus services that are stopped, never change DNS, VPN or proxy settings.

## Report

In plain Russian: what was wrong (fact or hypothesis), what you changed and how you checked it, and the one
action left for the owner, for example «нажмите „Остановить Nexus“, затем „Запустить Nexus“».
