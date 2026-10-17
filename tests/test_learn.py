"""Learning tools: guides, starter decks, coding practice, the API Lab, stand-up notes, and their phone rules."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from jarvis import sync
from jarvis.db import Database
from jarvis.learn import api_lab as lab_module
from jarvis.learn.decks import STARTER_DECKS, StarterDecks
from jarvis.learn.exercises import EXERCISES
from jarvis.learn.guides import GuideLibrary
from jarvis.learn.practice import Runtimes, run_code
from jarvis.learn.standup import standup
from jarvis.phone import PhoneChannel
from jarvis.server import create_app
from tests.conftest import FakeProvider

TOKEN = "test-token"
H = {"X-Jarvis-Token": TOKEN}
HOSTS = {"127.0.0.1:8765", "localhost:8765"}
BASE = "http://127.0.0.1:8765"
API = "/practice/api/v1"


def basic(user, password):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


def desk_app(data_dir, provider=None, **kw):
    return create_app(data_dir, token=TOKEN, allowed_hosts=HOSTS, restore_last_project=False,
                      provider_factory=lambda s: provider or FakeProvider(), **kw)


# ------------------------------------------------------------------ guides
def test_guides_parse_and_search():
    lib = GuideLibrary()
    ids = {g["id"] for g in lib.list()}
    assert {"performance", "project-structure", "git", "workplace", "devnet-apis", "devnet-software-design",
            "api-strategies"} <= ids
    for guide in lib.guides.values():
        assert guide.title and guide.summary and guide.sections
        assert all(s.text.strip() for s in guide.sections)
    expectations = {
        "how do I undo a commit I already pushed": ("git", "Undoing"),
        "should I add database indexes": ("performance", "Index the database"),
        "leaky bucket vs token bucket": ("devnet-apis", ""),
        "observer design pattern": ("devnet-software-design", "Observer"),
        "how to ask for help at work when stuck": ("workplace", "ask for help"),
        "retry with exponential backoff javascript": ("api-strategies", "Retries"),
        "php laravel folder structure": ("project-structure", ""),
    }
    for query, (guide, section) in expectations.items():
        top = lib.search(query, k=2)
        assert any(h["guide"] == guide and section in h["section"] for h in top), (query, top)
    assert lib.search("what is the capital of France") == []
    text, sources = lib.context_for("PUT vs PATCH", 4000)
    assert "PATCH" in text and sources and all(s["kind"] == "guide" and s["path"].startswith("guide:") for s in sources)
    assert lib.context_for("bananas and oranges", 4000) == ("", [])
    with pytest.raises(FileNotFoundError):
        lib.get("no-such-guide")


def test_headings_inside_code_blocks_are_not_sections():
    from jarvis.learn.guides import parse_guide
    g = parse_guide("t", "---\ntitle: T\n---\n# T\n\n## Real\n" + "text " * 60 + "\n```bash\n## not a heading\n```\n")
    assert [s.title for s in g.sections] == ["Real"]


# ------------------------------------------------------------------ practice
RUNTIMES = Runtimes()


@pytest.mark.parametrize("exercise", EXERCISES, ids=[e["id"] for e in EXERCISES])
def test_reference_solution_passes_and_starter_fails(exercise):
    if not RUNTIMES.get()[exercise["language"]]["available"]:
        pytest.skip(f"{exercise['language']} is not installed here")
    good = run_code(exercise, exercise["solution"], RUNTIMES)
    assert good["ok"] and good["passed"] == good["total"] > 0, good
    start = run_code(exercise, exercise["starter"], RUNTIMES)
    assert start["passed"] == 0 and not start["ok"], start


def test_practice_reports_syntax_errors_timeouts_and_output():
    ex = next(e for e in EXERCISES if e["id"] == "py-status-category")
    broken = run_code(ex, "def status_category(code)\n    return 1\n", RUNTIMES)
    assert broken["results"][0]["name"] == "Your code loads" and "SyntaxError" in broken["results"][0]["detail"]
    assert "jarvis-practice-" not in broken["results"][0]["detail"]  # temp folder hidden
    loop = run_code(ex, "def status_category(code):\n    while True:\n        pass\n", RUNTIMES, timeout=2)
    assert loop["timed_out"] and not loop["ok"] and "endless loop" in loop["problem"]
    printed = run_code(ex, "print('debug line')\ndef status_category(code):\n    return 'success'\n", RUNTIMES)
    assert printed["output"] == "debug line" and 0 < printed["passed"] < printed["total"]


def test_practice_api_saves_progress(data_dir):
    with TestClient(desk_app(data_dir), base_url=BASE) as c:
        listing = c.get("/api/learn/exercises", headers=H).json()
        assert listing["can_run"] and len(listing["exercises"]) == len(EXERCISES)
        assert listing["runtimes"]["python"]["available"]
        detail = c.get("/api/learn/exercises/py-basic-auth", headers=H).json()
        assert detail["code"] == detail["starter"] and detail["checks"] == 3 and detail["hints"]
        c.put("/api/learn/exercises/py-basic-auth/code", json={"code": "# draft"}, headers=H)
        assert c.get("/api/learn/exercises/py-basic-auth", headers=H).json()["code"] == "# draft"
        ex = next(e for e in EXERCISES if e["id"] == "py-basic-auth")
        fail = c.post("/api/learn/exercises/py-basic-auth/run", json={"code": ex["starter"]}, headers=H).json()
        assert fail["passed"] == 0 and not fail["solved"] and fail["attempts"] == 1
        win = c.post("/api/learn/exercises/py-basic-auth/run", json={"code": ex["solution"]}, headers=H).json()
        assert win["ok"] and win["solved"] and win["attempts"] == 2
        row = next(e for e in c.get("/api/learn/exercises", headers=H).json()["exercises"] if e["id"] == "py-basic-auth")
        assert row["solved"] and row["best"] == 3
        assert "base64" in c.get("/api/learn/exercises/py-basic-auth/solution", headers=H).json()["solution"]
        assert c.get("/api/learn/exercises/nope", headers=H).status_code == 404


def test_hint_uses_the_model_without_giving_the_answer(data_dir):
    provider = FakeProvider(reply="Look at how you join the username and password.")
    with TestClient(desk_app(data_dir, provider), base_url=BASE) as c:
        r = c.post("/api/learn/exercises/py-basic-auth/hint", headers=H, json={
            "code": "def basic_auth_header(u, p):\n    return {}", "results": [{"name": "x", "ok": False, "detail": "expected"}]})
        assert r.json()["hint"].startswith("Look at")
        prompt = provider.calls[-1][0][-1]["content"]
        assert "Do not write the full solution" in prompt and "expected" in prompt


# ------------------------------------------------------------------ starter decks
def test_starter_decks_install_once_and_respect_deleted_cards(data_dir):
    db = Database(data_dir / "a.db")
    decks = StarterDecks(db)
    first = decks.install("git")
    assert first["added"] == len(next(d for d in STARTER_DECKS if d["key"] == "git")["cards"])
    assert decks.install("git")["added"] == 0  # installing again adds nothing
    with db.connect() as conn:
        card = conn.execute("SELECT id FROM cards WHERE deck_id = ? ORDER BY id LIMIT 1", (first["deck_id"],)).fetchone()
        conn.execute("DELETE FROM cards WHERE id = ?", (card["id"],))
    assert decks.install("git")["added"] == 0  # a card you deleted stays deleted
    listing = {d["key"]: d for d in decks.list()}
    assert listing["git"]["installed"] and listing["git"]["missing"] == 1 and not listing["http-status"]["installed"]
    with pytest.raises(FileNotFoundError):
        decks.install("nope")


def test_starter_deck_installed_on_both_devices_merges_when_syncing(tmp_path):
    laptop, phone = Database(tmp_path / "laptop.db"), Database(tmp_path / "phone.db")
    StarterDecks(laptop).install("http-status")
    StarterDecks(phone).install("http-status")
    sync.apply(laptop, sync.collect(phone))
    sync.apply(phone, sync.collect(laptop))
    for db in (laptop, phone):
        with db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM decks").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 20


def test_starter_deck_api(data_dir):
    with TestClient(desk_app(data_dir), base_url=BASE) as c:
        listing = c.get("/api/learn/decks", headers=H).json()
        assert {d["key"] for d in listing} == {d["key"] for d in STARTER_DECKS}
        r = c.post("/api/learn/decks/devnet-apis/install", headers=H).json()
        assert r["added"] > 40
        assert any(d["name"].startswith("DevNet 4") for d in c.get("/api/study/decks", headers=H).json())


# ------------------------------------------------------------------ chat with guides
def test_chat_includes_guide_notes_only_when_asked(data_dir):
    provider = FakeProvider(reply="401 means not authenticated.")
    with TestClient(desk_app(data_dir, provider), base_url=BASE) as c:
        lines = c.post("/api/chat", headers=H, json={"message": "What is the difference between 401 and 403?",
                                                       "mode": "study", "use_guides": True}).text.splitlines()
        events = [json.loads(line) for line in lines]
        sources = [s for e in events if e["type"] == "sources" for s in e["sources"]]
        assert any(s["kind"] == "guide" for s in sources)
        assert "Reference notes from Jarvis's built-in study guides" in provider.calls[-1][0][-1]["content"]
        c.post("/api/chat", headers=H, json={"message": "What is the difference between 401 and 403?", "mode": "study"})
        assert "Reference notes" not in provider.calls[-1][0][-1]["content"]


# ------------------------------------------------------------------ stand-up
def test_standup_note_from_tasks():
    now = datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)  # a Tuesday
    tasks = [
        {"id": 1, "title": "Write login tests", "status": "done", "priority": "medium", "due_date": None,
         "completed_at": (now - timedelta(hours=20)).isoformat(), "parent_id": None, "project": "shop", "notes": ""},
        {"id": 2, "title": "Old thing", "status": "done", "priority": "low", "due_date": None,
         "completed_at": (now - timedelta(days=5)).isoformat(), "parent_id": None, "project": "", "notes": ""},
        {"id": 3, "title": "Fix N+1 on orders page", "status": "in_progress", "priority": "high", "due_date": None,
         "completed_at": None, "parent_id": None, "project": "", "notes": ""},
        {"id": 4, "title": "DevNet module 4 quiz", "status": "todo", "priority": "medium", "due_date": "2026-10-12",
         "completed_at": None, "parent_id": None, "project": "", "notes": ""},
        {"id": 5, "title": "Deploy to staging", "status": "blocked", "priority": "high", "due_date": None,
         "completed_at": None, "parent_id": None, "project": "", "notes": "Waiting for server access\nmore"},
    ]
    note = standup(tasks, now)
    text = note["text"]
    assert "Finished: Write login tests [shop]" in text and "Old thing" not in text
    assert "Continue: Fix N+1 on orders page" in text and "DevNet module 4 quiz (overdue)" in text
    assert "Deploy to staging – Waiting for server access" in text
    monday = standup([{**tasks[0], "completed_at": (now - timedelta(days=4)).isoformat()}],
                     datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc))
    assert "Since Friday" in monday["text"] and "Write login tests" in monday["text"]


# ------------------------------------------------------------------ API Lab
def test_api_lab_teaches_status_codes(data_dir, monkeypatch):
    monkeypatch.setattr(lab_module, "REPORT_SECONDS", 0.2)
    app = desk_app(data_dir)
    with TestClient(app, base_url=BASE) as c:
        assert c.get(API).json()["name"].startswith("Jarvis practice API")          # no session token needed
        assert c.get(API + "/books").status_code == 401
        assert c.get(API + "/books", headers=basic("learner", "wrong")).status_code == 401
        page = c.get(API + "/books?page=2&per_page=5", headers={"X-API-Key": "practice-key-123"})
        assert page.status_code == 200 and page.json()["page"] == 2 and len(page.json()["items"]) == 5
        assert page.headers["X-Total-Count"] == "24" and 'rel="next"' in page.headers["Link"]
        assert int(page.headers["X-RateLimit-Remaining"]) < 10
        assert c.get(API + "/books?page=x", headers=basic("viewer", "viewer123")).status_code == 400
        assert c.get(API + "/books/999", headers=basic("viewer", "viewer123")).status_code == 404

        editor = {"Authorization": "Bearer " + c.post(API + "/auth/login", headers=basic("learner", "devnet123")).json()["token"]}
        reader = {"Authorization": "Bearer " + c.post(API + "/auth/login", headers=basic("viewer", "viewer123")).json()["token"]}
        book = {"title": "My API Notes", "author": "Me", "year": 2026, "isbn": "my-isbn-1"}
        assert c.post(API + "/books", json=book, headers=basic("learner", "devnet123")).status_code == 401  # Bearer only
        assert c.post(API + "/books", json=book, headers=reader).status_code == 403                         # authorization
        assert c.post(API + "/books", content="<book/>", headers={**editor, "Content-Type": "application/xml"}).status_code == 415
        assert c.post(API + "/books", content="{title: 1}", headers={**editor, "Content-Type": "application/json"}).status_code == 400
        missing = c.post(API + "/books", json={"author": "Me"}, headers=editor)
        assert missing.status_code == 400 and missing.json()["error"]["details"][0]["field"] == "title"
        created = c.post(API + "/books", json=book, headers=editor)
        assert created.status_code == 201 and created.headers["Location"].endswith(f"/books/{created.json()['id']}")
        assert c.post(API + "/books", json=book, headers=editor).status_code == 409                      # duplicate isbn
        bid = created.json()["id"]
        assert c.patch(f"{API}/books/{bid}", json={"year": 2025}, headers=editor).json()["year"] == 2025
        assert c.put(f"{API}/books/{bid}", json={"title": "Only title"}, headers=editor).status_code == 400  # PUT = whole book
        assert c.delete(f"{API}/books/{bid}", headers=editor).status_code == 204
        assert c.get(f"{API}/books/{bid}", headers=editor).status_code == 404

        # (that token has used up its 10-request bucket by now, so log in again: each token has its own bucket)
        editor = {"Authorization": "Bearer " + c.post(API + "/auth/login", headers=basic("learner", "devnet123")).json()["token"]}
        job = c.post(API + "/reports", headers=editor)
        assert job.status_code == 202 and job.json()["status"] == "pending"
        time.sleep(0.3)
        done = c.get(job.headers["Location"], headers=editor).json()
        assert done["status"] == "done" and done["result"]["books"] == 24

        flaky = [c.get(API + "/flaky", headers=reader).status_code for _ in range(3)]
        assert flaky == [503, 503, 200]


def test_api_lab_rate_limit(data_dir):
    with TestClient(desk_app(data_dir), base_url=BASE) as c:
        statuses = [c.get(API + "/books", headers=basic("viewer", "viewer123")) for _ in range(12)]
        assert [r.status_code for r in statuses][:10] == [200] * 10
        limited = statuses[-1]
        assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
        assert limited.headers["X-RateLimit-Remaining"] == "0"
        # Another user has their own bucket.
        assert c.get(API + "/books", headers=basic("learner", "devnet123")).status_code == 200


def test_api_lab_webhooks_are_signed_and_local_only(data_dir):
    app = desk_app(data_dir)
    app.state.api_lab.transport = httpx.ASGITransport(app=app)
    with TestClient(app, base_url=BASE) as c:
        editor = {"Authorization": "Bearer " + c.post(API + "/auth/login", headers=basic("learner", "devnet123")).json()["token"]}
        assert c.post(API + "/webhooks", json={"url": "https://example.com/hook"}, headers=editor).status_code == 400
        hook = c.post(API + "/webhooks", json={"url": f"{BASE}/practice/hooks/my-app", "events": ["book.created"]},
                      headers=editor).json()
        c.post(API + "/books", json={"title": "Webhook test", "author": "Me"}, headers=editor)
        for _ in range(50):
            inbox = c.get("/practice/hooks").json()
            if inbox["inbox"]:
                break
            time.sleep(0.05)
        entry = inbox["inbox"][0]
        assert entry["name"] == "my-app" and entry["event"] == "book.created" and entry["signature_valid"] is True
        expected = "sha256=" + hmac.new(hook["secret"].encode(), entry["body"].encode(), hashlib.sha256).hexdigest()
        assert entry["signature"] == expected and json.loads(entry["body"])["data"]["title"] == "Webhook test"
        assert inbox["deliveries"][0]["status"] == 200
        c.post("/practice/hooks/forged", json={"x": 1}, headers={"X-Jarvis-Signature": "sha256=00"})
        assert c.get("/practice/hooks").json()["inbox"][0]["signature_valid"] is False
        c.post("/practice/lab/reset")
        assert c.get("/practice/hooks").json()["webhooks"] == []


def test_api_lab_soap_and_json_rpc(data_dir):
    with TestClient(desk_app(data_dir), base_url=BASE) as c:
        envelope = ('<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
                    '<GetBook><id>4</id></GetBook></soap:Body></soap:Envelope>')
        r = c.post("/practice/soap", content=envelope, headers={"Content-Type": "text/xml"})
        assert r.status_code == 200 and "<title>Clean Code</title>" in r.text
        fault = c.post("/practice/soap", content=envelope.replace("<id>4", "<id>999"), headers={"Content-Type": "text/xml"})
        assert fault.status_code == 500 and "<faultcode>soap:Client</faultcode>" in fault.text
        assert "Fault" in c.post("/practice/soap", content='<!DOCTYPE x [<!ENTITY a "b">]><x/>').text
        rpc = c.post("/practice/rpc", json={"jsonrpc": "2.0", "method": "books.count", "id": 1}).json()
        assert rpc == {"jsonrpc": "2.0", "result": 24, "id": 1}
        assert c.post("/practice/rpc", json={"jsonrpc": "2.0", "method": "nope", "id": 2}).json()["error"]["code"] == -32601
        assert c.post("/practice/rpc", content="{").json()["error"]["code"] == -32700


# ------------------------------------------------------------------ who may use what
def test_api_lab_needs_a_local_host_header(data_dir):
    with TestClient(desk_app(data_dir), base_url="http://evil.example:8765") as c:
        assert c.get(API).status_code == 403  # DNS-rebinding protection still applies


def test_phone_connected_to_laptop_can_learn_but_not_run_code(data_dir):
    app = desk_app(data_dir, phone_host="127.0.0.1")
    with TestClient(PhoneChannel(app), base_url="https://192.168.1.5:8766") as phone:
        code = app.state.devices.new_code()["code"]
        auth = {"Authorization": "Bearer " + phone.post("/api/phone/pair", json={"code": code, "name": "P"}).json()["token"]}
        assert phone.get("/api/learn/guides", headers=auth).status_code == 200
        assert phone.get("/api/learn/guides/git", headers=auth).json()["markdown"].startswith("# Git")
        assert phone.post("/api/learn/decks/git/install", headers=auth).status_code == 200
        listing = phone.get("/api/learn/exercises", headers=auth).json()
        assert listing["can_run"] is False
        ex = EXERCISES[0]
        assert phone.post(f"/api/learn/exercises/{ex['id']}/run", json={"code": ex["solution"]}, headers=auth).status_code == 403
        assert phone.get("/practice/api/v1", headers=auth).status_code == 403
        assert phone.get("/api/learn/standup", headers=auth).status_code == 200


def test_jarvis_on_the_phone_can_run_code_and_the_api_lab(data_dir):
    app = desk_app(data_dir, pocket=True)
    with TestClient(PhoneChannel(app), base_url="http://127.0.0.1:8766") as phone:
        _, token = app.state.devices.issue("Jarvis app on this phone")
        auth = {"Authorization": "Bearer " + token}
        assert phone.get("/api/learn/exercises", headers=auth).json()["can_run"] is True
        ex = next(e for e in EXERCISES if e["language"] == "python")
        r = phone.post(f"/api/learn/exercises/{ex['id']}/run", json={"code": ex["solution"]}, headers=auth)
        assert r.status_code == 200 and r.json()["ok"]
        assert phone.get("/practice/api/v1/books", headers={"X-API-Key": "practice-key-123"}).status_code == 200
