"""Two-way sync of tasks and flashcards between two Jarvis copies (the laptop and the phone).

How it works:
* Every task, deck and card has a permanent id (uid) that both copies share, plus an
  `updated_at` time. Deleting something leaves a small record (in `deletions`).
* The phone's Jarvis regularly sends the laptop everything that changed since the last
  sync, and receives everything that changed on the laptop.
* When the same item changed on both, the newer change wins. A deletion wins over an
  older edit, and a newer edit brings a deleted item back.

Chats are not synced: each copy keeps its own conversations.
"""

from __future__ import annotations

import logging
import ssl
from pathlib import Path

import httpx

from .db import Database, now_iso

log = logging.getLogger(__name__)

TASK_FIELDS = ["uid", "title", "description", "due_date", "priority", "status", "project", "project_path",
               "notes", "position", "created_at", "updated_at", "completed_at", "area"]
DEFAULTS = {"area": ""}  # fields an older copy of Jarvis doesn't send yet
REVIEW_FIELDS = ["uid", "card_uid", "deck_uid", "grade", "reviewed_at"]
CHECKIN_FIELDS = ["uid", "at", "mood", "energy", "stress", "sleep_hours", "body", "note", "context"]
DECK_FIELDS = ["uid", "name", "description", "created_at", "updated_at"]
CARD_FIELDS = ["uid", "front", "back", "ease", "interval", "reps", "lapses", "due", "last_reviewed",
               "created_at", "updated_at"]
TABLES = {"task": "tasks", "deck": "decks", "card": "cards"}


def collect(db: Database, since: str = "") -> dict:
    """Everything that changed at or after `since` (everything when empty)."""
    with db.connect() as conn:
        tasks = conn.execute(
            f"SELECT {', '.join('t.' + f for f in TASK_FIELDS)}, p.uid AS parent_uid "
            "FROM tasks t LEFT JOIN tasks p ON p.id = t.parent_id WHERE t.updated_at >= ?", (since,)).fetchall()
        decks = conn.execute(f"SELECT {', '.join(DECK_FIELDS)} FROM decks WHERE updated_at >= ?", (since,)).fetchall()
        cards = conn.execute(
            f"SELECT {', '.join('c.' + f for f in CARD_FIELDS)}, d.uid AS deck_uid "
            "FROM cards c JOIN decks d ON d.id = c.deck_id WHERE c.updated_at >= ?", (since,)).fetchall()
        deletions = conn.execute("SELECT kind, uid, deleted_at FROM deletions WHERE deleted_at >= ?", (since,)).fetchall()
        reviews = conn.execute(f"SELECT {', '.join(REVIEW_FIELDS)} FROM study_reviews WHERE reviewed_at >= ?",
                               (since,)).fetchall()
        checkins = conn.execute(f"SELECT {', '.join(CHECKIN_FIELDS)} FROM checkins WHERE at >= ?", (since,)).fetchall()
    return {"tasks": [dict(r) for r in tasks], "decks": [dict(r) for r in decks],
            "cards": [dict(r) for r in cards], "deletions": [dict(r) for r in deletions],
            "reviews": [dict(r) for r in reviews], "checkins": [dict(r) for r in checkins]}


def apply(db: Database, changes: dict) -> dict:
    """Merge changes from the other copy. Returns how many items were written."""
    counts = {"tasks": 0, "decks": 0, "cards": 0, "deleted": 0, "reviews": 0, "checkins": 0}
    with db.connect() as conn:
        def newer(kind: str, uid: str, updated_at: str) -> bool:
            """True if the incoming version should replace what we have."""
            row = conn.execute(f"SELECT updated_at FROM {TABLES[kind]} WHERE uid = ?", (uid,)).fetchone()
            if row and row["updated_at"] >= updated_at:
                return False
            tomb = conn.execute("SELECT deleted_at FROM deletions WHERE kind = ? AND uid = ?", (kind, uid)).fetchone()
            return not (tomb and tomb["deleted_at"] >= updated_at)

        def upsert(kind: str, fields: list[str], record: dict) -> None:
            table = TABLES[kind]
            values = [record[f] if record.get(f) is not None else DEFAULTS.get(f) for f in fields]
            exists = conn.execute(f"SELECT id FROM {table} WHERE uid = ?", (record["uid"],)).fetchone()
            if exists:
                conn.execute(f"UPDATE {table} SET {', '.join(f + ' = ?' for f in fields)} WHERE id = ?", (*values, exists["id"]))
            else:
                conn.execute(f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({', '.join('?' * len(fields))})", values)
            conn.execute("DELETE FROM deletions WHERE kind = ? AND uid = ?", (kind, record["uid"]))

        for deck in changes.get("decks", []):
            if deck.get("uid") and deck.get("name") and newer("deck", deck["uid"], deck["updated_at"]):
                upsert("deck", DECK_FIELDS, deck)
                counts["decks"] += 1
        for card in changes.get("cards", []):
            deck = conn.execute("SELECT id FROM decks WHERE uid = ?", (card.get("deck_uid"),)).fetchone()
            if deck and card.get("uid") and newer("card", card["uid"], card["updated_at"]):
                upsert("card", ["deck_id", *CARD_FIELDS], {**card, "deck_id": deck["id"]})
                counts["cards"] += 1
        tasks = sorted(changes.get("tasks", []), key=lambda t: t.get("parent_uid") is not None)  # parents first
        for task in tasks:
            if task.get("uid") and task.get("title") and newer("task", task["uid"], task["updated_at"]):
                parent = conn.execute("SELECT id FROM tasks WHERE uid = ?", (task.get("parent_uid"),)).fetchone() \
                    if task.get("parent_uid") else None
                upsert("task", ["parent_id", *TASK_FIELDS], {**task, "parent_id": parent["id"] if parent else None})
                counts["tasks"] += 1
        for r in changes.get("reviews", []):  # the review history only grows: add what we don't have
            if r.get("uid") and r.get("grade") and r.get("reviewed_at"):
                cur = conn.execute(f"INSERT OR IGNORE INTO study_reviews ({', '.join(REVIEW_FIELDS)}) VALUES (?, ?, ?, ?, ?)",
                                   [r.get(f) or "" for f in REVIEW_FIELDS])
                counts["reviews"] += cur.rowcount
        for c in changes.get("checkins", []):  # check-ins are never edited: add the ones we don't have
            if c.get("uid") and c.get("at") and all(isinstance(c.get(k), int) for k in ("mood", "energy", "stress")):
                cur = conn.execute(f"INSERT OR IGNORE INTO checkins ({', '.join(CHECKIN_FIELDS)}) VALUES ({', '.join('?' * len(CHECKIN_FIELDS))})",
                                   [c.get(f) if c.get(f) is not None or f == "sleep_hours" else "" for f in CHECKIN_FIELDS])
                counts["checkins"] += cur.rowcount
        for d in changes.get("deletions", []):
            kind, uid = d.get("kind"), d.get("uid")
            if kind not in TABLES or not uid:
                continue
            row = conn.execute(f"SELECT updated_at FROM {TABLES[kind]} WHERE uid = ?", (uid,)).fetchone()
            if row and row["updated_at"] <= d["deleted_at"]:
                conn.execute(f"DELETE FROM {TABLES[kind]} WHERE uid = ?", (uid,))
                counts["deleted"] += 1
            if not row or row["updated_at"] <= d["deleted_at"]:
                conn.execute("INSERT OR REPLACE INTO deletions (kind, uid, deleted_at) VALUES (?, ?, ?)",
                             (kind, uid, d["deleted_at"]))
    return counts


# ------------------------------------------------------------------ peer state
def state(db: Database, peer: str) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM sync_state WHERE peer = ?", (peer,)).fetchone()
    return dict(row) if row else {"peer": peer, "last_pull": "", "last_push": "", "last_ok": "", "last_error": ""}


def save_state(db: Database, peer: str, **fields) -> None:
    current = {**state(db, peer), **fields}
    with db.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO sync_state (peer, last_pull, last_push, last_ok, last_error) "
                     "VALUES (?, ?, ?, ?, ?)", (peer, current["last_pull"], current["last_push"],
                                                current["last_ok"], current["last_error"]))


# ------------------------------------------------------------------ the phone side
async def sync_with(db: Database, url: str, token: str, ca_file: Path | None,
                    transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Send local changes to the laptop at `url` and bring back its changes."""
    peer = url.rstrip("/")
    st = state(db, peer)
    started = now_iso()
    outgoing = collect(db, st["last_push"])
    verify: ssl.SSLContext | bool = ssl.create_default_context(cafile=str(ca_file)) if ca_file else True
    try:
        async with httpx.AsyncClient(verify=verify, timeout=httpx.Timeout(30, connect=4), trust_env=False,
                                     transport=transport) as client:
            r = await client.post(peer + "/api/sync", json={"since": st["last_pull"], "changes": outgoing},
                                  headers={"Authorization": "Bearer " + token})
        if r.status_code == 401:
            raise RuntimeError("The laptop no longer accepts this phone (it was removed). Pair again.")
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        save_state(db, peer, last_error=str(exc) or exc.__class__.__name__)
        raise
    counts = apply(db, data["changes"])
    save_state(db, peer, last_pull=data["server_time"], last_push=started, last_ok=now_iso(), last_error="")
    sent = {k: len(v) for k, v in outgoing.items()}
    return {"sent": sent, "received": counts}
