"""The watcher against a fake systemd and fake services, on a fake clock."""
import http.server
import importlib
import json
import os
import threading
import unittest
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

if __name__ == "__main__":
    unittest.main()
