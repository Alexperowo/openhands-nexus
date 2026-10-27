#!/usr/bin/env python3
"""Watcher of the Nexus services, outside the agent (ohn-watch.service, part of ohn.target).

systemd restarts a service whose process exits, not one that hangs while running, and the agent
cannot be trusted to restore its own ground. Every 15 s this asks each running service whether it
answers. One silent for a minute is restarted once; the owner is then told on the PC and the
tablet whether that helped. Crashes systemd restarted and services it gave up on are told too.

A stopped service is never started, and none is restarted for working long: the checks are
answered while a model computes (voice /health is async, llama-swap and Caddy answer alongside).
"""
import json
import ssl
import subprocess
import time
import urllib.request
from pathlib import Path

WORK = Path(__file__).resolve().parent.parent
INTERVAL = 15
PROBE_TIMEOUT = 5
SILENT_FOR = 60
JOURNAL = "Журнал: journalctl --user -u {unit}"


class Check:
    def __init__(self, name, url=None, grace=0):
        self.name, self.url, self.grace = name, url, grace


# The agent has its own check in run.sh (18010/ready); here only its crashes and failures are told.
# grace: seconds after a (re)start before silence counts — the voice models load for ~10 s.
CHECKS = {
    "ohn-models": Check("модели", "http://127.0.0.1:18030/running", grace=60),
    "ohn-voice": Check("голос", "http://127.0.0.1:18020/health", grace=180),
    "ohn-agent": Check("агент"),
    "ohn-gateway": Check("шлюз для планшета", "https://localhost:8443/", grace=30),
}


class Episode:
    """What the watcher knows of one service since it last answered."""
    def __init__(self):
        self.silent_since = None
        self.restarted = False
        self.gave_up = False


class Watcher:
    def __init__(self, show, probe, restart, tell, clock=time.monotonic):
        self.show, self.probe, self.restart, self.tell, self.clock = show, probe, restart, tell, clock
        self.episodes = {unit: Episode() for unit in CHECKS}
        self.restarts = {}
        self.failed = set()

    def step(self):
        for unit, check in CHECKS.items():
            self.look(unit, check, self.show(unit))

    def look(self, unit, check, state):
        service = f"Nexus: служба «{check.name}»"
        # NRestarts counts systemd's own restarts after a crash; a manual start resets it.
        count = int(state.get("NRestarts") or 0)
        if count > self.restarts.get(unit, count):
            self.tell(f"{service} перезапущена", "Она упала, systemd запустил её снова. "
                      "Текущая работа могла прерваться.", urgent=False)
        self.restarts[unit] = count
        active = state.get("ActiveState")
        if active == "failed":
            if unit not in self.failed:
                self.failed.add(unit)
                self.tell(f"{service} не запускается",
                          "Несколько попыток подряд не удались. " + JOURNAL.format(unit=unit), urgent=True)
        else:
            self.failed.discard(unit)
        episode = self.episodes[unit]
        if active in ("inactive", "failed"):
            # Stopped or given up on: starting it is the owner's call; a later start begins anew.
            self.episodes[unit] = Episode()
        if active != "active" or not check.url:
            return
        if self.probe(check.url):
            if episode.gave_up:
                self.tell(f"{service} снова отвечает", "", urgent=False)
            elif episode.restarted:
                self.tell(f"{service} перезапущена", "Минуту не отвечала; после перезапуска работает.",
                          urgent=False)
            self.episodes[unit] = Episode()
            return
        now = self.clock()
        if now - int(state.get("ActiveEnterTimestampMonotonic") or 0) / 1e6 < check.grace:
            return  # still loading after its start: silence does not count yet
        if episode.silent_since is None:
            episode.silent_since = now
        if now - episode.silent_since < SILENT_FOR or episode.gave_up:
            return
        if not episode.restarted:
            print(f"{unit}: no answer for {now - episode.silent_since:.0f} s, restarting", flush=True)
            episode.restarted, episode.silent_since = True, None
            self.restart(unit)
        else:
            episode.gave_up = True
            self.tell(f"{service} не отвечает", "Перезапуск не помог. " + JOURNAL.format(unit=unit), urgent=True)


def show(unit):
    out = subprocess.run(["systemctl", "--user", "show", unit, "--property=ActiveState,NRestarts,"
                          "ActiveEnterTimestampMonotonic"], capture_output=True, text=True, timeout=30).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


# No proxy: a proxy left in the environment (a closed VPN client) would make every check fail.
_opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=WORK / "gateway/ca/openhands-ca.crt")))


def probe(url):
    try:
        with _opener.open(url, timeout=PROBE_TIMEOUT) as response:
            body = response.read(4096)
    except (OSError, ValueError):
        return False
    if url.endswith("/health"):
        try:
            return json.loads(body).get("ready") is True
        except ValueError:
            return False
    return True


def restart(unit):
    # A restart after systemd's own attempts could trip its start limit.
    subprocess.run(["systemctl", "--user", "reset-failed", unit], timeout=30)
    subprocess.run(["systemctl", "--user", "restart", unit], timeout=120)


def tell(title, body, urgent):
    message = f"{title}. {body}" if body else title
    print(message, flush=True)
    quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "timeout": 30}
    try:
        subprocess.run(["notify-send", "-a", "Nexus", *(["-u", "critical"] if urgent else []), title, body], **quiet)
        devices = subprocess.run(["kdeconnect-cli", "-a", "--id-only"], capture_output=True, text=True,
                                 timeout=30).stdout.split()
        for device in devices:
            subprocess.run(["kdeconnect-cli", "-d", device, "--ping-msg", message], **quiet)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"could not notify: {error}", flush=True)


def main():
    watcher = Watcher(show, probe, restart, tell)
    print("watching " + ", ".join(CHECKS), flush=True)
    while True:
        watcher.step()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
