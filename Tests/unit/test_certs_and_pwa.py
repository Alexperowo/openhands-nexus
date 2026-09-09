"""
Unit tests for X.509 certificates and PWA manifest integrity.
Hardware-independent: runs in < 1 second without GPU.
"""

import json
from pathlib import Path
import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestPwaManifest:
    """Validates Progressive Web App manifest for desktop and tablet."""

    @pytest.fixture(autouse=True)
    def setup(self):
        m_web = PROJECT_ROOT / "openhands-pwa" / "manifest.webmanifest"
        m_json = PROJECT_ROOT / "openhands-pwa" / "manifest.json"
        self.manifest_path = m_web if m_web.exists() else m_json
        assert self.manifest_path.exists(), f"Missing manifest: {self.manifest_path}"
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)

    def test_pwa_fields(self):
        assert self.manifest.get("display") == "standalone"
        assert "name" in self.manifest
        assert "short_name" in self.manifest
        assert "start_url" in self.manifest
        assert "icons" in self.manifest
        assert len(self.manifest["icons"]) > 0


class TestX509Certificates:
    """Validates local TLS certificates and PKI generation."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.cert_dir = PROJECT_ROOT / "openhands-pwa" / "certs"
        assert self.cert_dir.exists(), f"Missing cert dir: {self.cert_dir}"
        self.ca_crt = self.cert_dir / "openhands-ca.crt"
        self.leaf_crt = self.cert_dir / "openhands-lan.crt"
        self.token_file = self.cert_dir / "lan-auth-token.txt"

    def test_auth_token_format(self):
        assert self.token_file.exists(), "lan-auth-token.txt missing"
        token = self.token_file.read_text(encoding="utf-8").strip()
        assert len(token) == 32, f"Auth token must be 32 hex chars, got {len(token)}"
        int(token, 16)  # Must be valid hex

    def test_root_ca_certificate(self):
        assert self.ca_crt.exists(), "openhands-ca.crt missing"
        cert_bytes = self.ca_crt.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_bytes, default_backend())
        # Check CA constraint
        bc = cert.extensions.get_extension_for_oid(x509.ExtensionOID.BASIC_CONSTRAINTS).value
        assert bc.ca is True, "Root certificate must have CA=True"

    def test_leaf_certificate_san(self):
        assert self.leaf_crt.exists(), "openhands-lan.crt missing"
        cert_bytes = self.leaf_crt.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_bytes, default_backend())
        san = cert.extensions.get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
        dns_names = [n.value for n in san if isinstance(n, x509.DNSName)]
        ip_addresses = [str(ip.value) for ip in san if isinstance(ip, x509.IPAddress)]
        assert "localhost" in dns_names
        assert "127.0.0.1" in ip_addresses
        # Ensure at least one LAN IP is present
        assert any(ip.startswith("192.168.") or ip.startswith("10.") for ip in ip_addresses), (
            f"No LAN IP found in SANs: {ip_addresses}"
        )
