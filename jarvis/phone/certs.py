"""HTTPS certificates for the phone connection, made on this computer.

Jarvis creates its own small certificate authority (CA) once, and uses it to
sign a certificate for this computer's network addresses. Traffic between the
phone and the computer is then encrypted. Because no public authority signed
it, the phone warns the first time; installing the CA certificate on the phone
(optional) removes the warning. No certificate service on the internet is used.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

SERVER_CERT_DAYS = 397  # phones reject longer-lived server certificates
RENEW_BEFORE_DAYS = 30


@dataclass
class CertInfo:
    certfile: Path
    keyfile: Path
    ca_certfile: Path
    fingerprint: str
    ca_fingerprint: str


def lan_addresses() -> list[str]:
    """This computer's private network (IPv4) addresses, most likely first.

    Connecting a UDP socket sends no packets; it only asks the OS which
    interface it would use, so this makes no network request.
    """
    found: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        found += [info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass
    result = []
    for ip in found:
        addr = ipaddress.ip_address(ip)
        if addr.is_private and not addr.is_loopback and not addr.is_link_local and ip not in result:
            result.append(ip)
    return result


def _fingerprint(cert: x509.Certificate) -> str:
    return cert.fingerprint(hashes.SHA256()).hex(":").upper()


def _write_key(path: Path, key) -> None:
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    if os.name != "nt":
        os.chmod(path, 0o600)


def _load_or_create_ca(folder: Path, hostname: str) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    cert_path, key_path = folder / "jarvis-ca.crt", folder / "jarvis-ca.key"
    if cert_path.exists() and key_path.exists():
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        if cert.not_valid_after_utc > dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=RENEW_BEFORE_DAYS):
            return cert, key
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"Jarvis local CA ({hostname})"[:64]),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Jarvis on this computer only"),
    ])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_key(key_path, key)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert, key


def ensure_certificates(folder: Path, hostname: str, ips: list[str]) -> CertInfo:
    """Return a valid server certificate for `ips`, creating or renewing it as needed."""
    folder.mkdir(parents=True, exist_ok=True)
    ca_cert, ca_key = _load_or_create_ca(folder, hostname)
    cert_path, key_path, meta_path = folder / "server.crt", folder / "server.key", folder / "server.json"
    wanted = sorted({*ips, "127.0.0.1"})
    names = sorted({hostname, f"{hostname}.local", "localhost"} if hostname else {"localhost"})
    if cert_path.exists() and key_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
            fresh = cert.not_valid_after_utc > dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=RENEW_BEFORE_DAYS)
            signed_by_ca = cert.issuer == ca_cert.subject
            if fresh and signed_by_ca and set(wanted) <= set(meta.get("ips", [])) and meta.get("names") == names:
                return CertInfo(cert_path, key_path, folder / "jarvis-ca.crt", _fingerprint(cert), _fingerprint(ca_cert))
        except (ValueError, OSError):
            pass  # unreadable: make a new one
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.timezone.utc)
    san = [x509.DNSName(n) for n in names] + [x509.IPAddress(ipaddress.ip_address(ip)) for ip in wanted]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, (hostname or "jarvis")[:64])]))
        .issuer_name(ca_cert.subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=SERVER_CERT_DAYS))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=False, crl_sign=False,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    _write_key(key_path, key)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    meta_path.write_text(json.dumps({"ips": wanted, "names": names}))
    return CertInfo(cert_path, key_path, folder / "jarvis-ca.crt", _fingerprint(cert), _fingerprint(ca_cert))
