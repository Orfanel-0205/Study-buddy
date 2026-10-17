"""v1.6.1: Study Buddy's generated expressions, the phone's offline pack, and the page/overlay pose sync."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from jarvis.build import catalog, hackathon
from jarvis.phone import PhoneChannel
from tests.test_v16 import H, app_for

ART = Path(__file__).resolve().parent.parent / "jarvis" / "static" / "companion"


def test_expressions_exist_for_every_pack():
    packs = json.loads((ART / "packs.json").read_text(encoding="utf-8"))["packs"]
    for p in packs:
        items = {i["mood"]: i for i in p["items"]}
        for mood in ("cheer", "code", "study", "idea"):  # open eyes: she can blink
            for key in ("blink", "half", "overlay_blink"):
                assert (ART / items[mood][key]).is_file(), (p["id"], mood, key)
        assert items["relax"]["file"] == items["study"]["blink"]  # breaks: the study pose, eyes peacefully closed
        for key in ("plain", "plain_blink", "blink", "file", "overlay"):
            assert (ART / items["pouty"][key]).is_file(), (p["id"], key)
        for i in p["items"]:
            assert (ART / i["file"]).is_file() and (ART / i["overlay"]).is_file()
    android = ART.parent.parent.parent / "android" / "app" / "assets" / "companion"
    assert sorted(f.name for f in android.glob("*.webp")) == sorted(f.name for f in ART.glob("*.webp"))


def test_offline_pack_has_what_the_phone_needs(data_dir):
    with TestClient(PhoneChannel(app_for(data_dir)), base_url="https://192.168.1.5:8766") as phone:
        assert phone.get("/api/offline/pack").status_code == 401  # paired phones only
    with TestClient(app_for(data_dir)) as c:
        c.post("/api/tasks", headers=H, json={"title": "PRIVATE-TASK-7731"})
        c.post("/api/checkins", headers=H, json={"mood": 3, "energy": 3, "stress": 3, "note": "PRIVATE-NOTE-7731"})
        pack = c.get("/api/offline/pack", headers=H).json()
    assert len(pack["guides"]) >= 12 and all(g["markdown"].startswith("#") or g["markdown"] for g in pack["guides"])
    assert {b["id"] for b in pack["build"]["blueprints"]} >= {"restaurant", "booking", "network"}
    assert pack["build"]["fallback"]["id"] == "web" and "laravel" in pack["build"]["tech"]
    assert [ph["title"] for ph in pack["hackathon"]["phases"]] == [t for _, _, t, _ in hackathon.PHASES]
    assert pack["words"] and {"id", "kind", "source", "text"} <= set(pack["words"][0])
    assert "PRIVATE-" not in json.dumps(pack)  # only Jarvis's own content: none of your tasks, notes or chats


def test_offline_planner_data_matches_the_server():
    # build.js redoes catalog.plan() from this data; the rules it relies on must hold
    data = catalog.offline_data()
    assert catalog.plan("zzz qqq")["blueprint"] == data["fallback"]["id"]
    for bp in data["blueprints"]:
        assert all(k == k.lower() for k in bp["keywords"])  # build.js lower-cases the idea and checks includes()
        for st in bp["stacks"]:
            assert st["structure"] in data["structures"] and all(t in data["tech"] for t in st["tech"])


def test_page_pose_drives_the_floating_window(data_dir):
    with TestClient(app_for(data_dir)) as c:
        assert c.put("/api/companion/session", headers=H, json={"pose": "relax"}).json() == {"ok": True}
        assert c.get("/api/companion/state", headers=H).json()["pose"] == "relax"
        c.put("/api/companion/session", headers=H, json={"pose": "pouty", "message": "Hmph! 5 min."})
        st = c.get("/api/companion/state", headers=H).json()
        assert st["pose"] == "pouty" and st["message"]["text"] == "Hmph! 5 min." and st["message"]["alert"]
        assert c.put("/api/companion/session", headers=H, json={"pose": "robot"}).status_code == 422
    with TestClient(PhoneChannel(app_for(data_dir)), base_url="https://192.168.1.5:8766") as phone:
        assert phone.put("/api/companion/session", json={"pose": "code"}).status_code == 403


def test_more_stoicism_and_philosophy(tmp_path):
    import random
    from collections import Counter
    from datetime import datetime

    from jarvis.db import Database
    from jarvis.motivation import ENTRIES, pick

    schools = [e for e in ENTRIES if e.get("school")]
    assert len(schools) >= 30 and {e["school"] for e in schools} == {"stoic", "philosophy"}
    for e in schools:  # every Stoic or philosophy passage names its (public-domain) translation
        assert e["kind"] == "quote" and ("(tr. " in e["source"] or e["id"] == "durant-habit"), e["id"]
    db = Database(tmp_path / "j.db")
    noon = datetime(2026, 10, 14, 13, 0).astimezone()  # a Wednesday: no time-of-day or weekend leaning
    mix = Counter("philosophy" if p.get("school") else p["kind"] for p in (pick(db, now=noon, rng=random.Random(i)) for i in range(300)))
    assert mix["philosophy"] > 0.5 * 300 and mix["verse"] > 0.12 * 300, mix  # mostly philosophy, verses still there
    only = [pick(db, kinds="philosophy", rng=random.Random(i)) for i in range(40)]
    assert all(p.get("school") for p in only)


def test_offline_words_keep_the_school(data_dir):
    with TestClient(app_for(data_dir)) as c:
        words = c.get("/api/offline/pack", headers=H).json()["words"]
        assert sum(1 for w in words if w.get("school") == "stoic") >= 25
        assert c.get("/api/motivation?kinds=philosophy", headers=H).json()["school"] in ("stoic", "philosophy")
