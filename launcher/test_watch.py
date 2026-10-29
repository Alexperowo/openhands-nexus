"""The watcher against a fake systemd and fake services, on a fake clock."""
import http.server
import importlib
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import watch


class FakeNexus:
    """ohn-* units as systemd shows them; answers decides which services reply to a check."""
    def __init__(self):
        self.now = 1000.0
        self.units = {unit: {"ActiveState": "active", "NRestarts": "0", "ActiveEnterTimestampMonotonic": "0"}
                      for unit in watch.CHECKS}
        self.answers = {check.url: True for check in watch.CHECKS.values() if check.url}
        self.restarted, self.told = [], []
        self.watcher = watch.Watcher(self.show, self.answers.get, self.restart, self.tell, clock=lambda: self.now)

    def show(self, unit):
        return dict(self.units[unit])

    def restart(self, unit):
        self.restarted.append(unit)
        self.units[unit]["ActiveEnterTimestampMonotonic"] = str(int(self.now * 1e6))

    def tell(self, title, body, urgent):
        self.told.append((title, urgent))

    def run(self, seconds):
        end = self.now + seconds
        while self.now < end:
            self.watcher.step()
            self.now += watch.INTERVAL


VOICE = watch.CHECKS["ohn-voice"].url


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.nexus = FakeNexus()
        self.nexus.run(30)

    def test_hung_service_is_restarted_once_and_the_owner_hears_it_helped(self):
        self.nexus.answers[VOICE] = False
        self.nexus.run(watch.SILENT_FOR - watch.INTERVAL)
        self.assertEqual(self.nexus.restarted, [])
        self.nexus.run(2 * watch.INTERVAL)
        self.assertEqual(self.nexus.restarted, ["ohn-voice"])
        self.assertEqual(self.nexus.told, [])
        # Loading after the restart: silent, but not counted; the first answer is told at once.
        self.nexus.run(watch.CHECKS["ohn-voice"].grace - 2 * watch.INTERVAL)
        self.assertEqual(self.nexus.told, [])
        self.nexus.answers[VOICE] = True
        self.nexus.run(watch.INTERVAL)
        self.assertEqual(self.nexus.restarted, ["ohn-voice"])
        self.assertEqual(self.nexus.told, [("Nexus: служба «голос» перезапущена", False)])

    def test_restart_that_did_not_help_is_told_once_and_not_repeated(self):
        self.nexus.answers[VOICE] = False
        self.nexus.run(watch.SILENT_FOR + watch.CHECKS["ohn-voice"].grace + 3 * watch.SILENT_FOR)
        self.assertEqual(self.nexus.restarted, ["ohn-voice"])
        self.assertEqual(self.nexus.told, [("Nexus: служба «голос» не отвечает", True)])
        self.nexus.answers[VOICE] = True
        self.nexus.run(2 * watch.INTERVAL)
        self.assertEqual(self.nexus.told[-1], ("Nexus: служба «голос» снова отвечает", False))
        self.assertEqual(self.nexus.restarted, ["ohn-voice"])

    def test_short_silence_is_not_a_hang(self):
        self.nexus.answers[VOICE] = False
        self.nexus.run(watch.SILENT_FOR - watch.INTERVAL)
        self.nexus.answers[VOICE] = True
        self.nexus.run(watch.INTERVAL)
        self.nexus.answers[VOICE] = False
        self.nexus.run(watch.SILENT_FOR - watch.INTERVAL)
        self.assertEqual((self.nexus.restarted, self.nexus.told), ([], []))

    def test_stopped_service_is_never_started(self):
        for unit in watch.CHECKS:
            self.nexus.units[unit]["ActiveState"] = "inactive"
        self.nexus.answers = dict.fromkeys(self.nexus.answers, False)
        self.nexus.watcher.probe = self.nexus.answers.get
        self.nexus.run(10 * watch.SILENT_FOR)
        self.assertEqual((self.nexus.restarted, self.nexus.told), ([], []))

    def test_service_loading_after_its_start_is_left_alone(self):
        self.nexus.units["ohn-voice"]["ActiveEnterTimestampMonotonic"] = str(int(self.nexus.now * 1e6))
        self.nexus.answers[VOICE] = False
        self.nexus.run(watch.CHECKS["ohn-voice"].grace - watch.INTERVAL)
        self.assertEqual(self.nexus.restarted, [])

    def test_crash_and_given_up_service_are_told_once_without_a_restart(self):
        self.nexus.units["ohn-agent"]["NRestarts"] = "1"
        self.nexus.run(3 * watch.INTERVAL)
        self.assertEqual(self.nexus.told, [("Nexus: служба «агент» перезапущена", False)])
        self.nexus.units["ohn-agent"].update(ActiveState="failed", NRestarts="3")
        self.nexus.run(10 * watch.INTERVAL)
        self.assertEqual(self.nexus.told[1:], [("Nexus: служба «агент» перезапущена", False),
                                               ("Nexus: служба «агент» не запускается", True)])
        self.assertEqual(self.nexus.restarted, [])
        # The owner starts it again: a later failure is told again.
        self.nexus.units["ohn-agent"].update(ActiveState="active", NRestarts="0")
        self.nexus.run(watch.INTERVAL)
        self.nexus.units["ohn-agent"]["ActiveState"] = "failed"
        self.nexus.run(watch.INTERVAL)
        self.assertEqual(self.nexus.told[-1], ("Nexus: служба «агент» не запускается", True))

    def test_checks_go_around_a_proxy_and_voice_must_be_ready(self):
        ready = {"value": False}

        class Voice(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"status": "ok", "ready": ready["value"]}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Voice)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/health"
        # A proxy a closed VPN client left in the unit's environment: nothing listens there.
        with mock.patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:9", "no_proxy": ""}):
            probe = importlib.reload(watch).probe
        self.addCleanup(importlib.reload, watch)
        self.assertFalse(probe(url))
        ready["value"] = True
        self.assertTrue(probe(url))
        server.shutdown()
        server.server_close()
        self.assertFalse(probe(url))


FIVE, TWO = "GPU-5060", "GPU-2080"
MODELS = {"Nex-25G": "openai/nex25", "Nex-19G-2080": "openai/nex19-2080",
          "Nex-19G-5060": "openai/nex19-5060", "Tess-27B": "openai/tess"}


class FakeAgent:
    """agent-server's settings and conversations as the Cards see them through the API."""
    def __init__(self, active="Nex-25G", conversations=()):
        self.active, self.calls = active, []
        self.models = dict(conversations)
        self.updated = {c: datetime.now(timezone.utc).isoformat() for c in self.models}

    def api(self, method, path, body=None):
        if method == "POST":
            self.calls.append(path)
        if path == "/api/settings":
            return {"active_profile": self.active}
        if path.endswith("/activate"):
            self.active = path.split("/")[3]
            return {}
        if path.startswith("/api/conversations/search"):
            return {"items": [{"id": c, "agent": {"llm": {"model": m}}, "updated_at": self.updated[c]}
                              for c, m in self.models.items()]}
        if path.endswith("/switch_profile"):
            self.models[path.split("/")[3]] = MODELS[body["profile_name"]]
            return {}
        raise AssertionError(path)


class CardsTests(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp()) / "cards.json"
        self.alive = {FIVE: "RTX 5060 Ti", TWO: "RTX 2080 Ti"}
        self.agent = FakeAgent(conversations={"a": "openai/nex25", "b": "openai/tess", "c": "openai/nex19-2080",
                                              "old": "openai/nex25"})
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        self.agent.updated["old"] = week_ago.isoformat().replace("+00:00", "Z")
        self.told = []

    def cards(self):
        needs = {"Nex-25G": {FIVE, TWO}, "Tess-27B": {FIVE, TWO}, "Nex-19G-2080": {TWO}, "Nex-19G-5060": {FIVE}}
        single = {TWO: "Nex-19G-2080", FIVE: "Nex-19G-5060"}
        return watch.Cards(lambda: (MODELS, needs, single), lambda cards: dict(self.alive), self.agent.api,
                           lambda title, body, urgent: self.told.append((title, body, urgent)), self.state)

    def test_lost_card_moves_the_agent_to_the_other_and_back_after_a_reboot(self):
        cards = self.cards()
        cards.step()
        self.assertEqual((self.agent.calls, self.told), ([], []))
        del self.alive[FIVE]
        cards.step()
        cards.step()
        self.assertEqual(self.agent.active, "Nex-19G-2080")
        self.assertEqual(self.agent.models, {"a": "openai/nex19-2080", "b": "openai/nex19-2080",
                                             "c": "openai/nex19-2080", "old": "openai/nex25"})
        self.assertEqual(len(self.told), 1)
        self.assertIn("RTX 2080 Ti", self.told[0][1])
        self.assertTrue(self.told[0][2])
        self.alive[FIVE] = "RTX 5060 Ti"
        self.cards().step()  # a new watcher: the way back comes from the file
        self.assertEqual(self.agent.active, "Nex-25G")
        self.assertEqual(self.agent.models, {"a": "openai/nex25", "b": "openai/tess", "c": "openai/nex19-2080",
                                             "old": "openai/nex25"})
        self.assertFalse(self.state.exists())
        self.assertEqual(self.told[-1][2], False)

    def test_what_runs_on_the_card_that_answers_is_left_alone(self):
        self.agent = FakeAgent(active="Nex-19G-2080", conversations={"c": "openai/nex19-2080"})
        del self.alive[FIVE]
        self.cards().step()
        self.assertEqual((self.agent.calls, self.told), ([], []))
        self.assertFalse(self.state.exists())

    def test_profile_on_the_lost_card_moves_to_the_other_card(self):
        self.agent = FakeAgent(active="Nex-19G-5060")
        del self.alive[FIVE]
        self.cards().step()
        self.assertEqual(self.agent.active, "Nex-19G-2080")
        del self.alive[TWO]
        self.alive[FIVE] = "RTX 5060 Ti"
        self.cards().step()  # still a card short: the agent goes where a card answers
        self.assertEqual(self.agent.active, "Nex-19G-5060")
        self.alive[TWO] = "RTX 2080 Ti"
        self.cards().step()
        self.assertEqual(self.agent.active, "Nex-19G-5060")
        self.assertFalse(self.state.exists())

    def test_no_card_answering_is_told_once_and_nothing_moves(self):
        self.alive.clear()
        cards = self.cards()
        cards.step()
        cards.step()
        self.assertEqual(self.agent.calls, [])
        self.assertEqual(len(self.told), 1)

    def test_plan_reads_the_pinned_cards_from_llama_swap(self):
        root = Path(tempfile.mkdtemp())
        (root / "models").mkdir()
        (root / "agent/config").mkdir(parents=True)
        (root / "models/llama-swap.yaml").write_text(
            "models:\n"
            "  nex25:\n    env: &both\n      - \"CUDA_DEVICE_ORDER=PCI_BUS_ID\"\n    cmd: x\n"
            "  nex19-2080:\n    env:\n      - \"CUDA_VISIBLE_DEVICES=GPU-2080\"\n    cmd: x\n"
            "  nex19-5060:\n    env:\n      - \"CUDA_VISIBLE_DEVICES=GPU-5060\"\n    cmd: x\n"
            "  tess:\n    env: *both\n    cmd: x\n")
        (root / "agent/config/profiles.json").write_text(json.dumps(
            {"profiles": {**{p: {"model": m} for p, m in MODELS.items()}, "Cloud": {"model": "other/x"}}}))
        with mock.patch.object(watch, "WORK", root):
            models, needs, single = watch.card_plan()
        self.assertEqual(single, {TWO: "Nex-19G-2080", FIVE: "Nex-19G-5060"})
        self.assertEqual(needs["Nex-25G"], {TWO, FIVE})
        self.assertEqual(needs["Tess-27B"], {TWO, FIVE})
        self.assertNotIn("Cloud", needs)
        self.assertEqual(models["Nex-19G-5060"], "openai/nex19-5060")


if __name__ == "__main__":
    unittest.main()
