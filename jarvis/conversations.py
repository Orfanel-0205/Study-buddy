"""Chat history, stored locally in jarvis.db."""

from __future__ import annotations

import json

from .db import Database, now_iso


class ConversationNotFound(LookupError):
    pass


class ConversationStore:
    def __init__(self, db: Database):
        self.db = db

    def create(self, title: str = "New chat", mode: str = "general", project_path: str = "") -> dict:
        now = now_iso()
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO conversations (title, mode, project_path, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (title[:120] or "New chat", mode, project_path, now, now),
            )
            conv_id = cur.lastrowid
        return self.get(conv_id)

    def get(self, conv_id: int) -> dict:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if not row:
            raise ConversationNotFound(f"Conversation {conv_id} does not exist")
        return dict(row)

    def list(self, limit: int = 200) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def rename(self, conv_id: int, title: str) -> dict:
        self.get(conv_id)
        with self.db.connect() as conn:
            conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (title[:120], conv_id))
        return self.get(conv_id)

    def delete(self, conv_id: int) -> None:
        self.get(conv_id)
        with self.db.connect() as conn:
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))

    def messages(self, conv_id: int) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conv_id,)
            ).fetchall()
        return [{**dict(r), "sources": json.loads(r["sources"] or "[]"),
                 "images": json.loads(r["images"] or "[]"), "stopped": bool(r["stopped"])} for r in rows]

    def add_message(self, conv_id: int, role: str, content: str, *, mode: str = "general",
                    sources: list | None = None, model: str = "", stopped: bool = False,
                    images: list[str] | None = None) -> dict:
        now = now_iso()
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, mode, sources, model, "
                "stopped, images, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (conv_id, role, content, mode, json.dumps(sources or []), model, int(stopped),
                 json.dumps(images or []), now),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ?, mode = ? WHERE id = ?", (now, mode, conv_id)
            )
            msg_id = cur.lastrowid
            row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        return {**dict(row), "sources": sources or [], "images": images or [], "stopped": stopped}
