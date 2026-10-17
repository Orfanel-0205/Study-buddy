"""Activity log: a record of what Jarvis did, so you can review what changed.

Logged: projects opened, files sent to the model, proposed/applied/undone file
changes, commands run (with exit codes), task changes and settings changes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from .db import Database, now_iso

log = logging.getLogger(__name__)


class ActivityLog:
    def __init__(self, db: Database, session_id: str | None = None):
        self.db = db
        self.session_id = session_id or datetime.now().strftime("%Y%m%d-%H%M%S")

    def record(self, kind: str, summary: str, **details) -> None:
        try:
            with self.db.connect() as conn:
                conn.execute(
                    "INSERT INTO actions (session_id, kind, summary, details, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (self.session_id, kind, summary, json.dumps(details, default=str), now_iso()),
                )
        except Exception:  # the log must never break the action it describes
            log.exception("Could not write activity record")

    def list(self, *, current_session_only: bool = True, limit: int = 500) -> list[dict]:
        query = "SELECT * FROM actions"
        params: list = []
        if current_session_only:
            query += " WHERE session_id = ?"
            params.append(self.session_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [{**dict(r), "details": json.loads(r["details"] or "{}")} for r in rows]
