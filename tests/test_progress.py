"""Progress (studying vs developing), the word of encouragement, task areas and the new API routes."""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from jarvis.activity import ActivityLog
from jarvis.db import Database, now_iso
from jarvis.motivation import ENTRIES, pick
from jarvis.phone import PhoneChannel
from jarvis.progress import progress
from jarvis.server import create_app
from jarvis.study import CardIn, DeckIn, StudyStore
from jarvis.tasks import TaskIn, TaskStore, TaskUpdate
from tests.conftest import FakeProvider

TOKEN = "t"
H = {"X-Jarvis-Token": TOKEN}


def _at(db, table_sql, params):
    with db.connect() as conn:
        conn.execute(table_sql, params)


def test_progress_separates_studying_from_developing(tmp_path):
    db = Database(tmp_path / "j.db")
    today = date.today()
    study = StudyStore(db)
    deck = study.create_deck(DeckIn(name="DevNet"))
    cards = study.add_cards(deck["id"], [CardIn(front=f"q{i}", back="a") for i in range(4)])
    for c, g in zip(cards, ["good", "easy", "again", "good"]):
        study.review(c["id"], g)
    tasks = TaskStore(db)
    s = tasks.create(TaskIn(title="Read module 4", area="study"))
    d = tasks.create(TaskIn(title="Fix checkout", project="shop"))
    tasks.create(TaskIn(title="Buy groceries"))          # no area: counted in neither
    for t in (s, d):
        tasks.update(t["id"], TaskUpdate(status="done"))
    log = ActivityLog(db)
    log.record("practice", "checked", exercise="x", passed=3, total=3)
    log.record("change_applied", "applied", path="a.py")
    log.record("command_finished", "tests ok", exit_code=0)
    log.record("command_finished", "tests failed", exit_code=1)
    with db.connect() as conn:
        conn.execute("INSERT INTO conversations (title, mode, created_at, updated_at) VALUES ('c', 'study', ?, ?)", (now_iso(), now_iso()))
        for mode in ("study", "coach", "implement", "test", "general"):
            conn.execute("INSERT INTO messages (conversation_id, role, content, mode, created_at) VALUES (1, 'user', 'q', ?, ?)",
                         (mode, now_iso()))
        conn.execute("INSERT INTO practice (exercise_id, solved_at, updated_at) VALUES ('py-basic-auth', ?, ?)", (now_iso(), now_iso()))
    p = progress(db, 7)
    st, dv = p["study"], p["dev"]
    last_s, last_d = st["daily"][-1], dv["daily"][-1]
    assert last_s["date"] == today.isoformat() and len(st["daily"]) == 7
    assert (last_s["reviews"], last_s["practice"], last_s["questions"], last_s["tasks"]) == (4, 1, 2, 1)
    assert (last_d["tasks"], last_d["changes"], last_d["runs"], last_d["questions"]) == (1, 1, 2, 2)
    assert st["retention"] == 75 and st["grades"] == {"again": 1, "hard": 0, "good": 2, "easy": 1}
    assert st["streak"] == 1 and dv["streak"] == 1
    assert dv["test_runs"] == {"passed": 1, "failed": 1}
    assert {m["mode"]: m["questions"] for m in dv["modes"]}["implement"] == 1
    assert st["exercises"]["solved"] == 1
    py = next(x for x in st["exercises"]["by_language"] if x["language"] == "python")
    assert py["solved"] == 1 and py["total"] >= 6
    assert st["cards"] == {"total": 4, "learned": 3, "due": 0}  # "again" resets a card; it comes back tomorrow


def test_streak_counts_consecutive_days(tmp_path):
    db = Database(tmp_path / "j.db")
    today = date.today()
    with db.connect() as conn:
        for back in (0, 1, 2, 4):  # today, yesterday, two days ago, then a gap
            when = datetime.combine(today - timedelta(days=back), datetime.min.time()).replace(hour=12).astimezone()
            conn.execute("INSERT INTO study_reviews (card_uid, deck_uid, grade, reviewed_at) VALUES ('c', 'd', 'good', ?)",
                         (when.astimezone(timezone.utc).isoformat(),))
    p = progress(db, 30)
    assert p["study"]["streak"] == 3 and p["study"]["active_days"] == 4


def test_new_subtasks_inherit_area(tmp_path):
    tasks = TaskStore(Database(tmp_path / "j.db"))
    parent = tasks.create(TaskIn(title="Study for the quiz", area="study"))
    child = tasks.create(TaskIn(title="Make flashcards", parent_id=parent["id"]))
    assert child["area"] == "study"
    assert tasks.create(TaskIn(title="API", project="KitaPH"))["area"] == "dev"
    assert tasks.update(parent["id"], TaskUpdate(area="dev"))["area"] == "dev"


def test_motivation_entries_are_well_formed():
    ids = [e["id"] for e in ENTRIES]
    assert len(ids) == len(set(ids)) and len(ENTRIES) >= 40
    for e in ENTRIES:
        assert e["kind"] in ("verse", "quote", "note") and e["text"] and e["source"] and e["themes"]
        if e["kind"] == "verse":
            assert e["source"].endswith("(KJV)")


def test_motivation_follows_context_and_preferences(tmp_path):
    db = Database(tmp_path / "j.db")
    late = datetime(2026, 10, 14, 23, 30).astimezone()
    picks = [pick(db, now=late, rng=random.Random(i)) for i in range(60)]
    restful = sum(1 for p in picks if {"rest", "peace"} & set(p["themes"]))
    assert restful > 35, restful  # late at night, rest and peace come up most
    assert any(p["reason"] == "It's late" for p in picks)
    verses = [pick(db, kinds="verses", rng=random.Random(i)) for i in range(20)]
    assert all(p["kind"] == "verse" for p in verses)
    quotes = [pick(db, kinds="quotes", rng=random.Random(i)) for i in range(20)]
    assert all(p["kind"] in ("quote", "note") for p in quotes)
    everything_but_one = [e["id"] for e in ENTRIES if e["kind"] == "verse"][1:]
    only = pick(db, kinds="verses", exclude=everything_but_one)
    assert only["id"] == [e["id"] for e in ENTRIES if e["kind"] == "verse"][0]  # recent ones are skipped


def test_motivation_notices_failures(tmp_path):
    db = Database(tmp_path / "j.db")
    log = ActivityLog(db)
    for _ in range(4):
        log.record("practice", "checked", passed=1, total=5)
    noon = datetime(2026, 10, 14, 13, 0).astimezone()  # a Wednesday: no weekend themes
    picks = [pick(db, now=noon, rng=random.Random(i)) for i in range(60)]
    assert sum(1 for p in picks if {"perseverance", "worth"} & set(p["themes"])) > 25
    assert picks[0]["context"]["recent_failures"] == 4


def test_progress_and_motivation_routes_work_for_computer_and_phone(data_dir):
    app = create_app(data_dir, token=TOKEN, allowed_hosts={"testserver"}, restore_last_project=False,
                     provider_factory=lambda s: FakeProvider(), phone_host="127.0.0.1")
    with TestClient(app) as c:
        p = c.get("/api/progress?days=7", headers=H).json()
        assert p["days"] == 7 and set(p) >= {"study", "dev"}
        m = c.get("/api/motivation?kinds=verses&focus=peace&exclude=mt-11-28", headers=H).json()
        assert m["kind"] == "verse" and m["id"] != "mt-11-28"
        r = c.post("/api/tasks", json={"title": "Thesis chapter 2", "area": "study"}, headers=H).json()
        assert r["area"] == "study"
        assert c.post("/api/tasks", json={"title": "x", "area": "fun"}, headers=H).status_code == 422
    with TestClient(PhoneChannel(app), base_url="https://192.168.1.5:8766") as phone:
        code = app.state.devices.new_code()["code"]
        auth = {"Authorization": "Bearer " + phone.post("/api/phone/pair", json={"code": code, "name": "P"}).json()["token"]}
        assert phone.get("/api/progress?days=30", headers=auth).status_code == 200
        assert phone.get("/api/motivation", headers=auth).status_code == 200
