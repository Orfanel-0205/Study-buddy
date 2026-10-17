"""Auto mode, Coding Focus, check-ins, the build planner/hackathon, Study Buddy's state, and syncing check-ins."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from jarvis import sync
from jarvis.assistant.router import route
from jarvis.build import catalog, hackathon
from jarvis.checkins import CheckinIn, CheckinStore, advice, insights
from jarvis.config import ConfigStore
from jarvis.db import Database
from jarvis.focus import FocusMonitor
from jarvis.learn.guides import GuideLibrary
from jarvis.phone import PhoneChannel
from jarvis.server import create_app
from tests.conftest import FakeProvider

TOKEN = "t"
H = {"X-Jarvis-Token": TOKEN}


def app_for(data_dir, provider=None, **kw):
    return create_app(data_dir, token=TOKEN, allowed_hosts={"testserver"}, restore_last_project=False,
                      provider_factory=lambda s: provider or FakeProvider(), phone_host="127.0.0.1", **kw)


# ------------------------------------------------------------------ chat: Auto mode and grounding
def test_router_picks_sensible_modes():
    cases = {
        "We're going to make a start up offering restaurants a website, we only have 23 dollars. What should we say?": "business",
        "What tech stack and file structure should I use for a booking app?": "stack",
        "We have a hackathon this weekend, 24 hours, team of 3": "hackathon",
        "TypeError: Cannot read properties of undefined (reading 'map')": "test",
        "My business app throws an error: KeyError price": "test",
        "Explain what an API is, with a simple example.": "explain",
        "Quiz me on DevNet module 4": "study",
        "I feel overwhelmed with my thesis and work": "coach",
        "hello": "general",
    }
    for text, mode in cases.items():
        assert route(text)[0] == mode, (text, route(text))


def test_guides_only_when_they_fit():
    lib = GuideLibrary()
    startup = ("We started by using free trial AI calls and scripts but got no calls. Our targets are restaurants and we "
               "offer them a website. What should we say, with 23 dollars only?")
    _, src = lib.context_for(startup, 4000)
    assert src and all("startup-playbook" in s["path"] for s in src)
    for off_topic in ("I like pizza and basketball on weekends", "hello there"):
        assert lib.context_for(off_topic, 4000) == ("", [])


def test_auto_chat_routes_and_grounds_business_answers(data_dir):
    provider = FakeProvider(reply="Talk to 15 owners first.")
    with TestClient(app_for(data_dir, provider)) as c:
        events = [json.loads(line) for line in c.post("/api/chat", headers=H, json={
            "message": "How do I start a startup selling websites to restaurants with only 23 dollars?", "mode": "auto",
            "lang": "ja"}).text.splitlines()]
        assert any(e["type"] == "status" and "Business & startup advisor" in e["text"] for e in events)
        meta = next(e for e in events if e["type"] == "meta")
        assert meta["mode"] == "business"
        system = provider.calls[-1][0][0]["content"]
        user = provider.calls[-1][0][-1]["content"]
        assert "Business & startup advisor" in system and "Japanese" in system
        assert "Never invent prices" in system
        assert "Jarvis catalog notes" in user and "Restaurant website" in user  # reliable tools, not guesses
        convo = c.get(f"/api/conversations/{meta['conversation_id']}", headers=H).json()
        assert convo["messages"][0]["mode"] == "business"  # saved under the mode actually used


def test_check_in_summary_reaches_the_model(data_dir):
    provider = FakeProvider()
    with TestClient(app_for(data_dir, provider)) as c:
        c.post("/api/chat", headers=H, json={"message": "Help me plan today", "mode": "coach", "wellbeing": "mood 2/5; energy 1/5"})
        assert "mood 2/5; energy 1/5" in provider.calls[-1][0][0]["content"]


# ------------------------------------------------------------------ build planner and hackathon
def test_plan_puts_your_language_first_and_uses_real_tools():
    p = catalog.plan("website with a menu admin for restaurants and a chatbot", "php")
    assert p["title"].startswith("Restaurant") and p["stacks"][0]["name"].startswith("PHP")
    names = {t["name"] for t in p["stacks"][0]["tech"]}
    assert {"Laravel (PHP)", "Filament (for Laravel)", "PayMongo"} <= names
    tree = p["stacks"][0]["structure"]
    assert "app/" in tree and "Models/" in tree and "Filament/Resources/" in tree and len(tree.splitlines()) > 5
    js = catalog.plan("restaurant menu site", "ts")
    assert js["stacks"][0]["name"].startswith("JavaScript")
    for t in catalog.TECH.values():
        assert t["url"].startswith("https://") and t["cost"] and t["for"]


def test_hackathon_plan_and_tasks(data_dir):
    p = hackathon.plan("HealthHack", "2026-10-24T09:00", 24, ["Ana", "Ben", "Cy"], "health")
    assert p["phases"][0]["start"] == "2026-10-24T09:00" and p["phases"][-1]["end"] == "2026-10-25T09:00"
    assert [m["role"] for m in p["team"]][0] == "Backend + data"
    with TestClient(app_for(data_dir)) as c:
        r = c.post("/api/build/hackathon", headers=H, json={"name": "HealthHack", "start": "2026-10-24T09:00", "hours": 24,
                                                             "team": ["Ana", "Ben"], "add_tasks": True}).json()
        tasks = c.get("/api/tasks", headers=H).json()
        parent = next(t for t in tasks if t["id"] == r["task_id"])
        assert parent["area"] == "dev" and sum(1 for t in tasks if t["parent_id"] == parent["id"]) == len(hackathon.PHASES)
        assert c.post("/api/build/hackathon", headers=H, json={"start": "tomorrow", "hours": 24}).status_code == 400
        plan = c.post("/api/build/plan", headers=H, json={"idea": "booking app for a salon", "language": "python"}).json()
        assert plan["title"].startswith("Booking") and plan["stacks"][0]["name"].startswith("Python")


# ------------------------------------------------------------------ check-ins
def test_check_in_advice_follows_how_you_feel():
    tired = advice({"mood": 3, "energy": 1, "stress": 2, "sleep_hours": 4, "body": ["hungry"]})
    assert tired["kind"] == "gentle" and tired["minutes"] == 20 and any("Eat" in t for t in tired["tips"])
    great = advice({"mood": 5, "energy": 5, "stress": 1, "sleep_hours": 8, "body": []})
    assert great["kind"] == "deep" and great["minutes"] == 50
    stressed = advice({"mood": 3, "energy": 3, "stress": 5, "sleep_hours": None, "body": []})
    assert stressed["breathing"] and any("breathing" in t for t in stressed["tips"])
    low = advice({"mood": 1, "energy": 3, "stress": 4, "sleep_hours": None, "body": []})
    assert "1553" in low["support"]
    assert advice({"mood": 4, "energy": 3, "stress": 2, "sleep_hours": 7, "body": []})["support"] == ""


def test_check_in_api_and_insights(data_dir):
    with TestClient(app_for(data_dir)) as c:
        r = c.post("/api/checkins", headers=H, json={"mood": 4, "energy": 2, "stress": 3, "sleep_hours": 6,
                                                      "body": ["tired", "nonsense"], "context": "focus"}).json()
        assert json.loads(r["checkin"]["body"]) == ["tired"] and r["advice"]["kind"] == "gentle"
        assert c.post("/api/checkins", headers=H, json={"mood": 9, "energy": 2, "stress": 3}).status_code == 422
        assert c.get("/api/checkins/latest", headers=H).json()["checkin"]["mood"] == 4
        ins = c.get("/api/checkins/insights", headers=H).json()
        assert ins["count"] == 1 and "more day" in ins["notes"][0]


def test_check_ins_sync_between_devices(tmp_path):
    laptop, phone = Database(tmp_path / "l.db"), Database(tmp_path / "p.db")
    CheckinStore(phone).add(CheckinIn(mood=3, energy=4, stress=2, body=["rested"]))
    assert sync.apply(laptop, sync.collect(phone))["checkins"] == 1
    assert sync.apply(laptop, sync.collect(phone))["checkins"] == 0
    assert CheckinStore(laptop).latest()["energy"] == 4


# ------------------------------------------------------------------ Coding Focus
class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def monitor(tmp_path, **settings):
    cfg = ConfigStore(tmp_path)
    cfg.update({"focus_enabled": True, "focus_grace_minutes": 5, "focus_cooldown_minutes": 15, **settings})
    clock = Clock()
    return FocusMonitor(cfg, Database(tmp_path / "f.db"), probe=lambda: "code.exe", clock=clock), clock


def test_focus_states_and_one_reminder_per_stretch(tmp_path):
    m, clock = monitor(tmp_path)
    m.tick("code.exe")
    assert m.status()["state"] == "coding"
    clock.t += 60
    m.tick("chrome.exe")
    assert m.status()["state"] == "away"
    clock.t += 4 * 60
    m.tick("chrome.exe")
    assert m.status()["state"] == "away"  # still inside the 5-minute grace period
    clock.t += 61
    m.tick("chrome.exe")
    st = m.status()
    assert st["state"] == "distracted" and st["alert"]["id"] == 1 and "5 min" in st["alert"]["message"]
    clock.t += 2 * 60
    m.tick("chrome.exe")
    assert m.status()["alert"]["id"] == 1  # one reminder per stretch away
    clock.t += 10
    m.tick("code.exe")
    assert m.status()["state"] == "coding"
    clock.t += 1
    m.tick("spotify.exe")
    clock.t += 6 * 60
    m.tick("spotify.exe")  # a new stretch past the grace period, but only ~8 minutes since the last reminder
    assert m.status()["state"] == "distracted" and m.status()["alert"]["id"] == 1  # cooldown (15 minutes)
    clock.t += 8 * 60
    m.tick("spotify.exe")
    assert m.status()["alert"]["id"] == 2


def test_focus_snooze_pause_and_jarvis_tab(tmp_path):
    m, clock = monitor(tmp_path)
    m.tick("chrome.exe")
    m.snooze(10)
    clock.t += 9 * 60
    m.tick("chrome.exe")
    assert m.status()["state"] == "snoozed"
    clock.t += 2 * 60
    m.tick("chrome.exe")
    assert m.status()["state"] == "away"  # the grace period starts again after a snooze
    m.pause(True)
    clock.t += 60 * 60
    m.tick("chrome.exe")
    assert m.status()["state"] == "paused" and m.status()["alert"] is None
    m.pause(False)
    m.heartbeat()                # the Jarvis page is the focused tab
    m.tick("msedge.exe")
    assert m.status()["state"] == "coding"
    m.tick("pythonw.exe")        # clicking Study Buddy's own window doesn't count as leaving
    assert m.status()["app"] == "msedge.exe"


def test_focus_off_and_coding_minutes(tmp_path):
    m, clock = monitor(tmp_path)
    for _ in range(30):
        clock.t += 3
        m.tick("code.exe")
    assert m.coding_minutes_today() == 1
    m.config.update({"focus_enabled": False})
    m.tick("chrome.exe")
    assert m.status()["state"] == "off"


def test_focus_and_companion_routes(data_dir):
    with TestClient(app_for(data_dir)) as c:
        st = c.put("/api/focus", headers=H, json={"focus_enabled": True, "focus_grace_minutes": 3,
                                                   "focus_apps": ["Code.exe", " Termux "]}).json()
        assert st["enabled"] and st["grace_minutes"] == 3 and st["apps"] == ["code.exe", "termux"]
        assert c.post("/api/focus/snooze", headers=H, json={"minutes": 5, "break": True}).json()["snoozed_for"] > 0
        state = c.get("/api/companion/state", headers=H).json()
        assert state["pose"] == "sleepy" and "Break" in state["message"]["text"] and state["pack"].startswith("study-buddy")
        assert c.post("/api/focus/resume", headers=H).json()["state"] in ("coding", "away", "off", "distracted")
        assert c.put("/api/companion/overlay", headers=H, json={"pack": "study-buddy-1"}).json()["pack"] == "study-buddy-1"
        assert c.put("/api/companion/overlay", headers=H, json={"pack": "robot"}).status_code == 422
    with TestClient(PhoneChannel(app_for(data_dir)), base_url="https://192.168.1.5:8766") as phone:
        assert phone.get("/api/focus").status_code == 403          # the phone can't watch the laptop
        assert phone.put("/api/companion/overlay", json={"enabled": True}).status_code == 403


def test_robot_companion_is_gone():
    packs = json.loads((__import__("pathlib").Path(__file__).resolve().parent.parent / "jarvis" / "static" / "companion" / "packs.json")
                       .read_text(encoding="utf-8"))["packs"]
    assert [p["id"] for p in packs] == ["study-buddy-1", "study-buddy-2"]
    for p in packs:
        assert {i["mood"] for i in p["items"]} == {"cheer", "code", "study", "idea", "sleepy", "celebrate", "pouty", "relax"}


def test_check_in_steers_the_verse_or_quote(tmp_path):
    from datetime import datetime
    import random

    from jarvis.motivation import pick

    db = Database(tmp_path / "j.db")
    CheckinStore(db).add(CheckinIn(mood=2, energy=2, stress=5))
    noon = datetime(2026, 10, 14, 12, 0).astimezone()  # a Wednesday at noon: no late-night or weekend boost
    picks = [pick(db, now=noon, rng=random.Random(i)) for i in range(40)]
    assert picks[0]["context"]["checkin"] == {"mood": 2, "energy": 2, "stress": 5}
    calming = [p for p in picks if {"worth", "peace", "help", "rest"} & set(p["themes"])]
    assert len(calming) >= 32  # boosted, not forced
    assert any(p["reason"].startswith("You said") for p in calming)


def test_new_pages_are_served_on_both_devices(data_dir):
    with TestClient(app_for(data_dir)) as c:
        page = c.get("/").text
        for f in ("i18n.js", "build.js", "build.css", "companion.js"):
            assert f"/static/{f}?v=" in page
            assert c.get(f"/static/{f}").status_code == 200
        assert 'data-view="build"' in page and 'id="build-root"' in page
    with TestClient(PhoneChannel(app_for(data_dir)), base_url="https://192.168.1.5:8766") as phone:
        page = phone.get("/m/").text
        for f in ("i18n.js", "build.js", "build.css"):
            assert f"/static/{f}?v=" in page and phone.get(f"/static/{f}").status_code == 200
        assert "/static/build.js?v=" in phone.get("/m/sw.js").text


def test_resume_also_ends_a_snooze(tmp_path):
    m, clock = monitor(tmp_path)
    m.snooze(15)
    m.tick("chrome.exe")
    assert m.status()["state"] == "snoozed"
    m.pause(False)
    m.tick("chrome.exe")
    assert m.status()["state"] == "away" and m.status()["snoozed_for"] == 0
