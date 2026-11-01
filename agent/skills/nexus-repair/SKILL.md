---
name: nexus-repair
description: Use when Nexus itself misbehaves (no voice or speech, the tablet page fails, the model is slow or will not load, an update broke something, a Nexus service error) or the owner asks to restart Nexus or a part of it. How to find the cause without stopping Nexus, what to fix yourself and what needs the owner's yes.
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
4. No voice: Nexus speech plays in the browser page (tablet or PC), not through this PC's sound settings.
   Check `ohn-voice`, its health and log. Never change this PC's sound devices or volume.
5. Video cards: `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader`.
   Another program (ComfyUI, a game, another model) holding memory is the usual reason a model will not load
   or runs slowly. Name that program to the owner; do not close it yourself.
6. Project files: `git -C ~/Agents/OpenHands-Nexus status --short` (a changed file is a suspect) and
   `cd ~/Agents/OpenHands-Nexus && ./check` (about 3 minutes, processor only, safe while Nexus runs).
7. Updates: `~/Agents/OpenHands-Nexus/update/nexus-update check --offline`; the update journal is in
   `~/.local/state/ohn/`. A fault that began right after an update points at that component.

Stay inside Nexus: other projects in `~/Agents` and the conversation files in `agent/state` are not suspects.
When the services answer, `git status` is clean and `./check` passes, do not keep searching: report what you
checked and ask the owner for one concrete example (the phrase, the page, the time it happened).

The watcher `ohn-watch` already restarts a silent service once and tells the owner; with a lost video card it
moves the model to the card that still works. Read its log before repeating what it did.

## Fix

- A project file: back it up first (git is the backup for tracked files), keep the change small, run
  `./check` after it. Never discard changes you did not make in this conversation: report them. A change of
  the owner that causes the fault may be corrected after a copy to `~/Agents/Backups/nexus-repair/`.
- Restarts go detached (the guard denies a direct `systemctl restart` of Nexus). A running voice or gateway
  that needs a restart for your fix to take effect: restart it yourself,
  `systemd-run --user --collect systemctl --user restart ohn-voice`, then check its health.
- An update rollback (`update/nexus-update rollback canvas|ik-llama|caddy|llama-swap|voice`) only after the
  owner says yes. Anything that restarts `ohn-agent` or `ohn-models` (canvas, ik-llama, llama-swap rollbacks,
  `ohn.target`) needs the owner's yes; their own request to restart is that yes. Hand it to the helper that
  runs it once your reply is sent and no conversation is at work:
  `systemd-run --user --collect ~/Agents/OpenHands-Nexus/launcher/when-idle <command>`
  (for example `... when-idle systemctl --user restart ohn-agent`). Then reply at once: what will restart and
  that Nexus will be silent for about two minutes. Do not wait for the restart: it happens after your turn.
- «Slow» or «hangs»: before a restart, look at the video cards and the model log (another program on the card,
  a very long conversation). Tell the owner the cause you found; a restart does not cure those.
- Never read `~/.config/openhands-nexus/session.env`, `agent/state/settings.json`, other key files or the
  environment of other programs (`/proc/*/environ`).
- A stopped Nexus service was stopped on purpose or failed past the watcher's one restart: do not start it on
  your own. Tell the owner and start it only after their yes.
- Never change DNS, VPN or proxy settings, and do not advise the owner to turn the VPN off: this PC needs it.
- Delete the temporary files you made (test audio, logs) before the report.

## Report

In plain Russian: what was wrong (fact or hypothesis), what you changed and how you checked it, and the one
action left for the owner, for example «нажмите „Остановить Nexus“, затем „Запустить Nexus“».
