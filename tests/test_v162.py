"""v1.6.2: answers have a length limit, and an answer that repeats itself is stopped (a small model
looping used to run until the 10-minute timeout and overload the phone)."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from jarvis.assistant.service import LOOP_NOTE, repeating
from jarvis.llm.base import ChatOptions
from jarvis.llm.ollama import OllamaProvider
from tests.conftest import FakeProvider
from tests.test_v16 import H, app_for


def test_loops_are_recognised_but_normal_content_is_not():
    assert repeating("Intro. " + "The API returns JSON data to the client. " * 6)
    assert repeating("List:\n" + "Remember to drink some water today.\n" * 7)
    for fine in ("A normal answer that explains REST APIs well, with GET and POST.",
                 "| a | b |\n|" + "---|" * 40 + "\n| " + " | ".join(["x"] * 40),
                 "Done.\n" + "-" * 200, "grid = [" + "0, " * 120,
                 "\n".join(f"- Step {i}: do the next thing" for i in range(20))):
        assert not repeating(fine), fine[:40]


def test_a_looping_answer_is_stopped_with_a_note(data_dir):
    provider = FakeProvider(reply="Sure. " + "The API returns JSON data to the client. " * 60)
    with TestClient(app_for(data_dir, provider)) as c:
        lines = c.post("/api/chat", headers=H, json={"message": "What does an API return?", "mode": "general"}).text.splitlines()
        events = [json.loads(x) for x in lines if x.strip()]
    text = "".join(e["text"] for e in events if e["type"] == "content")
    assert text.endswith(LOOP_NOTE) and text.count("JSON data") < 20  # stopped early, not after all 60
    assert events[-1]["type"] == "done"
    assert provider.calls[0][1].max_tokens == 2048


def test_detailed_answers_get_twice_the_length_limit(data_dir):
    provider = FakeProvider(reply="Fine.")
    with TestClient(app_for(data_dir, provider)) as c:
        c.post("/api/chat", headers=H, json={"message": "Explain HTTP", "detail": "detailed"})
    assert provider.calls[0][1].max_tokens == 4096


def test_the_length_limit_reaches_ollama():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        seen.append(json.loads(request.content))
        return httpx.Response(200, text=json.dumps({"message": {"content": "ok"}, "done": True, "done_reason": "stop"}) + "\n")

    import asyncio

    async def run():
        p = OllamaProvider("http://127.0.0.1:11434", transport=httpx.MockTransport(handler))
        return [c async for c in p.chat_stream([{"role": "user", "content": "hi"}], ChatOptions(model="m", max_tokens=1024))]

    asyncio.run(run())
    assert seen[0]["options"]["num_predict"] == 1024



def test_jarvis_on_the_phone_chooses_its_own_model(data_dir):
    from jarvis.llm.base import ModelInfo, ProviderStatus
    from jarvis.phone import PhoneChannel
    from jarvis.server import create_app

    class PhoneModels(FakeProvider):
        async def status(self):
            return ProviderStatus(reachable=True, version="t", models=[
                ModelInfo(name="qwen3:1.7b", capabilities=["completion"]), ModelInfo(name="gemma3:4b", capabilities=["completion", "vision"])])

    laptop = create_app(data_dir, token="t", provider_factory=lambda s: PhoneModels(), restore_last_project=False)
    with TestClient(laptop) as c:
        assert c.get("/api/pocket/model", headers={"X-Jarvis-Token": "t"}).status_code == 404  # only on the phone
    app = create_app(data_dir, token="t", provider_factory=lambda s: PhoneModels(), restore_last_project=False, pocket=True)
    with TestClient(PhoneChannel(app), base_url="http://localhost:8766") as phone:
        _, token = app.state.devices.issue("Jarvis app")
        auth = {"Authorization": "Bearer " + token}
        st = phone.get("/api/pocket/model", headers=auth).json()
        assert [m["name"] for m in st["models"]] == ["qwen3:1.7b", "gemma3:4b"]
        r = phone.put("/api/pocket/model", json={"model": "gemma3:4b"}, headers=auth).json()
        assert r == {"model": "gemma3:4b", "vision_model": "gemma3:4b"}  # it can read photos too: one model for all
        assert phone.put("/api/pocket/model", json={"model": "qwen2.5-coder:7b"}, headers=auth).status_code == 400
        assert phone.put("/api/settings", json={"model": "x"}, headers=auth).status_code == 403  # other settings: no


def _voice_tool():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "tools" / "make_companion_voice.py"
    spec = importlib.util.spec_from_file_location("make_companion_voice", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_voice_line_has_a_mood_and_both_languages():
    tool = _voice_tool()
    assert set(tool.LINES["en"]) == set(tool.LINES["ja"]) == set(tool.MOODS)
    assert set(tool.MOODS.values()) <= set(tool.STYLES)


def test_voicevox_lines_use_the_style_for_their_mood(monkeypatch, tmp_path):
    tool = _voice_tool()
    speakers = [{"name": "Test", "styles": [{"name": "ノーマル", "id": 1}, {"name": "ツンツン", "id": 2}, {"name": "ささやき", "id": 3}]}]
    used = {}

    def fake(path, params=None, body=None):
        if path == "/speakers":
            return json.dumps(speakers).encode()
        if path == "/audio_query":
            return json.dumps({"text": params["text"]}).encode()
        used[body["text"]] = (params["speaker"], body["speedScale"], body["pitchScale"], body["intonationScale"])
        return b"RIFF"

    monkeypatch.setattr(tool, "voicevox", fake)
    monkeypatch.setattr(tool, "OUT", tmp_path / "voice")
    monkeypatch.setattr(tool, "ANDROID", tmp_path / "android")
    monkeypatch.setattr(tool, "ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr("subprocess.run", lambda cmd, check: open(cmd[-1], "wb").write(b"mp3"))
    tool.record_voicevox("Test", 1.1, 0.02, 1.3, only="ja")
    assert used[tool.LINES["ja"]["nudge"]][0] == 2  # annoyed for the reminder
    assert used[tool.LINES["ja"]["hello_late"]][0] == 3  # whispering late at night
    assert used[tool.LINES["ja"]["passed"]][0] == 1  # no happy style: normal
    assert used[tool.LINES["ja"]["back"]][1:] == (1.1, 0.02, 1.3)
    manifest = json.loads((tmp_path / "voice" / "voice.json").read_text(encoding="utf-8"))
    assert manifest["credit"] == "VOICEVOX:Test"
    assert manifest["lines"]["ja"]["nudge"] == {"file": "voice/ja/nudge.mp3", "text": tool.LINES["ja"]["nudge"], "mood": "tsun"}
    assert (tmp_path / "android" / "ja" / "nudge.mp3").read_bytes() == b"mp3"


def test_an_unknown_voicevox_character_is_explained(monkeypatch):
    tool = _voice_tool()
    monkeypatch.setattr(tool, "voicevox", lambda path, params=None, body=None: b"[]")
    import pytest
    with pytest.raises(SystemExit, match="--list-voicevox"):
        tool.voicevox_styles("Nobody")
