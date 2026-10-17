"""HTTP API tests using a fake model, so they run without Ollama."""

from __future__ import annotations

import json
import time
import warnings

import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)
from fastapi.testclient import TestClient  # noqa: E402

from jarvis.server import create_app  # noqa: E402
from tests.conftest import FakeProvider  # noqa: E402

TOKEN = "test-token"
H = {"X-Jarvis-Token": TOKEN}


def make_client(data_dir, provider=None, hosts=None):
    provider = provider or FakeProvider()
    app = create_app(data_dir, token=TOKEN, allowed_hosts=hosts, provider_factory=lambda s: provider,
                     restore_last_project=False)
    return TestClient(app), provider, app


def stream_events(client, body):
    with client.stream("POST", "/api/chat", json=body, headers=H) as resp:
        assert resp.status_code == 200
        return [json.loads(line) for line in resp.iter_lines() if line.strip()]


# ------------------------------------------------------------------ security
def test_token_required_and_page_embeds_it(data_dir):
    client, _, _ = make_client(data_dir)
    with client:
        assert client.get("/api/status").status_code == 403
        assert client.get("/api/status", headers={"X-Jarvis-Token": "wrong"}).status_code == 403
        assert client.get("/api/status", headers=H).status_code == 200
        page = client.get("/")
        assert page.status_code == 200 and f'content="{TOKEN}"' in page.text
        assert client.get("/static/app.js").status_code == 200


def test_host_and_origin_checks(data_dir):
    client, _, _ = make_client(data_dir, hosts={"testserver"})
    with client:
        assert client.get("/api/status", headers=H).status_code == 200
        assert client.get("/api/status", headers={**H, "Host": "evil.example.com"}).status_code == 403
        assert client.get("/api/status", headers={**H, "Origin": "http://evil.example.com"}).status_code == 403
        assert client.get("/api/status", headers={**H, "Origin": "http://testserver"}).status_code == 200


# ------------------------------------------------------------------ status & settings
def test_status_reports_model_states(data_dir):
    provider = FakeProvider(reachable=False)
    client, _, _ = make_client(data_dir, provider)
    with client:
        st = client.get("/api/status", headers=H).json()["model"]
        assert st["state"] == "not_running" and "ollama" in st["hint"].lower()
        provider.reachable = True
        st = client.get("/api/status", headers=H).json()["model"]
        assert st["state"] == "ready" and st["model"] == "fake-model:1b"
        client.put("/api/settings", json={"model": "missing:7b"}, headers=H)
        st = client.get("/api/status", headers=H).json()["model"]
        assert st["state"] == "model_missing" and "ollama pull missing:7b" in st["hint"]
        provider.models = []
        client.put("/api/settings", json={"model": ""}, headers=H)
        assert client.get("/api/status", headers=H).json()["model"]["state"] == "no_models"


def test_remote_endpoint_is_blocked(data_dir):
    client, _, _ = make_client(data_dir)
    with client:
        # Use the real factory path: a remote endpoint must never get a provider.
        from jarvis.llm import create_provider
        client.app.state.config.update({"endpoint": "http://203.0.113.9:11434"})
        from jarvis.config import EndpointNotLocalError
        with pytest.raises(EndpointNotLocalError):
            create_provider(client.app.state.config.get())


def test_settings_validation_error_is_readable(data_dir):
    client, _, _ = make_client(data_dir)
    with client:
        r = client.put("/api/settings", json={"temperature": 50}, headers=H)
        assert r.status_code == 422 and "temperature" in r.json()["detail"]
        r = client.get("/api/settings", headers=H).json()
        assert r["paths"]["database"].endswith("jarvis.db")


# ------------------------------------------------------------------ chat
def test_chat_streams_and_saves_history(data_dir):
    client, provider, _ = make_client(data_dir, FakeProvider(reply="Use **pytest** for tests."))
    with client:
        events = stream_events(client, {"message": "How do I test Python?", "mode": "test", "stream_id": "s1"})
        types = [e["type"] for e in events]
        assert types[0] == "meta" and types[-1] == "done" and "content" in types
        text = "".join(e["text"] for e in events if e["type"] == "content")
        assert "pytest" in text
        conv_id = events[0]["conversation_id"]
        hist = client.get(f"/api/conversations/{conv_id}", headers=H).json()
        assert [m["role"] for m in hist["messages"]] == ["user", "assistant"]
        system = provider.calls[0][0][0]["content"]
        assert "Testing & debugging" in system and "Never claim tests pass" in system
        # second turn includes history
        stream_events(client, {"message": "And for JavaScript?", "conversation_id": conv_id, "stream_id": "s2"})
        roles = [m["role"] for m in provider.calls[1][0]]
        assert roles == ["system", "user", "assistant", "user"]


def test_chat_uses_project_files_and_hides_secrets(data_dir, project):
    client, provider, app = make_client(data_dir)
    with client:
        r = client.post("/api/project/open", json={"path": str(project)}, headers=H)
        assert r.status_code == 200
        app.state.projects.wait_for_index()
        events = stream_events(client, {"message": "How does divide handle zero?", "attached": ["config.py"],
                                        "stream_id": "s3"})
        sources = next(e for e in events if e["type"] == "sources")
        paths = {s["path"] for s in sources["sources"]}
        assert "src/calculator.py" in paths and "config.py" in paths
        assert sources["redactions"] >= 2
        sent = provider.calls[0][0][-1]["content"]
        assert "ZeroDivisionError" in sent
        assert "hunter2pass" not in sent and "letmein123" not in sent and "super-secret-value" not in sent
        activity = client.get("/api/activity", headers=H).json()
        assert any(a["kind"] == "files_shared" for a in activity)


def test_chat_reports_model_not_running(data_dir):
    client, _, _ = make_client(data_dir, FakeProvider(reachable=False))
    with client:
        events = stream_events(client, {"message": "hi", "stream_id": "s4"})
        err = events[-1]
        assert err["type"] == "error" and err["code"] == "not_running" and err["hint"]


def test_chat_can_be_cancelled(data_dir):
    import threading
    provider = FakeProvider(reply=" ".join(["word"] * 400), delay=0.02)
    client, _, _ = make_client(data_dir, provider)
    with client:
        threading.Timer(0.5, lambda: client.post("/api/chat/cancel", json={"stream_id": "c1"}, headers=H)).start()
        start = time.time()
        events = stream_events(client, {"message": "long please", "stream_id": "c1"})
        assert events[-1]["type"] == "stopped"
        assert time.time() - start < 6
        conv = events[0]["conversation_id"]
        msgs = client.get(f"/api/conversations/{conv}", headers=H).json()["messages"]
        assert msgs[-1]["role"] == "assistant" and msgs[-1]["stopped"] is True


# ------------------------------------------------------------------ tasks
def test_task_endpoints_and_ai_helpers(data_dir):
    plan_json = None
    provider = FakeProvider(json_reply='{"steps": [{"title": "Outline", "description": "List sections"}, '
                                       '{"title": "Draft", "description": "Write it"}], "notes": "Keep it short"}')
    client, _, _ = make_client(data_dir, provider)
    with client:
        t = client.post("/api/tasks", json={"title": "Write blog post", "priority": "high", "due_date": "2026-11-01"},
                        headers=H).json()
        assert client.post("/api/tasks", json={"title": ""}, headers=H).status_code == 422
        bd = client.post(f"/api/tasks/{t['id']}/breakdown", headers=H).json()
        assert [s["title"] for s in bd["steps"]] == ["Outline", "Draft"] and bd["notes"] == "Keep it short"
        subs = client.post(f"/api/tasks/{t['id']}/subtasks", json={"steps": bd["steps"]}, headers=H).json()
        assert all(s["parent_id"] == t["id"] for s in subs)
        upd = client.patch(f"/api/tasks/{t['id']}", json={"status": "done"}, headers=H).json()
        assert upd["status"] == "done" and upd["completed_at"]
        assert len(client.get("/api/tasks?include_done=false", headers=H).json()) == 2
        provider.json_reply = json.dumps({"order": [{"id": subs[1]["id"], "reason": "do first"}, {"id": 999, "reason": "x"}],
                                          "advice": "Start small"})
        plan = client.post("/api/tasks/plan", headers=H).json()
        assert plan["order"][0]["id"] == subs[1]["id"] and len(plan["order"]) == 2  # unknown id dropped, missing added
        exported = client.get("/api/tasks/export", headers=H)
        assert "attachment" in exported.headers["content-disposition"] and len(exported.json()["tasks"]) == 3
        assert client.delete(f"/api/tasks/{t['id']}", headers=H).status_code == 200
        assert client.get("/api/tasks", headers=H).json() == []
        assert plan_json is None


def test_breakdown_reports_bad_model_output(data_dir):
    client, _, _ = make_client(data_dir, FakeProvider(json_reply="sorry, I can't do JSON"))
    with client:
        t = client.post("/api/tasks", json={"title": "x"}, headers=H).json()
        r = client.post(f"/api/tasks/{t['id']}/breakdown", headers=H)
        assert r.status_code == 503 and r.json()["code"] == "bad_output"


# ------------------------------------------------------------------ project, changes, commands
def test_project_endpoints(data_dir, project, tmp_path):
    client, _, app = make_client(data_dir)
    with client:
        assert client.get("/api/project/tree", headers=H).status_code == 400  # no project yet
        assert client.post("/api/project/open", json={"path": str(tmp_path / "nope")}, headers=H).status_code == 404
        info = client.post("/api/project/open", json={"path": str(project)}, headers=H).json()
        assert info["open"] and info["name"] == "sample-project"
        app.state.projects.wait_for_index()
        tree = client.get("/api/project/tree", headers=H).json()
        assert {"src", ".env"} <= {e["name"] for e in tree}
        assert client.get("/api/project/file", params={"path": ".env"}, headers=H).status_code == 403
        assert client.get("/api/project/file", params={"path": "../x"}, headers=H).status_code == 403
        f = client.get("/api/project/file", params={"path": "src/calculator.py"}, headers=H).json()
        assert "def divide" in f["content"]
        hits = client.get("/api/project/search", params={"q": "divide"}, headers=H).json()
        assert hits[0]["path"] == "src/calculator.py"
        proj = client.get("/api/project", headers=H).json()
        assert proj["index"]["state"] == "ready" and proj["overview"]["languages"]


def test_change_flow_over_api(data_dir, project):
    client, _, app = make_client(data_dir)
    with client:
        client.post("/api/project/open", json={"path": str(project)}, headers=H)
        p = client.post("/api/changes", json={"path": "src/hello.py", "content": "print('hi')\n"}, headers=H).json()
        assert p["status"] == "pending" and not (project / "src/hello.py").exists()
        r = client.post(f"/api/changes/{p['id']}/apply", json={}, headers=H)
        assert r.status_code == 200 and (project / "src/hello.py").exists()
        r = client.post(f"/api/changes/{p['id']}/undo", json={}, headers=H)
        assert r.status_code == 200 and not (project / "src/hello.py").exists()
        d = client.post("/api/changes", json={"path": "README.md", "delete": True}, headers=H).json()
        r = client.post(f"/api/changes/{d['id']}/apply", json={}, headers=H)
        assert r.status_code == 400 and (project / "README.md").exists()
        listing = client.get("/api/changes", headers=H).json()
        assert {c["status"] for c in listing} == {"undone", "pending"}
        kinds = [a["kind"] for a in client.get("/api/activity", headers=H).json()]
        assert "change_applied" in kinds and "change_undone" in kinds


def test_command_approval_rules(data_dir, project):
    client, _, _ = make_client(data_dir)
    with client:
        client.post("/api/project/open", json={"path": str(project)}, headers=H)
        chk = client.post("/api/commands/check", json={"command": "pip install requests"}, headers=H).json()
        assert chk["level"] == "danger" and chk["reasons"]
        r = client.post("/api/commands/run", json={"command": "pip install requests", "approved": True}, headers=H)
        assert r.status_code == 400 and "risk" in r.json()["detail"]
        r = client.post("/api/commands/run", json={"command": "python --help-me"}, headers=H)
        assert r.status_code == 400 and "approval" in r.json()["detail"]
        r = client.post("/api/commands/run", json={"command": "echo a && echo b", "approved": True}, headers=H)
        assert r.status_code == 400 and "&&" in r.json()["detail"]
        # safe command runs with one click
        run = client.post("/api/commands/run", json={"command": "python --version"}, headers=H).json()
        for _ in range(100):
            run = client.get(f"/api/commands/{run['id']}", headers=H).json()
            if run["status"] != "running":
                break
            time.sleep(0.1)
        assert run["status"] == "finished" and "Python" in run["output"]
        time.sleep(0.2)
        kinds = [a["kind"] for a in client.get("/api/activity", headers=H).json()]
        assert "command_started" in kinds and "command_finished" in kinds
