#!/usr/bin/env python3
"""
OpenHands Local LAN PWA - CA & Certificate Generator
Generates:
1. Root CA: CN=OpenHands Local Root CA (BasicConstraints: CA=True, KeyCertSign, CrlSign)
2. Leaf Cert: CN=DESKTOP-L0FBHL4 signed by Root CA (BasicConstraints: CA=False, ServerAuth, SANs)
3. PFX Bundle: openhands-lan.pfx (leaf key + leaf cert + CA chain)
4. LAN Auth Token: lan-auth-token.txt (persistent 32-char hex secret for gateway auth boundary)
"""

import datetime
import ipaddress
import os
import secrets
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

PWA_DIR = Path(__file__).resolve().parent
CERT_DIR = PWA_DIR / "certs"
CERT_DIR.mkdir(parents=True, exist_ok=True)

CA_KEY_FILE = CERT_DIR / "openhands-ca.key"
CA_CRT_FILE = CERT_DIR / "openhands-ca.crt"
LEAF_KEY_FILE = CERT_DIR / "openhands-lan.key"
LEAF_CRT_FILE = CERT_DIR / "openhands-lan.crt"
LEAF_PFX_FILE = CERT_DIR / "openhands-lan.pfx"
AUTH_TOKEN_FILE = CERT_DIR / "lan-auth-token.txt"

# 1. LAN Auth Token
if not AUTH_TOKEN_FILE.exists():
    token = secrets.token_hex(16)
    AUTH_TOKEN_FILE.write_text(token.strip(), encoding="utf-8")
    print(f"[AUTH] Generated new persistent LAN Auth Token in: {AUTH_TOKEN_FILE.name}")
else:
    token = AUTH_TOKEN_FILE.read_text(encoding="utf-8").strip()
    print(f"[AUTH] Using existing LAN Auth Token from: {AUTH_TOKEN_FILE.name}")

# 2. Hostname and Dynamic LAN IP Detection
def get_local_lan_ip() -> str:
    env_ip = os.environ.get("OPENHANDS_LAN_IP", "").strip()
    if env_ip:
        return env_ip
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1.0)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        host_ip = socket.gethostbyname(socket.gethostname())
        if host_ip and not host_ip.startswith("127."):
            return host_ip
    except Exception:
        pass
    return "192.168.0.14"

hostname = os.environ.get("COMPUTERNAME", "DESKTOP-L0FBHL4")
lan_ip = get_local_lan_ip()

print(f"[CERT] Target Hostname: {hostname}")
print(f"[CERT] Target LAN IP:   {lan_ip}")

# 3. Root CA
now = datetime.datetime.now(datetime.timezone.utc)
if CA_KEY_FILE.exists() and CA_CRT_FILE.exists():
    print("[CA] Loading existing Root CA key and certificate...")
    ca_key = serialization.load_pem_private_key(CA_KEY_FILE.read_bytes(), password=None)
    ca_cert = x509.load_pem_x509_certificate(CA_CRT_FILE.read_bytes())
else:
    print("[CA] Generating new Root CA (2048-bit RSA, CA=True)...")
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "OpenHands Local Root CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OpenHands Local Station")
    ])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=365 * 10))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False
            ),
            critical=True
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    CA_KEY_FILE.write_bytes(ca_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ))
    CA_CRT_FILE.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    print(f"[OK] Root CA exported: {CA_CRT_FILE.name}")

# 4. Leaf Certificate signed by Root CA
print(f"[LEAF] Generating Leaf Certificate for {hostname} signed by Root CA...")
leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
leaf_name = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, hostname)
])
san_ips = {ipaddress.IPv4Address("127.0.0.1"), ipaddress.IPv4Address(lan_ip)}
try:
    san_ips.add(ipaddress.IPv4Address("192.168.0.14"))
except Exception:
    pass

san_list = [
    x509.DNSName(hostname),
    x509.DNSName("localhost")
] + [x509.IPAddress(ip) for ip in sorted(san_ips, key=lambda x: str(x))]
leaf_cert = (
    x509.CertificateBuilder()
    .subject_name(leaf_name)
    .issuer_name(ca_cert.subject)
    .public_key(leaf_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - datetime.timedelta(minutes=5))
    .not_valid_after(now + datetime.timedelta(days=365 * 3))
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=True,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False
        ),
        critical=True
    )
    .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
    .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
    .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
    .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False)
    .sign(ca_key, hashes.SHA256())
)

LEAF_KEY_FILE.write_bytes(leaf_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption()
))
LEAF_CRT_FILE.write_bytes(leaf_cert.public_bytes(serialization.Encoding.PEM))

# 5. Export PFX with Leaf Key, Leaf Cert, and CA Cert Chain
pfx_data = pkcs12.serialize_key_and_certificates(
    b"openhands-lan",
    leaf_key,
    leaf_cert,
    [ca_cert],
    serialization.BestAvailableEncryption(b"openhands-pwa-local")
)
LEAF_PFX_FILE.write_bytes(pfx_data)

# Print Summary & Truth
ca_bc = ca_cert.extensions.get_extension_for_class(x509.BasicConstraints).value
leaf_bc = leaf_cert.extensions.get_extension_for_class(x509.BasicConstraints).value

print("\n=====================================================================")
print("             CERTIFICATE & TRUST SPECIFICATIONS")
print("=====================================================================")
print(f"ROOT CA SUBJECT:          {ca_cert.subject.rfc4514_string()}")
print(f"ROOT CA ISSUER:           {ca_cert.issuer.rfc4514_string()}")
print(f"ROOT CA IS_CA:            {ca_bc.ca} (PathLen: {ca_bc.path_length})")
print(f"ROOT CA PUBLIC FILE:      {CA_CRT_FILE}")
print("---------------------------------------------------------------------")
print(f"LEAF SUBJECT:             {leaf_cert.subject.rfc4514_string()}")
print(f"LEAF ISSUER:              {leaf_cert.issuer.rfc4514_string()}")
print(f"LEAF SELF_SIGNED:         {leaf_cert.subject == leaf_cert.issuer}")
print(f"LEAF IS_CA:               {leaf_bc.ca}")
print(f"LEAF SANs:                {[str(san.value) for san in leaf_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value]}")
print(f"LEAF PFX FILE:            {LEAF_PFX_FILE}")
print("=====================================================================\n")
