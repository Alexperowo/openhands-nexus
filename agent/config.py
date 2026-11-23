#!/usr/bin/env python3
"""Agent settings kept in git (agent/config/): check agent-server for drift or apply them.

  python3 -I agent/config.py check   # differing keys, exit 1 on drift
  python3 -I agent/config.py apply   # LLM profiles, other settings, then the active profile
  python3 -I agent/config.py sync-optional   # reconcile optional profiles on agent startup
  python3 -I agent/config.py optional-model-dir   # llama-swap's optional configuration directory

The files hold only what differs from OpenHands defaults; apply leaves everything else as
it is. It talks to agent-server directly with the session key and never prints a value of
a key: local models get the placeholder "not-needed", other providers are not managed here.
"""
import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlsplit

SERVER = "http://127.0.0.1:18010"
SESSION_ENV = Path.home() / ".config/openhands-nexus/session.env"
CONFIG = Path(__file__).resolve().parent / "config"
MODELS = CONFIG.parent.parent / "models"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def session_key():
    for line in SESSION_ENV.read_text().splitlines():
        if line.startswith("OHN_SESSION_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"OHN_SESSION_KEY не найден в {SESSION_ENV}")


def call(method, path, body=None):
    request = urllib.request.Request(
        SERVER + path, method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"X-Session-API-Key": session_key(), "Content-Type": "application/json"})
    # agent-server is on this PC: never through the system proxy (Happ answered 503 for it).
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=30) as response:
        return json.load(response)


def merged(common, own):
    """The profile over the common part; objects inside (litellm_extra_body) merge key by key."""
    result = dict(common)
    for key, value in own.items():
        result[key] = merged(common[key], value) \
            if isinstance(value, dict) and isinstance(common.get(key), dict) else value
    return result


def profile_data():
    return json.loads((CONFIG / "profiles.json").read_text())


def optional_weight_ready(spec):
    path = MODELS / "weights" / spec["weight"]
    try:
        if not path.is_file() or path.stat().st_size != spec["size"]:
            return False
        with path.open("rb") as model:
            return model.read(4) == b"GGUF"
    except OSError:
        return False


def optional_model_dir():
    if optional_weight_ready(profile_data()["optional"]["Holo4-MTP-27B"]):
        print(MODELS / "optional/holo-mtp")
    return 0


def wanted():
    """Settings and profiles exactly as the files describe them."""
    settings = json.loads((CONFIG / "settings.json").read_text())
    settings["agent_settings"].setdefault("agent_context", {})["system_message_suffix"] = \
        (CONFIG / "suffix.md").read_text()
    data = profile_data()
    optional = data.get("optional", {})
    profiles = {name: merged(data["common"], own) for name, own in data["profiles"].items()
                if name not in optional or optional_weight_ready(optional[name])}
    for name, llm in profiles.items():
        if urlsplit(llm["base_url"]).hostname not in LOCAL_HOSTS:
            raise SystemExit(f"Профиль {name}: внешний провайдер, его ключ этим скриптом не задаётся")
    if data["active"] not in profiles:
        raise SystemExit(f"Активный профиль {data['active']} не описан")
    return settings, profiles, data["active"]


def differences(expected, actual, prefix=""):
    """Keys of expected whose values differ in actual (values are never shown)."""
    found = []
    for key, value in expected.items():
        here = actual.get(key) if isinstance(actual, dict) else None
        if isinstance(value, dict) and isinstance(here, dict):
            found += differences(value, here, f"{prefix}{key}.")
        elif value != here:
            found.append(prefix + key)
    return found


def check():
    settings, profiles, active = wanted()
    current = call("GET", "/api/settings")
    drift = [f"settings: {key}" for section in ("agent_settings", "conversation_settings")
             for key in differences(settings[section], current.get(section, {}), f"{section}.")]
    stored = {item["name"] for item in call("GET", "/api/profiles")["profiles"]}
    drift += [f"профиль {name}: нет на сервере" for name in profiles.keys() - stored]
    drift += [f"профиль {name}: нет в git" for name in stored - profiles.keys()]
    for name in profiles.keys() & stored:
        config = call("GET", f"/api/profiles/{quote(name)}")["config"]
        drift += [f"профиль {name}: {key}" for key in differences(profiles[name], config)]
    if current.get("active_profile") != active:
        drift.append(f"активный профиль: {current.get('active_profile')} вместо {active}")
    # Activation copies the profile into the settings; an edit there is not saved anywhere else.
    drift += [f"settings: agent_settings.llm.{key} (не совпадает с {active})"
              for key in differences(profiles[active], current["agent_settings"].get("llm", {}))]
    print("\n".join(drift) or "Настройки агента совпадают с git")
    return 1 if drift else 0


def save_profile(name, llm):
    call("POST", f"/api/profiles/{quote(name)}", {"llm": {**llm, "api_key": "not-needed"}})


def sync_optional():
    data = profile_data()
    optional = data.get("optional", {})
    if not optional:
        return 0
    current = call("GET", "/api/profiles")
    stored = {item["name"]: item for item in current["profiles"]}
    for name, spec in optional.items():
        llm = merged(data["common"], data["profiles"][name])
        path = f"/api/profiles/{quote(name)}"
        if optional_weight_ready(spec):
            if name not in stored or differences(llm, call("GET", path)["config"]):
                save_profile(name, llm)
        elif name in stored and stored[name].get("model") == llm["model"]:
            if current.get("active_profile") == name:
                fallback = spec["fallback"]
                if fallback not in stored:
                    save_profile(fallback, merged(data["common"], data["profiles"][fallback]))
                call("POST", f"/api/profiles/{quote(fallback)}/activate")
            call("DELETE", path)
    return 0


def apply():
    settings, profiles, active = wanted()
    for name, llm in profiles.items():
        save_profile(name, llm)
    call("PATCH", "/api/settings", {"agent_settings_diff": settings["agent_settings"],
                                    "conversation_settings_diff": settings["conversation_settings"]})
    call("POST", f"/api/profiles/{quote(active)}/activate")
    sync_optional()
    print(f"Применено: {len(profiles)} профилей, активный {active}")
    return check()


if __name__ == "__main__":
    commands = {"check": check, "apply": apply, "sync-optional": sync_optional,
                "optional-model-dir": optional_model_dir}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit(__doc__)
    sys.exit(commands[sys.argv[1]]())
