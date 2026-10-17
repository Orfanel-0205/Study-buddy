"""Answer-quality features: real test evidence, per-mode model, search by meaning, eval grading."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from jarvis.config import Settings
from jarvis.db import Database
from jarvis.phone import PhoneChannel
from jarvis.project.embeddings import Embedder
from jarvis.project.index import ProjectIndex
from jarvis.project.workspace import Workspace
from jarvis.server import create_app
from tests.conftest import FakeProvider

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))
import run_eval  # noqa: E402

TOKEN = "t"
H = {"X-Jarvis-Token": TOKEN}


def make(data_dir, provider):
    return create_app(data_dir, token=TOKEN, provider_factory=lambda s: provider, restore_last_project=False,
                      phone_host="127.0.0.1")


def chat(client, body, headers=H):
    with client.stream("POST", "/api/chat", json=body, headers=headers) as r:
        assert r.status_code == 200
        return [json.loads(line) for line in r.iter_lines() if line.strip()]


# ------------------------------------------------------------------ evidence from real runs
def test_debug_mode_includes_latest_real_run(data_dir, project):
    provider = FakeProvider()
    app = make(data_dir, provider)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": str(project)}, headers=H)
        app.state.projects.wait_for_index()
        run = c.post("/api/commands/run", json={"command": "python --version"}, headers=H).json()
        for _ in range(100):
            if c.get(f"/api/commands/{run['id']}", headers=H).json()["status"] != "running":
                break
            time.sleep(0.1)
        chat(c, {"message": "why?", "mode": "general", "stream_id": "a"})
        assert "Real result of running" not in provider.calls[-1][0][-1]["content"]  # only in debugging mode
        events = chat(c, {"message": "why did it fail?", "mode": "test", "stream_id": "b"})
        sent = provider.calls[-1][0][-1]["content"]
        assert "Real result of running `python --version`" in sent and "Python 3" in sent
        sources = [e for e in events if e["type"] == "sources"][-1]["sources"]
        assert {"path": "$ python --version", "start_line": 0, "end_line": 0, "kind": "command"} in sources


def test_run_tests_first_runs_the_project_tests(data_dir, project):
    provider = FakeProvider()
    app = make(data_dir, provider)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": str(project)}, headers=H)
        assert c.get("/api/status", headers=H).json()["project"]["can_run_tests"] is True
        events = chat(c, {"message": "do the tests pass?", "mode": "test", "run_tests": True, "stream_id": "r"})
        statuses = [e["text"] for e in events if e["type"] == "status"]
        assert statuses[0].startswith("Running ") and "-m pytest -q first" in statuses[0]
        assert statuses[1].startswith("Tests finished (exit code 0)")
        assert "1 passed" in provider.calls[-1][0][-1]["content"]
        kinds = [a["kind"] for a in c.get("/api/activity", headers=H).json()]
        assert "command_started" in kinds


def test_phone_cannot_trigger_test_runs(data_dir, project):
    provider = FakeProvider()
    app = make(data_dir, provider)
    with TestClient(app) as desk, TestClient(PhoneChannel(app), base_url="https://192.168.1.2:8766") as phone:
        desk.post("/api/project/open", json={"path": str(project)}, headers=H)
        code = app.state.devices.new_code()["code"]
        token = phone.post("/api/phone/pair", json={"code": code, "name": "P"}).json()["token"]
        events = chat(phone, {"message": "test it", "mode": "test", "run_tests": True, "stream_id": "p"},
                      headers={"Authorization": "Bearer " + token})
        assert not [e for e in events if e["type"] == "status"]
        assert not app.state.runner.runs


# ------------------------------------------------------------------ per-mode model
def test_code_model_used_for_code_modes(data_dir):
    provider = FakeProvider(models=("chat:4b", "coder:7b"))
    app = make(data_dir, provider)
    with TestClient(app) as c:
        c.put("/api/settings", json={"model": "chat:4b", "code_model": "coder:7b"}, headers=H)
        chat(c, {"message": "hi", "mode": "general", "stream_id": "1"})
        chat(c, {"message": "write code", "mode": "implement", "stream_id": "2"})
        chat(c, {"message": "debug", "mode": "test", "stream_id": "3"})
        assert [call[1].model for call in provider.calls] == ["chat:4b", "coder:7b", "coder:7b"]
        c.put("/api/settings", json={"code_model": "missing:7b"}, headers=H)
        events = chat(c, {"message": "write code", "mode": "implement", "stream_id": "4"})
        assert provider.calls[-1][1].model == "chat:4b"
        assert any(e["type"] == "status" and "isn't installed" in e["text"] for e in events)


# ------------------------------------------------------------------ search by meaning
TOPICS = {"secret": 0, "password": 0, "credential": 0, "redact": 0, "weather": 1, "rain": 1, "sunny": 1}


def fake_embedding_server(calls):
    """Embeds by topic: texts about secrets point one way, about weather another."""
    def handler(request: httpx.Request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "nomic-embed-text:latest"}]})
        body = json.loads(request.content)
        calls.append(body["input"])
        vectors = []
        for text in body["input"]:
            v = [0.01, 0.01, 0.01]
            for word, axis in TOPICS.items():
                if word in text.lower():
                    v[axis] += 1
            vectors.append(v)
        return httpx.Response(200, json={"embeddings": vectors})
    return httpx.MockTransport(handler)


def test_embedder_prefixes_and_caches(data_dir):
    calls = []
    emb = Embedder(Settings(), Database(data_dir / "jarvis.db"), transport=fake_embedding_server(calls))
    assert emb.available()
    first = emb.embed(["hide the password", "sunny weather"])
    assert calls[0][0].startswith("search_document: ")
    again = emb.embed(["hide the password", "sunny weather"])  # served from the cache
    assert len(calls) == 1 and list(first[0]) == list(again[0])
    emb.embed(["password?"], "query")
    assert calls[-1][0].startswith("search_query: ")
    with pytest.raises(Exception):
        Embedder(Settings(endpoint="http://10.1.2.3:11434"))  # never a non-local server


def test_meaning_search_finds_files_keywords_miss(tmp_path, data_dir):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "privacy.py").write_text("def scrub(text):\n    # redact credential values\n    return text\n")
    (root / "forecast.py").write_text("def tomorrow():\n    return 'rain or sunny'\n")
    calls = []
    emb = Embedder(Settings(), Database(data_dir / "jarvis.db"), transport=fake_embedding_server(calls))
    keyword_only = ProjectIndex()
    keyword_only.build(Workspace(root), 100)
    assert keyword_only.search("where do we hide secret passwords") == []  # no shared words
    hybrid = ProjectIndex()
    status = hybrid.build(Workspace(root), 100, emb)
    assert status.semantic == "ready" and status.embedded == 2
    assert hybrid.search("where do we hide secret passwords")[0]["path"] == "privacy.py"


def test_meaning_search_reports_missing_model(tmp_path, data_dir):
    root = tmp_path / "p"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n")
    no_models = httpx.MockTransport(lambda r: httpx.Response(200, json={"models": []}))
    status = ProjectIndex().build(Workspace(root), 10, Embedder(Settings(), transport=no_models))
    assert status.state == "ready" and status.semantic == "unavailable"


# ------------------------------------------------------------------ evaluation grading
CASE = {"options": ["It returns 0", "It returns None", "It raises ZeroDivisionError", "It returns 0.0"], "answer": "C"}


@pytest.mark.parametrize("reply,letter", [
    ("C\nBecause len([]) is 0.", "C"),
    ("**C) It raises ZeroDivisionError** because...", "C"),
    ("The answer is B.", "B"),
    ("Answer: (D)", "D"),
    ("A function that divides by zero raises ZeroDivisionError, so: C) is right", "C"),
    ("It raises ZeroDivisionError since the length is zero.", "C"),
    ("I am not sure.", None),
])
def test_choice_grading(reply, letter):
    assert run_eval.grade_choice(reply, CASE) == letter


def test_hidden_tests_runner():
    ok, _ = run_eval.run_hidden_tests("def f(x):\n    return x * 2\n", "assert f(2) == 4\n")
    assert ok
    ok, detail = run_eval.run_hidden_tests("def f(x):\n    return x\n", "assert f(2) == 4\n")
    assert not ok and "AssertionError" in detail
    ok, detail = run_eval.run_hidden_tests("while True:\n    pass\n", "")
    assert not ok and detail == "timed out"
    assert run_eval.extract_code("Here:\n```python\ndef g():\n    pass\n```\nDone") == "def g():\n    pass\n"
