"""Config, tasks, conversations and activity storage."""

from __future__ import annotations

import json
from datetime import date

import pytest
from pydantic import ValidationError

from jarvis.activity import ActivityLog
from jarvis.config import ConfigStore, EndpointNotLocalError, Settings, ensure_local_endpoint, is_loopback_endpoint
from jarvis.conversations import ConversationStore
from jarvis.db import Database
from jarvis.llm import pick_model
from jarvis.tasks import TaskIn, TaskNotFound, TaskStore, TaskUpdate, smart_sort


# ------------------------------------------------------------------ config
def test_config_created_with_defaults_and_persisted(data_dir):
    store = ConfigStore(data_dir)
    assert store.path.exists()
    store.update({"model": "gemma3:4b", "temperature": 0.5})
    again = ConfigStore(data_dir).get()
    assert again.model == "gemma3:4b" and again.temperature == 0.5


def test_config_rejects_invalid_values(data_dir):
    store = ConfigStore(data_dir)
    with pytest.raises(ValidationError):
        store.update({"temperature": 9})
    with pytest.raises(ValidationError):
        store.update({"endpoint": "not a url"})
    assert store.get().temperature == 0.3  # unchanged


def test_config_recovers_from_broken_file(data_dir):
    (data_dir / "config.json").write_text(json.dumps({"temperature": "hot", "model": "x", "unknown": 1}))
    s = ConfigStore(data_dir).get()
    assert s.model == "x" and s.temperature == 0.3
    (data_dir / "config.json").write_text("{not json")
    assert ConfigStore(data_dir).get().provider == "ollama"


@pytest.mark.parametrize("url,local", [
    ("http://127.0.0.1:11434", True), ("http://localhost:8080/v1", True), ("http://[::1]:11434", True),
    ("http://127.0.0.2:1", True), ("http://192.168.1.5:11434", False), ("https://api.example.com/v1", False),
])
def test_loopback_detection(url, local):
    assert is_loopback_endpoint(url) is local


def test_remote_endpoint_blocked_unless_allowed():
    with pytest.raises(EndpointNotLocalError):
        ensure_local_endpoint(Settings(endpoint="http://10.0.0.5:11434"))
    ensure_local_endpoint(Settings(endpoint="http://10.0.0.5:11434", allow_remote_endpoint=True))


def test_pick_model_prefers_configured_then_best_installed():
    assert pick_model("mine:1b", ["gemma3:1b"]) == "mine:1b"
    assert pick_model("", ["gemma3:1b", "gemma3:4b", "qwen3:1.7b"]) == "gemma3:4b"
    assert pick_model("", ["nomic-embed-text", "custom:7b"]) == "custom:7b"
    assert pick_model("", []) == ""


# ------------------------------------------------------------------ tasks
def test_task_crud_and_persistence(data_dir):
    db_path = data_dir / "jarvis.db"
    store = TaskStore(Database(db_path))
    t = store.create(TaskIn(title="  Write report ", due_date="2026-11-01", priority="high", project="Work",
                            notes="draft first"))
    assert t["title"] == "Write report" and t["status"] == "todo"
    store.update(t["id"], TaskUpdate(status="done"))
    # a fresh store on the same file sees the change (survives restart)
    again = TaskStore(Database(db_path)).get(t["id"])
    assert again["status"] == "done" and again["completed_at"]
    store.update(t["id"], TaskUpdate(status="in_progress"))
    assert store.get(t["id"])["completed_at"] is None
    assert store.projects() == ["Work"]
    store.delete(t["id"])
    with pytest.raises(TaskNotFound):
        store.get(t["id"])


def test_task_validation(data_dir):
    with pytest.raises(ValidationError):
        TaskIn(title="   ")
    with pytest.raises(ValidationError):
        TaskIn(title="x", due_date="31/12/2026")
    with pytest.raises(ValidationError):
        TaskIn(title="x", priority="whenever")
    store = TaskStore(Database(data_dir / "jarvis.db"))
    with pytest.raises(TaskNotFound):
        store.create(TaskIn(title="child", parent_id=999))


def test_subtasks_are_deleted_with_parent(data_dir):
    store = TaskStore(Database(data_dir / "jarvis.db"))
    parent = store.create(TaskIn(title="Parent"))
    child1 = store.create(TaskIn(title="Step 1", parent_id=parent["id"]))
    child2 = store.create(TaskIn(title="Step 2", parent_id=parent["id"]))
    assert (child1["position"], child2["position"]) == (0, 1)
    store.delete(parent["id"])
    assert store.list() == []


def test_smart_sort_order():
    today = date(2026, 10, 13)
    tasks = [
        {"id": 1, "status": "todo", "priority": "low", "due_date": None, "position": 0},
        {"id": 2, "status": "todo", "priority": "medium", "due_date": "2026-10-01", "position": 0},  # overdue
        {"id": 3, "status": "done", "priority": "urgent", "due_date": None, "position": 0},
        {"id": 4, "status": "todo", "priority": "urgent", "due_date": "2026-10-30", "position": 0},
        {"id": 5, "status": "todo", "priority": "urgent", "due_date": "2026-10-20", "position": 0},
    ]
    assert [t["id"] for t in smart_sort(tasks, today)] == [2, 5, 4, 1, 3]


# ------------------------------------------------------------------ conversations & activity
def test_conversations_and_activity(data_dir):
    db = Database(data_dir / "jarvis.db")
    convs = ConversationStore(db)
    c = convs.create("Hello", "explain")
    convs.add_message(c["id"], "user", "What is an API?", mode="explain")
    convs.add_message(c["id"], "assistant", "An API is...", sources=[{"path": "a.py"}], model="m", stopped=True)
    msgs = convs.messages(c["id"])
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["sources"] == [{"path": "a.py"}] and msgs[1]["stopped"] is True
    convs.delete(c["id"])
    assert convs.list() == []

    log = ActivityLog(db, session_id="s1")
    log.record("test", "did a thing", path="x")
    ActivityLog(db, session_id="s2").record("test", "other session")
    assert [a["summary"] for a in log.list()] == ["did a thing"]
    assert len(log.list(current_session_only=False)) == 2
    assert log.list()[0]["details"] == {"path": "x"}
