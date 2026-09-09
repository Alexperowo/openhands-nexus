"""
Integration tests verifying health and HTTP responses of all OpenHands Nexus services.
Requires services to be active (openhands start).
"""

import urllib.request
import urllib.error
import ssl
import json
import pytest

# Ignore SSL verification for local self-signed LAN gateway testing
SSL_UNVERIFIED_CTX = ssl.create_default_context()
SSL_UNVERIFIED_CTX.check_hostname = False
SSL_UNVERIFIED_CTX.verify_mode = ssl.CERT_NONE


class TestServicesHealth:
    """Verifies all 5 core platform services are listening and responding."""

    def test_core_engine_health(self):
        """OpenHands Core Agent Server on port 18000."""
        req = urllib.request.Request("http://127.0.0.1:18000")
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200, f"Core Server returned {resp.status}"

    def test_agent_canvas_health(self):
        """Agent Canvas Web UI on port 8000."""
        req = urllib.request.Request("http://127.0.0.1:8000")
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200, f"Agent Canvas returned {resp.status}"

    def test_llama_swap_health(self):
        """llama-swap Model Router on port 8080."""
        req = urllib.request.Request("http://127.0.0.1:8080/v1/models")
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200, f"llama-swap returned {resp.status}"
            data = json.loads(resp.read().decode("utf-8"))
            assert "data" in data
            model_ids = [m["id"] for m in data["data"]]
            assert "qwen" in model_ids or "ornith" in model_ids or "next" in model_ids

    def test_voice_bridge_health(self):
        """Local Voice Bridge on port 18002."""
        req = urllib.request.Request("http://127.0.0.1:18002/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200, f"Voice Bridge returned {resp.status}"
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("status") == "ok"

    def test_lan_gateway_health(self):
        """HTTPS LAN Gateway on port 8443."""
        # Using 127.0.0.1:8443 or dynamic LAN IP
        try:
            req = urllib.request.Request("https://127.0.0.1:8443")
            with urllib.request.urlopen(req, context=SSL_UNVERIFIED_CTX, timeout=3) as resp:
                assert resp.status == 200
        except urllib.error.URLError:
            req = urllib.request.Request("https://192.168.0.14:8443")
            with urllib.request.urlopen(req, context=SSL_UNVERIFIED_CTX, timeout=3) as resp:
                assert resp.status == 200
