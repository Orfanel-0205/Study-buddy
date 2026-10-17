"""Study companion: flashcards with spaced repetition, images, vision model choice, reliability."""

from __future__ import annotations

import base64
import io
import json
import sqlite3
from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from jarvis.assistant.service import pick_vision_model
from jarvis.db import Database
from jarvis.images import ImageError, ImageStore
from jarvis.llm import ChatOptions, OpenAICompatibleProvider
from jarvis.phone import PhoneChannel
from jarvis.reliability import daily_backup
from jarvis.server import create_app
from jarvis.study import CardIn, DeckIn, StudyStore, schedule
from tests.conftest import FakeProvider

TOKEN = "t"
H = {"X-Jarvis-Token": TOKEN}
TODAY = date(2026, 10, 13)


def png_data_url() -> str:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class VisionFake(FakeProvider):
    """Fake server with one model that can see and one that can't."""

    async def status(self):
        st = await super().status()
        for m in st.models:
            m.capabilities = ["completion", "vision"] if m.name == "eyes:4b" else ["completion"]
        return st


# ------------------------------------------------------------------ scheduling
def card(**kw):
    return {"ease": 2.5, "interval": 0, "reps": 0, "lapses": 0, **kw}


def test_spaced_repetition_intervals_grow_and_reset():
    c = card()
    c.update(schedule(c, "good", TODAY))
    assert (c["interval"], c["due"]) == (1, "2026-10-14")
    c.update(schedule(c, "good", TODAY))
    assert c["interval"] == 3
    c.update(schedule(c, "good", TODAY))
    assert c["interval"] == round(3 * 2.5)
    c.update(schedule(c, "again", TODAY))
    assert (c["interval"], c["reps"], c["lapses"]) == (1, 0, 1) and c["ease"] == pytest.approx(2.3)
    for _ in range(20):  # ease never drops below the minimum
        c.update(schedule(c, "again", TODAY))
    assert c["ease"] == pytest.approx(1.3)
    assert schedule(card(), "easy", TODAY)["interval"] == 3
    assert schedule(card(reps=3, interval=10), "hard", TODAY)["interval"] == 12


def test_study_store_due_and_review(data_dir):
    store = StudyStore(Database(data_dir / "jarvis.db"))
    deck = store.create_deck(DeckIn(name="  Cells "))
    assert deck["name"] == "Cells"
    cards = store.add_cards(deck["id"], [CardIn(front="Q1", back="A1"), CardIn(front="Q2", back="A2")], today=TODAY)
    assert [c["front"] for c in store.due(today=TODAY)] == ["Q1", "Q2"]  # new cards are due right away
    store.review(cards[0]["id"], "good", reviewed_on=TODAY)
    assert [c["front"] for c in store.due(today=TODAY)] == ["Q2"]
    assert [c["front"] for c in store.due(today=TODAY + timedelta(days=1))] == ["Q1", "Q2"]
    assert [c["front"] for c in store.due(today=TODAY, within_days=1)] == ["Q1", "Q2"]
    summary = store.decks(today=TODAY)[0]
    assert (summary["cards"], summary["due"], summary["new"]) == (2, 1, 1)
    store.delete_deck(deck["id"])
    assert store.decks() == []


# ------------------------------------------------------------------ images
def test_image_store_accepts_only_real_images(tmp_path):
    images = ImageStore(tmp_path / "images")
    name = images.save(png_data_url())
    assert name.endswith(".png") and images.save(png_data_url()) == name  # stored once
    assert images.base64(name)
    for bad in ["data:image/png;base64,bm90IGFuIGltYWdl", "!!!not base64", base64.b64encode(b"<svg/>").decode()]:
        with pytest.raises(ImageError):
            images.save(bad)
    with pytest.raises(ImageError):
        images.path("../../secret.png")


def test_vision_model_choice():
    models = [{"name": "chat:2b", "capabilities": ["completion"]},
              {"name": "gemma3:4b", "capabilities": ["completion", "vision"]},
              {"name": "qwen3-vl:2b", "capabilities": ["vision"]}]
    assert pick_vision_model("", "chat:2b", models) == "gemma3:4b"       # best installed that can see
    assert pick_vision_model("", "qwen3-vl:2b", models) == "qwen3-vl:2b"  # the chat model can see
    assert pick_vision_model("qwen3-vl:2b", "chat:2b", models) == "qwen3-vl:2b"
    assert pick_vision_model("", "chat:2b", models[:1]) == ""


def test_chat_with_image_uses_vision_model(data_dir):
    provider = VisionFake(models=("chat:2b", "eyes:4b"))
    app = create_app(data_dir, token=TOKEN, provider_factory=lambda s: provider, restore_last_project=False)
    with TestClient(app) as c:
        c.put("/api/settings", json={"model": "chat:2b"}, headers=H)
        assert c.get("/api/status", headers=H).json()["model"]["vision_model"] == "eyes:4b"
        with c.stream("POST", "/api/chat", json={"message": "what is this?", "images": [png_data_url()],
                                                 "mode": "study", "stream_id": "i"}, headers=H) as r:
            events = [json.loads(x) for x in r.iter_lines() if x]
        assert any(e["type"] == "status" and "eyes:4b" in e["text"] for e in events)
        messages, options = provider.calls[-1]
        assert options.model == "eyes:4b" and messages[-1]["images"] and "Study companion" in messages[0]["content"]
        conv = c.get("/api/conversations/1", headers=H).json()["messages"]
        name = conv[0]["images"][0]
        assert c.get(f"/api/images/{name}", headers=H).headers["content-type"] == "image/png"
        # next question without a picture goes back to the chat model; history mentions the image
        with c.stream("POST", "/api/chat", json={"message": "and now?", "conversation_id": 1, "stream_id": "j"}, headers=H) as r:
            list(r.iter_lines())
        messages, options = provider.calls[-1]
        assert options.model == "chat:2b" and "attached 1 image" in messages[1]["content"]
        bad = c.post("/api/chat", json={"message": "x", "images": ["data:image/png;base64,AAAA"]}, headers=H)
        assert bad.status_code == 400


def test_no_vision_model_gives_clear_error(data_dir):
    app = create_app(data_dir, token=TOKEN, provider_factory=lambda s: FakeProvider(), restore_last_project=False)
    with TestClient(app) as c:
        with c.stream("POST", "/api/chat", json={"message": "?", "images": [png_data_url()], "stream_id": "n"}, headers=H) as r:
            events = [json.loads(x) for x in r.iter_lines() if x]
        assert events[-1]["type"] == "error" and events[-1]["code"] == "no_vision" and "ollama pull" in events[-1]["hint"]


def test_openai_compatible_sends_images_as_content_parts():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n')

    import asyncio
    p = OpenAICompatibleProvider("http://127.0.0.1:8080/v1", transport=httpx.MockTransport(handler))
    asyncio.run(p.chat([{"role": "user", "content": "look", "images": ["iVBORw0KGgo="]}], ChatOptions(model="m")))
    content = seen[0]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "look"}
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


# ------------------------------------------------------------------ study API
def test_flashcard_api_generate_import_export(data_dir):
    provider = VisionFake(models=("chat:2b", "eyes:4b"),
                          json_reply='{"title": "Cells", "cards": [{"front": "What makes ATP?", "back": "Mitochondria"},'
                                     ' {"front": "", "back": "skipped"}]}')
    app = create_app(data_dir, token=TOKEN, provider_factory=lambda s: provider, restore_last_project=False)
    with TestClient(app) as c:
        assert c.post("/api/study/generate", json={"text": " ", "images": []}, headers=H).status_code == 400
        result = c.post("/api/study/generate", json={"images": [png_data_url()], "count": 5}, headers=H).json()
        assert result["title"] == "Cells" and result["cards"] == [{"front": "What makes ATP?", "back": "Mitochondria"}]
        assert result["transcript"]  # the picture was read first, then cards were written from the text
        assert provider.calls[-2][1].model == "eyes:4b" and provider.calls[-1][1].json_schema is not None
        deck = c.post("/api/study/decks", json={"name": "Cells"}, headers=H).json()
        c.post(f"/api/study/decks/{deck['id']}/cards", json={"cards": result["cards"]}, headers=H)
        imported = c.post(f"/api/study/decks/{deck['id']}/import",
                          json={"text": "front,back\nnucleus,holds DNA\n\"ribosome, small\",makes proteins\n"}, headers=H).json()
        assert imported == {"added": 2}
        tsv = c.post(f"/api/study/decks/{deck['id']}/import", json={"text": "chat\tcat\nperro\tdog"}, headers=H).json()
        assert tsv == {"added": 2}
        exported = c.get(f"/api/study/decks/{deck['id']}/export", headers=H)
        assert exported.text.splitlines()[0] == "front,back" and '"ribosome, small",makes proteins' in exported.text
        due = c.get("/api/study/due", headers=H).json()
        assert len(due) == 5 and set(due[0]["next"]) == {"again", "hard", "good", "easy"}
        r = c.post(f"/api/study/cards/{due[0]['id']}/review", json={"grade": "good", "reviewed_on": "2026-10-01"}, headers=H).json()
        assert r["due"] == "2026-10-02" and r["last_reviewed"] == "2026-10-01"
        assert c.post(f"/api/study/cards/{due[0]['id']}/review", json={"grade": "perfect"}, headers=H).status_code == 422


def test_phone_can_study_but_not_import(data_dir):
    app = create_app(data_dir, token=TOKEN, provider_factory=lambda s: FakeProvider(), restore_last_project=False,
                     phone_host="127.0.0.1")
    with TestClient(PhoneChannel(app), base_url="https://192.168.1.5:8766") as phone:
        code = app.state.devices.new_code()["code"]
        auth = {"Authorization": "Bearer " + phone.post("/api/phone/pair", json={"code": code, "name": "P"}).json()["token"]}
        deck = phone.post("/api/study/decks", json={"name": "Spanish"}, headers=auth).json()
        cards = phone.post(f"/api/study/decks/{deck['id']}/cards", json={"cards": [{"front": "perro", "back": "dog"}]}, headers=auth).json()
        assert phone.get("/api/study/due?within_days=14", headers=auth).status_code == 200
        assert phone.post(f"/api/study/cards/{cards[0]['id']}/review", json={"grade": "easy"}, headers=auth).status_code == 200
        assert phone.post(f"/api/study/decks/{deck['id']}/import", json={"text": "a,b"}, headers=auth).status_code == 403
        assert phone.get("/api/system/autostart", headers=auth).status_code == 403


# ------------------------------------------------------------------ reliability
def test_daily_backup_once_a_day_and_keeps_seven(data_dir):
    db = Database(data_dir / "jarvis.db")
    folder = data_dir / "backups" / "daily"
    first = daily_backup(db, folder, today=TODAY)
    assert first and daily_backup(db, folder, today=TODAY) is None  # only once per day
    conn = sqlite3.connect(first)  # a real, readable database copy
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] >= 4
    finally:
        conn.close()  # (sqlite3's "with" doesn't close; Windows can't delete open files)
    for i in range(1, 10):
        daily_backup(db, folder, today=TODAY + timedelta(days=i))
    names = sorted(p.name for p in folder.glob("jarvis-*.db"))
    assert len(names) == 7 and names[-1] == f"jarvis-{(TODAY + timedelta(days=9)).isoformat()}.db"
