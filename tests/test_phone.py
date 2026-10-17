"""Phone access: pairing, certificates, the phone allow-list, and the real HTTPS listener."""

from __future__ import annotations

import asyncio
import datetime as dt
import ipaddress
import socket
import ssl
import time

import httpx
import pytest
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID
from fastapi.testclient import TestClient

from jarvis.activity import ActivityLog
from jarvis.db import Database
from jarvis.phone import PhoneChannel
from jarvis.phone.certs import ensure_certificates
from jarvis.phone.devices import CODE_MAX_ATTEMPTS, DeviceRegistry, PairingError
from jarvis.server import create_app
from tests.conftest import FakeProvider

TOKEN = "desk-token"


def make_app(data_dir, provider=None):
    provider = provider or FakeProvider()
    app = create_app(data_dir, token=TOKEN, provider_factory=lambda s: provider, restore_last_project=False,
                     phone_host="127.0.0.1")
    return app, provider


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------ pairing
@pytest.fixture
def registry(data_dir):
    db = Database(data_dir / "jarvis.db")
    return DeviceRegistry(db, ActivityLog(db))


def test_pairing_code_is_single_use(registry):
    code = registry.new_code()["code"]
    device, token = registry.pair(code, "  My   Pixel ", "10.0.0.2")
    assert device["name"] == "My Pixel" and len(token) > 30
    assert registry.verify(token)["id"] == device["id"]
    with pytest.raises(PairingError, match="no active pairing code"):
        registry.pair(code, "Again", "10.0.0.2")


def test_wrong_codes_burn_the_code(registry):
    code = registry.new_code()["code"]
    wrong = "000000" if code != "000000" else "111111"
    for i in range(CODE_MAX_ATTEMPTS - 1):
        with pytest.raises(PairingError, match="isn't right"):
            registry.pair(wrong, "x", "10.0.0.3")
    with pytest.raises(PairingError, match="too many times"):
        registry.pair(wrong, "x", "10.0.0.3")
    with pytest.raises(PairingError, match="no active"):
        registry.pair(code, "x", "10.0.0.3")  # even the right code is now useless


def test_codes_expire_and_clients_are_rate_limited(registry, monkeypatch):
    code = registry.new_code()["code"]
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 301)
    with pytest.raises(PairingError, match="no active"):
        registry.pair(code, "x", "10.0.0.4")
    monkeypatch.setattr(time, "time", real)
    for _ in range(10):  # PAIR_RATE_LIMIT attempts are allowed...
        registry.new_code()
        with pytest.raises(PairingError):
            registry.pair("abc", "x", "10.0.0.9")
    registry.new_code()  # ...the next one is refused even with a fresh code
    with pytest.raises(PairingError) as exc:
        registry.pair("abc", "x", "10.0.0.9")
    assert exc.value.status == 429


def test_revoked_devices_lose_access(registry):
    device, token = registry.pair(registry.new_code()["code"], "Phone", "10.0.0.5")
    assert [d["id"] for d in registry.list()] == [device["id"]]
    registry.revoke(device["id"])
    assert registry.verify(token) is None and registry.list() == []
    assert registry.verify("") is None and registry.verify("made-up") is None


# ------------------------------------------------------------------ certificates
def test_certificates_are_valid_and_reused(tmp_path):
    folder = tmp_path / "phone"
    info = ensure_certificates(folder, "study-laptop", ["192.168.1.23"])
    cert = x509.load_pem_x509_certificate(info.certfile.read_bytes())
    ca = x509.load_pem_x509_certificate(info.ca_certfile.read_bytes())
    cert.verify_directly_issued_by(ca)
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert {str(ip) for ip in san.get_values_for_type(x509.IPAddress)} == {"192.168.1.23", "127.0.0.1"}
    assert {"study-laptop", "study-laptop.local"} <= {n.lower() for n in san.get_values_for_type(x509.DNSName)}
    assert ExtendedKeyUsageOID.SERVER_AUTH in cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert cert.not_valid_after_utc - cert.not_valid_before_utc <= dt.timedelta(days=398)
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    # Same addresses: same certificate. New address: new server cert, same CA (phones keep trusting it).
    assert ensure_certificates(folder, "study-laptop", ["192.168.1.23"]).fingerprint == info.fingerprint
    moved = ensure_certificates(folder, "study-laptop", ["10.0.0.7"])
    assert moved.fingerprint != info.fingerprint and moved.ca_fingerprint == info.ca_fingerprint
    new_san = x509.load_pem_x509_certificate(moved.certfile.read_bytes()).extensions.get_extension_for_class(
        x509.SubjectAlternativeName).value
    assert ipaddress.ip_address("10.0.0.7") in new_san.get_values_for_type(x509.IPAddress)


# ------------------------------------------------------------------ phone rules (no network)
def phone_client(app):
    return TestClient(PhoneChannel(app), base_url="https://192.168.1.20:8766")


def pair(app, client, name="Test Phone"):
    code = app.state.devices.new_code()["code"]
    r = client.post("/api/phone/pair", json={"code": code, "name": name})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_phone_pages_and_redirect(data_dir):
    app, _ = make_app(data_dir)
    with phone_client(app) as phone:
        r = phone.get("/", follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == "/m/"
        page = phone.get("/m/")
        assert page.status_code == 200 and "/static/mobile.js?v=" in page.text and "{{" not in page.text
        assert "JARVIS_TOKEN" not in page.text and TOKEN not in page.text
        assert phone.get("/m/manifest.webmanifest").json()["start_url"] == "/m/"
        sw = phone.get("/m/sw.js")
        assert sw.status_code == 200 and "{{VERSION}}" not in sw.text
        assert phone.get("/static/mobile.css").status_code == 200


def test_phone_needs_pairing_and_desktop_token_does_not_work(data_dir):
    app, _ = make_app(data_dir)
    with phone_client(app) as phone:
        r = phone.get("/api/tasks")
        assert r.status_code == 401 and r.json()["code"] == "unpaired"
        assert phone.get("/api/tasks", headers={"X-Jarvis-Token": TOKEN}).status_code == 401
        assert phone.get("/api/tasks", headers={"Authorization": "Bearer nope"}).status_code == 401
        assert phone.post("/api/phone/pair", json={"code": "123456"}).status_code == 400  # no code active
        auth = pair(app, phone)
        assert phone.get("/api/tasks", headers=auth).status_code == 200
        who = phone.get("/api/phone/whoami", headers=auth).json()
        assert who["device"]["name"] == "Test Phone"


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/commands/run"), ("POST", "/api/commands/check"), ("PUT", "/api/settings"),
    ("GET", "/api/settings"), ("POST", "/api/changes"), ("POST", "/api/changes/1/apply"),
    ("POST", "/api/project/open"), ("POST", "/api/project/pick"), ("GET", "/api/project/file"),
    ("GET", "/api/project/tree"), ("GET", "/api/project/search"), ("GET", "/api/activity"),
    ("GET", "/api/phone"), ("POST", "/api/phone/pairing-code"), ("DELETE", "/api/phone/devices/1"),
    ("GET", "/api/tasks/export"), ("GET", "/static/../jarvis.db"),
])
def test_phone_cannot_reach_computer_only_features(data_dir, method, path):
    app, _ = make_app(data_dir)
    with phone_client(app) as phone:
        auth = pair(app, phone)
        r = phone.request(method, path, headers=auth, json={})
        assert r.status_code in (403, 404), (path, r.status_code)


def test_phone_host_and_origin_checks(data_dir):
    app, _ = make_app(data_dir)
    with phone_client(app) as phone:
        auth = pair(app, phone)
        assert phone.get("/api/status", headers={**auth, "Host": "evil.example.com"}).status_code == 403
        assert phone.get("/api/status", headers={**auth, "Origin": "https://evil.example.com"}).status_code == 403
        ok = phone.get("/api/status", headers={**auth, "Origin": "https://192.168.1.20:8766"})
        assert ok.status_code == 200
        host = socket.gethostname()
        assert phone.get("/api/status", headers={**auth, "Host": f"{host}.local:8766"}).status_code == 200


def test_phone_actions_are_logged_and_attachments_ignored(data_dir, project):
    app, provider = make_app(data_dir)
    with TestClient(app) as desk, phone_client(app) as phone:
        desk_h = {"X-Jarvis-Token": TOKEN}
        desk.post("/api/project/open", json={"path": str(project)}, headers=desk_h)
        app.state.projects.wait_for_index()
        auth = pair(app, phone, "Pixel")
        task = phone.post("/api/tasks", json={"title": "From my phone"}, headers=auth).json()
        with phone.stream("POST", "/api/chat", headers=auth, json={
                "message": "hello", "attached": ["config.py"], "use_project": False, "stream_id": "p1"}) as resp:
            events = [line for line in resp.iter_lines() if line]
        assert '"done"' in events[-1]
        assert "hunter2" not in provider.calls[0][0][-1]["content"] and "config.py" not in provider.calls[0][0][-1]["content"]
        summaries = [a["summary"] for a in desk.get("/api/activity", headers=desk_h).json()]
        assert any("From my phone" in s and "(from phone 'Pixel')" in s for s in summaries)
        assert any("Paired phone 'Pixel'" in s for s in summaries)
        # The computer sees and can remove the phone; the phone is then locked out.
        devices = desk.get("/api/phone", headers=desk_h).json()["devices"]
        assert [d["name"] for d in devices] == ["Pixel"]
        desk.delete(f"/api/phone/devices/{devices[0]['id']}", headers=desk_h)
        assert phone.get(f"/api/tasks/{task['id']}", headers=auth).status_code in (401, 403, 405)
        assert phone.get("/api/tasks", headers=auth).status_code == 401
        # Pairing is not possible through the computer's own listener.
        assert desk.post("/api/phone/pair", json={"code": "1"}, headers=desk_h).status_code == 400


def test_phone_can_unpair_itself(data_dir):
    app, _ = make_app(data_dir)
    with phone_client(app) as phone:
        auth = pair(app, phone)
        assert phone.post("/api/phone/unpair", headers=auth).status_code == 200
        assert phone.get("/api/status", headers=auth).status_code == 401


# ------------------------------------------------------------------ the real HTTPS listener
def test_listener_serves_https_with_a_trusted_chain(data_dir):
    app, _ = make_app(data_dir)

    async def scenario():
        listener = app.state.phone
        info = await listener.start(0)
        assert info["running"] and not info["error"], info
        assert info["urls"] == [f"https://127.0.0.1:{info['port']}/m/"]
        ctx = ssl.create_default_context(cafile=str(data_dir / "phone" / "jarvis-ca.crt"))
        base = f"https://127.0.0.1:{info['port']}"
        async with httpx.AsyncClient(verify=ctx, base_url=base, trust_env=False) as client:
            assert (await client.get("/m/")).status_code == 200
            assert (await client.get("/api/status")).status_code == 401
            code = app.state.devices.new_code()["code"]
            token = (await client.post("/api/phone/pair", json={"code": code, "name": "Real TLS"})).json()["token"]
            r = await client.get("/api/tasks", headers={"Authorization": "Bearer " + token})
            assert r.status_code == 200
            assert (await client.get("/api/settings", headers={"Authorization": "Bearer " + token})).status_code == 403
        # Plain HTTP is not accepted on the phone port.
        async with httpx.AsyncClient(trust_env=False) as plain:
            with pytest.raises(httpx.HTTPError):
                await plain.get(f"http://127.0.0.1:{info['port']}/m/", timeout=3)
        await listener.stop()
        assert not listener.running
        with socket.socket() as s:  # port released
            s.bind(("127.0.0.1", info["port"]))

    asyncio.run(scenario())


def test_listener_reports_busy_port(data_dir):
    app, _ = make_app(data_dir)

    async def scenario():
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen(1)
            info = await app.state.phone.start(blocker.getsockname()[1])
        assert not info["running"] and "Could not use port" in info["error"]

    asyncio.run(scenario())


def test_settings_toggle_starts_and_stops_listener(data_dir):
    app, _ = make_app(data_dir)
    port = free_port()
    with TestClient(app) as desk:
        h = {"X-Jarvis-Token": TOKEN}
        assert desk.get("/api/status", headers=h).json()["phone"] == {"enabled": False, "running": False}
        assert desk.post("/api/phone/pairing-code", headers=h).status_code == 400  # off: no codes
        desk.put("/api/settings", json={"phone_access": True, "phone_port": port}, headers=h)
        info = desk.get("/api/phone", headers=h).json()
        assert info["running"] and info["port"] == port and info["fingerprint"]
        code = desk.post("/api/phone/pairing-code", headers=h).json()
        assert len(code["code"]) == 6 and code["seconds_left"] > 250
        desk.put("/api/settings", json={"phone_access": False}, headers=h)
        info = desk.get("/api/phone", headers=h).json()
        assert not info["running"] and info["pairing"] is None


def test_phone_access_restored_on_start_and_stopped_on_exit(data_dir):
    from jarvis.config import ConfigStore
    port = free_port()
    ConfigStore(data_dir).update({"phone_access": True, "phone_port": port})
    app, _ = make_app(data_dir)
    with TestClient(app) as desk:
        status = desk.get("/api/status", headers={"X-Jarvis-Token": TOKEN}).json()
        assert status["phone"] == {"enabled": True, "running": True}
    with socket.socket() as s:  # Jarvis exited: the phone port is closed again
        s.bind(("127.0.0.1", port))
