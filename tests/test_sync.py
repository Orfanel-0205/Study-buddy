"""Two-way sync between Jarvis on the laptop and Jarvis on the phone, and pocket mode."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time

import httpx
from fastapi.testclient import TestClient

from jarvis.activity import ActivityLog
from jarvis.config import ConfigStore
from jarvis.db import Database
from jarvis.phone import PhoneChannel
from jarvis.phone.devices import DeviceRegistry
from jarvis.server import create_app
from jarvis.study import CardIn, DeckIn, StudyStore
from jarvis.sync import apply, collect, sync_with
from jarvis.tasks import TaskIn, TaskStore, TaskUpdate
from tests.conftest import FakeProvider


def stores(path):
    db = Database(path)
    return db, TaskStore(db), StudyStore(db)


def exchange(a_db, b_db, since_a="", since_b=""):
    """One sync both ways, like the phone (b) talking to the laptop (a)."""
    apply(a_db, collect(b_db, since_b))
    apply(b_db, collect(a_db, since_a))


def titles(tasks: TaskStore):
    return sorted(t["title"] for t in tasks.list())


def test_tasks_and_cards_copy_both_ways(tmp_path):
    a_db, a_tasks, a_study = stores(tmp_path / "laptop.db")
    b_db, b_tasks, b_study = stores(tmp_path / "phone.db")
    parent = a_tasks.create(TaskIn(title="Revise biology", priority="high"))
    a_tasks.create(TaskIn(title="Chapter 1", parent_id=parent["id"]))
    deck = a_study.create_deck(DeckIn(name="Cells"))
    a_study.add_cards(deck["id"], [CardIn(front="ATP?", back="Mitochondria")])
    b_tasks.create(TaskIn(title="Buy notebook"))
    exchange(a_db, b_db)
    assert titles(a_tasks) == titles(b_tasks) == ["Buy notebook", "Chapter 1", "Revise biology"]
    child = next(t for t in b_tasks.list() if t["title"] == "Chapter 1")
    assert b_tasks.get(child["parent_id"])["title"] == "Revise biology"  # parent link survives
    b_deck = b_study.decks()[0]
    assert b_deck["name"] == "Cells" and b_study.cards(b_deck["id"])[0]["back"] == "Mitochondria"


def test_newer_change_wins_and_deletions_sync(tmp_path):
    a_db, a_tasks, a_study = stores(tmp_path / "laptop.db")
    b_db, b_tasks, b_study = stores(tmp_path / "phone.db")
    t = a_tasks.create(TaskIn(title="Essay"))
    exchange(a_db, b_db)
    b_t = b_tasks.list()[0]
    a_tasks.update(t["id"], TaskUpdate(notes="older edit on laptop"))
    time.sleep(0.01)  # timestamps have millisecond precision: make the phone's edit really newer
    b_tasks.update(b_t["id"], TaskUpdate(status="done"))  # newer edit on the phone
    exchange(a_db, b_db)
    assert a_tasks.get(t["id"])["status"] == "done" == b_tasks.get(b_t["id"])["status"]
    assert a_tasks.get(t["id"])["notes"] == ""  # the phone's whole newer version won
    # a card reviewed on the phone keeps its schedule on the laptop
    deck = a_study.create_deck(DeckIn(name="Words"))
    card = a_study.add_cards(deck["id"], [CardIn(front="perro", back="dog")])[0]
    exchange(a_db, b_db)
    b_card = b_study.cards(b_study.decks()[0]["id"])[0]
    b_study.review(b_card["id"], "good")
    exchange(a_db, b_db)
    assert a_study.card(card["id"])["reps"] == 1 and a_study.card(card["id"])["due"] == b_study.card(b_card["id"])["due"]
    # deleting on one side deletes on the other
    a_tasks.delete(t["id"])
    exchange(a_db, b_db)
    assert "Essay" not in titles(b_tasks)
    a_study.delete_deck(deck["id"])  # deleting a deck removes its cards everywhere
    exchange(a_db, b_db)
    assert [d["name"] for d in b_study.decks()] == []


def test_edit_after_delete_brings_item_back(tmp_path):
    a_db, a_tasks, _ = stores(tmp_path / "laptop.db")
    b_db, b_tasks, _ = stores(tmp_path / "phone.db")
    a_tasks.create(TaskIn(title="Plan trip"))
    exchange(a_db, b_db)
    a_tasks.delete(a_tasks.list()[0]["id"])
    b_tasks.update(b_tasks.list()[0]["id"], TaskUpdate(notes="changed later on the phone"))
    exchange(a_db, b_db)
    assert titles(a_tasks) == ["Plan trip"] and a_tasks.list()[0]["notes"] == "changed later on the phone"


def test_sync_over_http_with_pairing(tmp_path, data_dir):
    laptop = create_app(data_dir, token="t", provider_factory=lambda s: FakeProvider(), restore_last_project=False)
    pocket_dir = tmp_path / "pocket"
    (pocket_dir / "backups").mkdir(parents=True)
    (pocket_dir / "logs").mkdir()
    pocket_db, pocket_tasks, _ = stores(pocket_dir / "jarvis.db")
    pocket_tasks.create(TaskIn(title="Made on the phone"))
    TaskStore(Database(data_dir / "jarvis.db")).create(TaskIn(title="Made on the laptop"))
    _, token = laptop.state.devices.issue("Jarvis on this phone")
    transport = httpx.ASGITransport(app=PhoneChannel(laptop))
    url = "https://192.168.1.10:8766"
    result = asyncio.run(sync_with(pocket_db, url, token, None, transport=transport))
    assert result["received"]["tasks"] == 1 and result["sent"]["tasks"] == 1
    assert titles(pocket_tasks) == ["Made on the laptop", "Made on the phone"]
    assert titles(TaskStore(Database(data_dir / "jarvis.db"))) == ["Made on the laptop", "Made on the phone"]
    again = asyncio.run(sync_with(pocket_db, url, token, None, transport=transport))
    assert again["received"] == {"tasks": 0, "decks": 0, "cards": 0, "deleted": 0, "reviews": 0, "checkins": 0}  # nothing new
    try:
        asyncio.run(sync_with(pocket_db, url, "wrong", None, transport=transport))
    except RuntimeError as exc:
        assert "Pair again" in str(exc)
    else:
        raise AssertionError("a wrong key must be refused")


def test_pocket_mode_rules(data_dir):
    app = create_app(data_dir, token="t", provider_factory=lambda s: FakeProvider(), restore_last_project=False,
                     pocket=True)
    with TestClient(PhoneChannel(app), base_url="http://localhost:8766") as phone:
        assert phone.get("/", follow_redirects=False).headers["location"] == "/m/"
        assert phone.get("/api/tasks").status_code == 401
        _, token = app.state.devices.issue("Jarvis app")
        auth = {"Authorization": "Bearer " + token}
        status = phone.get("/api/status", headers=auth).json()
        assert status["pocket"] is True and status["phone"]["running"] is False  # never listens on the network
        assert phone.get("/api/sync/status", headers=auth).json() == {"enabled": False, "pocket": True}
        assert phone.post("/api/commands/run", json={"command": "git status"}, headers=auth).status_code == 403


def test_issue_device_token_cli(data_dir):
    out = subprocess.run([sys.executable, "-m", "jarvis", "--data-dir", str(data_dir), "--issue-device-token", "Jarvis app"],
                         capture_output=True, text=True, check=True).stdout
    token = json.loads(out)["token"]
    db = Database(data_dir / "jarvis.db")
    assert DeviceRegistry(db, ActivityLog(db)).verify(token)["name"] == "Jarvis app"
    assert ConfigStore(data_dir).get().sync_url == ""


def test_reviews_and_task_areas_sync(tmp_path):
    laptop, phone = Database(tmp_path / "laptop.db"), Database(tmp_path / "phone.db")
    deck = StudyStore(laptop).create_deck(DeckIn(name="Spanish"))
    card = StudyStore(laptop).add_cards(deck["id"], [CardIn(front="perro", back="dog")])[0]
    apply(phone, collect(laptop))
    phone_card = StudyStore(phone).cards(StudyStore(phone).decks()[0]["id"])[0]
    StudyStore(phone).review(phone_card["id"], "good")       # reviewed on the phone
    StudyStore(laptop).review(card["id"], "again")           # and on the laptop
    TaskStore(phone).create(TaskIn(title="Revise DevNet 4", area="study"))
    TaskStore(phone).create(TaskIn(title="Fix login bug", project="shop"))  # project -> developing
    got = apply(laptop, collect(phone))
    assert got["reviews"] == 1
    apply(phone, collect(laptop))
    for db in (laptop, phone):
        with db.connect() as conn:
            grades = sorted(r["grade"] for r in conn.execute("SELECT grade FROM study_reviews"))
            areas = {r["title"]: r["area"] for r in conn.execute("SELECT title, area FROM tasks")}
        assert grades == ["again", "good"]
        assert areas == {"Revise DevNet 4": "study", "Fix login bug": "dev"}
    assert apply(laptop, collect(phone))["reviews"] == 0  # the same reviews are never added twice
    # A copy of Jarvis that doesn't know about areas yet still syncs (area defaults to "")
    old = {"tasks": [{**{k: v for k, v in collect(phone)["tasks"][0].items() if k != "area"},
                      "uid": "old-copy-task", "title": "From an older Jarvis", "updated_at": "2999-01-01T00:00:00+00:00"}]}
    apply(laptop, old)
    with laptop.connect() as conn:
        assert conn.execute("SELECT area FROM tasks WHERE uid = 'old-copy-task'").fetchone()["area"] == ""
