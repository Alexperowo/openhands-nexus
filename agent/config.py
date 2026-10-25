#!/usr/bin/env python3
"""Agent settings kept in git (agent/config/): check agent-server for drift or apply them.

  python3 -I agent/config.py check   # differing keys, exit 1 on drift
  python3 -I agent/config.py apply   # LLM profiles, other settings, then the active profile

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
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def merged(common, own):
    """The profile over the common part; objects inside (litellm_extra_body) merge key by key."""
    result = dict(common)
    for key, value in own.items():
        result[key] = merged(common[key], value) \
            if isinstance(value, dict) and isinstance(common.get(key), dict) else value
    return result


def wanted():
    """Settings and profiles exactly as the files describe them."""
    settings = json.loads((CONFIG / "settings.json").read_text())
    settings["agent_settings"].setdefault("agent_context", {})["system_message_suffix"] = \
        (CONFIG / "suffix.md").read_text()
    data = json.loads((CONFIG / "profiles.json").read_text())
    profiles = {name: merged(data["common"], own) for name, own in data["profiles"].items()}
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


def apply():
    settings, profiles, active = wanted()
    for name, llm in profiles.items():
        call("POST", f"/api/profiles/{quote(name)}", {"llm": {**llm, "api_key": "not-needed"}})
    call("PATCH", "/api/settings", {"agent_settings_diff": settings["agent_settings"],
                                    "conversation_settings_diff": settings["conversation_settings"]})
    call("POST", f"/api/profiles/{quote(active)}/activate")
    print(f"Применено: {len(profiles)} профилей, активный {active}")
    return check()


if __name__ == "__main__":
    commands = {"check": check, "apply": apply}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit(__doc__)
    sys.exit(commands[sys.argv[1]]())
