"""
Integration tests for Voice Bridge and Working Profiles HTTP API.
Port: 127.0.0.1:18002
"""

import json
import urllib.request
import pytest


class TestVoiceBridgeApi:
    """Verifies Voice Bridge endpoints on port 18002."""

    BASE_URL = "http://127.0.0.1:18002"

    def test_voice_bridge_health(self):
        url = f"{self.BASE_URL}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "ok"
            assert "gigaam" in data["stt_engine"].lower()
            assert "supertonic" in data["tts_engine"].lower()
            assert "voices" in data
            assert len(data["voices"]) > 0

    def test_working_profiles_endpoint(self):
        url = f"{self.BASE_URL}/api/working-profiles"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "profiles" in data
            assert "state" in data
            assert len(data["profiles"]) >= 7
            active_id = data["state"].get("active_working_profile_id") or data["state"].get("active_profile_id")
            assert active_id is not None

    def test_static_assets_served(self):
        for asset in ["/voice-bridge.js", "/voice-bridge.css", "/working-profile-ui.js"]:
            url = f"{self.BASE_URL}{asset}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                assert resp.status == 200
                content = resp.read()
                assert len(content) > 100
