"""Task storage. Tasks live in jarvis.db, never inside your project folders.

A task can optionally be linked to a project folder (project_path); otherwise
the free-text `project` field is just a label for grouping.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .db import Database, now_iso

Priority = Literal["low", "medium", "high", "urgent"]
Status = Literal["todo", "in_progress", "blocked", "done"]
Area = Literal["", "study", "dev"]  # studying, developing, or not set (for the progress charts)

PRIORITY_RANK = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
STATUS_RANK = {"in_progress": 0, "todo": 1, "blocked": 2, "done": 3}


def _check_date(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    date.fromisoformat(v)  # raises ValueError for anything that isn't YYYY-MM-DD
    return v


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field("", max_length=20000)
    due_date: str | None = None
    priority: Priority = "medium"
    status: Status = "todo"
    project: str = Field("", max_length=200)
    project_path: str = Field("", max_length=1000)
    notes: str = Field("", max_length=50000)
    parent_id: int | None = None
    area: Area = ""

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be empty")
        return v

    @field_validator("due_date")
    @classmethod
    def _due(cls, v: str | None) -> str | None:
        return _check_date(v)


class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = Field(None, max_length=20000)
    due_date: str | None = None
    priority: Priority | None = None
    status: Status | None = None
    project: str | None = Field(None, max_length=200)
    project_path: str | None = Field(None, max_length=1000)
    notes: str | None = Field(None, max_length=50000)
    area: Area | None = None

    @field_validator("due_date")
    @classmethod
    def _due(cls, v: str | None) -> str | None:
        return _check_date(v)


class TaskNotFound(LookupError):
    pass


class TaskStore:
    def __init__(self, db: Database):
        self.db = db

    def create(self, data: TaskIn) -> dict:
        now = now_iso()
        with self.db.connect() as conn:
            parent = conn.execute("SELECT area FROM tasks WHERE id = ?", (data.parent_id,)).fetchone() \
                if data.parent_id is not None else None
            if data.parent_id is not None and not parent:
                raise TaskNotFound(f"Parent task {data.parent_id} does not exist")
            # Steps belong to the same area as their task; a task for a software project counts as developing.
            area = data.area or (parent["area"] if parent else "") or ("dev" if data.project.strip() else "")
            position = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM tasks WHERE parent_id IS ?",
                (data.parent_id,),
            ).fetchone()[0]
            cur = conn.execute(
                """INSERT INTO tasks (title, description, due_date, priority, status, project,
                   project_path, notes, parent_id, position, created_at, updated_at, completed_at, area)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.title, data.description, data.due_date, data.priority, data.status,
                    data.project.strip(), data.project_path, data.notes, data.parent_id,
                    position, now, now, now if data.status == "done" else None, area,
                ),
            )
            task_id = cur.lastrowid
        return self.get(task_id)

    def get(self, task_id: int) -> dict:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise TaskNotFound(f"Task {task_id} does not exist")
        return dict(row)

    def update(self, task_id: int, changes: TaskUpdate) -> dict:
        current = self.get(task_id)
        fields = changes.model_dump(exclude_unset=True)
        if "title" in fields:
            fields["title"] = (fields["title"] or "").strip()
            if not fields["title"]:
                raise ValueError("Title cannot be empty")
        if not fields:
            return current
        if "status" in fields:
            if fields["status"] == "done" and current["status"] != "done":
                fields["completed_at"] = now_iso()
            elif fields["status"] != "done":
                fields["completed_at"] = None
        fields["updated_at"] = now_iso()
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self.db.connect() as conn:
            conn.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", (*fields.values(), task_id))
        return self.get(task_id)

    def delete(self, task_id: int) -> dict:
        task = self.get(task_id)
        with self.db.connect() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return task

    def list(self, *, status: str | None = None, project: str | None = None,
             include_done: bool = True) -> list[dict]:
        query = "SELECT * FROM tasks WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        elif not include_done:
            query += " AND status != 'done'"
        if project:
            query += " AND project = ?"
            params.append(project)
        with self.db.connect() as conn:
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]
        return smart_sort(rows)

    def projects(self) -> list[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT project FROM tasks WHERE project != '' ORDER BY project"
            ).fetchall()
        return [r[0] for r in rows]


def smart_sort(tasks: list[dict], today: date | None = None) -> list[dict]:
    """A practical default order that needs no AI:

    unfinished before done -> overdue first -> higher priority -> earlier due date
    -> in-progress before todo before blocked -> oldest first.
    Subtasks keep their manual position under their parent.
    """
    today = today or date.today()

    def key(t: dict):
        due = date.fromisoformat(t["due_date"]) if t.get("due_date") else None
        done = t["status"] == "done"
        overdue = bool(due and due < today and not done)
        return (
            done,
            not overdue,
            PRIORITY_RANK.get(t["priority"], 9),
            due or date.max,
            STATUS_RANK.get(t["status"], 9),
            t.get("position", 0),
            t["id"],
        )

    return sorted(tasks, key=key)
