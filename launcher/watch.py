#!/usr/bin/env python3
"""Watcher of the Nexus services, outside the agent (ohn-watch.service, part of ohn.target).

systemd restarts a service whose process exits, not one that hangs while running, and the agent
cannot be trusted to restore its own ground. Every 15 s this asks each running service whether it
answers. One silent for a minute is restarted once; the owner is then told on the PC and the
tablet whether that helped. Crashes systemd restarted and services it gave up on are told too.

A stopped service is never started, and none is restarted for working long: the checks are
answered while a model computes (voice /health is async, llama-swap and Caddy answer alongside).

While the models run it also looks after the video cards (Cards): with one gone, the agent moves
to the model pinned to a card that still answers, and back once every card answers again.
"""
import importlib.util
import json
import ssl
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

WORK = Path(__file__).resolve().parent.parent
INTERVAL = 15
PROBE_TIMEOUT = 5
SILENT_FOR = 60
CARD_ROUNDS = 4  # the cards are asked every 4th round (1 min) and right after the models start
CARDS_STATE = Path.home() / ".local/state/openhands-nexus/cards.json"
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


class Cards:
    """Keeps the agent on models whose cards answer.

    plan() gives each agent profile its model and the cards that model needs, and each card the
    profile pinned to it alone. With a card gone, the active profile and the open conversations
    that need it move to the profile of a card that answers; once every card is back, what was
    moved returns. The way back is kept in a file, so a restart or a reboot in between keeps it.
    """
    def __init__(self, plan, answering, api, tell, state=CARDS_STATE):
        self.plan, self.answering, self.api, self.tell, self.state = plan, answering, api, tell, state
        self.told_dead = False

    def step(self):
        models, needs, single = self.plan()
        if not single:
            return
        alive = self.answering(list(single))
        saved = json.loads(self.state.read_text()) if self.state.exists() else {}
        if alive.keys() >= single.keys():
            self.told_dead = False
            if saved:
                self.restore(saved, models, single)
            return
        if not alive:
            if not self.told_dead:
                self.told_dead = True
                self.tell("Nexus: видеокарты не отвечают", "Модели работать не смогут. " + JOURNAL.format(
                    unit="ohn-models"), urgent=True)
            return
        self.told_dead = False
        target = next(single[card] for card in single if card in alive)
        works = lambda profile: needs.get(profile, set()) <= alive.keys()
        moved = False
        active = self.api("GET", "/api/settings").get("active_profile")
        if not works(active):
            saved.setdefault("active", active)
            self.api("POST", f"/api/profiles/{quote(target)}/activate")
            self.save(saved)
            moved = True
        by_model = {model: profile for profile, model in models.items()}
        for conversation in self.conversations():
            profile = by_model.get(conversation["agent"]["llm"]["model"])
            if profile is not None and not works(profile):
                saved.setdefault("moved", {}).setdefault(conversation["id"], profile)
                self.switch(conversation["id"], target)
                self.save(saved)
                moved = True
        if moved:
            self.tell("Nexus: видеокарта не отвечает", f"Работает только {', '.join(alive.values())}: агент "
                      f"переведён на модель для неё ({target}). Когда карта вернётся, переведу обратно.", urgent=True)

    def restore(self, saved, models, single):
        fallback = {models[profile] for profile in single.values()}
        if "active" in saved and self.api("GET", "/api/settings").get("active_profile") in single.values():
            self.api("POST", f"/api/profiles/{quote(saved['active'])}/activate")
        moved = saved.get("moved", {})
        for conversation in self.conversations():
            if conversation["id"] in moved and conversation["agent"]["llm"]["model"] in fallback:
                self.switch(conversation["id"], moved[conversation["id"]])
        self.state.unlink()
        self.tell("Nexus: видеокарты снова работают", f"Агент вернулся к {saved.get('active') or 'прежним моделям'}.",
                  urgent=False)

    def conversations(self):
        return self.api("GET", "/api/conversations/search?limit=100")["items"]

    def switch(self, conversation, profile):
        self.api("POST", f"/api/conversations/{conversation}/switch_profile", {"profile_name": profile})

    def save(self, saved):
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self.state.write_text(json.dumps(saved))


def card_plan():
    """Profile -> model, profile -> the cards it needs, card -> the profile pinned to it alone.

    A model pinned to one card names it by UUID (CUDA_VISIBLE_DEVICES=GPU-… in llama-swap.yaml);
    any other model served there needs every such card; a model not served there needs none."""
    import yaml  # here: without it only the cards go unwatched
    served = yaml.safe_load((WORK / "models/llama-swap.yaml").read_text())["models"]
    pinned = {}
    for name, model in served.items():
        for item in model.get("env") or []:
            key, _, value = item.partition("=")
            if key == "CUDA_VISIBLE_DEVICES" and value.startswith("GPU-") and "," not in value:
                pinned[name] = value
    profiles = json.loads((WORK / "agent/config/profiles.json").read_text())["profiles"]
    models = {profile: llm["model"] for profile, llm in profiles.items()}
    needs, single = {}, {}
    for profile, model in models.items():
        name = model.removeprefix("openai/")
        if name in pinned:
            needs[profile] = {pinned[name]}
            single.setdefault(pinned[name], profile)
        elif name in served:
            needs[profile] = set(pinned.values())
    return models, needs, single


def answering(cards):
    """{UUID: name} of the cards nvidia-smi still reaches; one that fell off the bus fails or hangs."""
    alive = {}
    for card in cards:
        try:
            out = subprocess.run(["nvidia-smi", "-i", card, "--query-gpu=uuid,name", "--format=csv,noheader"],
                                 capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        uuid, _, name = out.strip().partition(", ")
        if uuid == card:
            alive[card] = name.removeprefix("NVIDIA GeForce ")
    return alive


def agent_api(method, path, body=None):
    spec = importlib.util.spec_from_file_location("agent_config", WORK / "agent/config.py")
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    return config.call(method, path, body)


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
    cards = Cards(card_plan, answering, agent_api, tell)
    print("watching " + ", ".join(CHECKS) + " and the video cards", flush=True)
    rounds, models_were = 0, None
    while True:
        watcher.step()
        models = show("ohn-models").get("ActiveState")
        if models == "active" and (rounds % CARD_ROUNDS == 0 or models_were != "active"):
            try:
                cards.step()
            except Exception as error:  # the agent may be restarting: the next round tries again
                print(f"card check: {error!r}", flush=True)
        rounds, models_were = rounds + 1, models
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
