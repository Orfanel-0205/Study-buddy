"""Flashcards with spaced repetition.

Spaced repetition means reviewing a card right before you would forget it: cards you
know well come back after longer and longer gaps, cards you miss come back soon. Jarvis
uses a simplified version of the SM-2 method (the one behind Anki):

* Again - you didn't remember: the card comes back today (in this session) and tomorrow.
* Hard  - remembered with difficulty: a slightly longer gap, and the card gets "harder".
* Good  - remembered: the gap grows (1 day, 3 days, then about x2.5 each time).
* Easy  - effortless: a bigger jump, and the card gets "easier".

Everything is stored locally in jarvis.db.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .db import Database, now_iso

Grade = Literal["again", "hard", "good", "easy"]
MIN_EASE = 1.3


class DeckIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field("", max_length=2000)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty")
        return v


class CardIn(BaseModel):
    front: str = Field(min_length=1, max_length=2000)
    back: str = Field(min_length=1, max_length=4000)

    @field_validator("front", "back")
    @classmethod
    def _text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Cannot be empty")
        return v


class StudyNotFound(LookupError):
    pass


def schedule(card: dict, grade: Grade, today: date) -> dict:
    """Return the card's new ease, interval (days), reps, lapses and due date."""
    ease, interval, reps, lapses = card["ease"], card["interval"], card["reps"], card["lapses"]
    if grade == "again":
        reps, lapses, interval = 0, lapses + 1, 1
        ease = max(MIN_EASE, ease - 0.2)
    elif grade == "hard":
        interval = 1 if reps == 0 else max(interval + 1, round(interval * 1.2))
        ease = max(MIN_EASE, ease - 0.15)
        reps += 1
    elif grade == "good":
        interval = 1 if reps == 0 else 3 if reps == 1 else max(interval + 1, round(interval * ease))
        reps += 1
    else:  # easy
        interval = 3 if reps == 0 else max(interval + 2, round(interval * ease * 1.3))
        ease += 0.15
        reps += 1
    return {"ease": round(ease, 3), "interval": interval, "reps": reps, "lapses": lapses,
            "due": (today + timedelta(days=interval)).isoformat()}


def next_intervals(card: dict, today: date) -> dict[str, int]:
    """How many days until the card returns for each answer (shown on the grade buttons)."""
    return {g: schedule(card, g, today)["interval"] for g in ("again", "hard", "good", "easy")}


class StudyStore:
    def __init__(self, db: Database):
        self.db = db

    # ---- decks
    def decks(self, today: date | None = None) -> list[dict]:
        today_s = (today or date.today()).isoformat()
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT d.*, COUNT(c.id) AS cards,
                          SUM(CASE WHEN c.id IS NOT NULL AND c.due <= ? THEN 1 ELSE 0 END) AS due,
                          SUM(CASE WHEN c.id IS NOT NULL AND c.reps = 0 AND c.last_reviewed IS NULL THEN 1 ELSE 0 END) AS new
                   FROM decks d LEFT JOIN cards c ON c.deck_id = d.id
                   GROUP BY d.id ORDER BY d.updated_at DESC, d.id DESC""", (today_s,)).fetchall()
        return [{**dict(r), "due": r["due"] or 0, "new": r["new"] or 0} for r in rows]

    def deck(self, deck_id: int) -> dict:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
        if not row:
            raise StudyNotFound(f"Deck {deck_id} does not exist")
        return dict(row)

    def create_deck(self, data: DeckIn) -> dict:
        now = now_iso()
        with self.db.connect() as conn:
            cur = conn.execute("INSERT INTO decks (name, description, created_at, updated_at) VALUES (?, ?, ?, ?)",
                               (data.name, data.description, now, now))
            deck_id = cur.lastrowid
        return self.deck(deck_id)

    def update_deck(self, deck_id: int, data: DeckIn) -> dict:
        self.deck(deck_id)
        with self.db.connect() as conn:
            conn.execute("UPDATE decks SET name = ?, description = ?, updated_at = ? WHERE id = ?",
                         (data.name, data.description, now_iso(), deck_id))
        return self.deck(deck_id)

    def delete_deck(self, deck_id: int) -> dict:
        deck = self.deck(deck_id)
        with self.db.connect() as conn:
            conn.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
        return deck

    # ---- cards
    def cards(self, deck_id: int) -> list[dict]:
        self.deck(deck_id)
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM cards WHERE deck_id = ? ORDER BY id", (deck_id,)).fetchall()
        return [dict(r) for r in rows]

    def card(self, card_id: int) -> dict:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        if not row:
            raise StudyNotFound(f"Card {card_id} does not exist")
        return dict(row)

    def add_cards(self, deck_id: int, cards: list[CardIn], today: date | None = None) -> list[dict]:
        self.deck(deck_id)
        now = now_iso()
        due = (today or date.today()).isoformat()  # new cards are ready to learn right away
        ids = []
        with self.db.connect() as conn:
            for c in cards:
                cur = conn.execute(
                    "INSERT INTO cards (deck_id, front, back, due, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (deck_id, c.front, c.back, due, now, now))
                ids.append(cur.lastrowid)
            conn.execute("UPDATE decks SET updated_at = ? WHERE id = ?", (now, deck_id))
        return [self.card(i) for i in ids]

    def update_card(self, card_id: int, data: CardIn) -> dict:
        self.card(card_id)
        with self.db.connect() as conn:
            conn.execute("UPDATE cards SET front = ?, back = ?, updated_at = ? WHERE id = ?",
                         (data.front, data.back, now_iso(), card_id))
        return self.card(card_id)

    def delete_card(self, card_id: int) -> None:
        self.card(card_id)
        with self.db.connect() as conn:
            conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))

    def due(self, deck_id: int | None = None, today: date | None = None, limit: int = 200,
            within_days: int = 0) -> list[dict]:
        """Cards due today (or within the next `within_days` days, so a phone can review offline)."""
        today = today or date.today()
        query = "SELECT * FROM cards WHERE due <= ?"
        params: list = [(today + timedelta(days=within_days)).isoformat()]
        if deck_id is not None:
            self.deck(deck_id)
            query += " AND deck_id = ?"
            params.append(deck_id)
        query += " ORDER BY (reps = 0), due, id LIMIT ?"  # reviews first, then new cards
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [{**dict(r), "next": next_intervals(dict(r), today)} for r in rows]

    def review(self, card_id: int, grade: Grade, reviewed_on: date | None = None) -> dict:
        card = self.card(card_id)
        day = reviewed_on or date.today()
        new = schedule(card, grade, day)
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE cards SET ease = ?, interval = ?, reps = ?, lapses = ?, due = ?, last_reviewed = ?, "
                "updated_at = ? WHERE id = ?",
                (new["ease"], new["interval"], new["reps"], new["lapses"], new["due"], day.isoformat(), now_iso(), card_id))
            deck = conn.execute("SELECT uid FROM decks WHERE id = ?", (card["deck_id"],)).fetchone()
            conn.execute("INSERT INTO study_reviews (card_uid, deck_uid, grade, reviewed_at) VALUES (?, ?, ?, ?)",
                         (card.get("uid") or "", deck["uid"] if deck else "", grade, now_iso()))  # for progress charts
        return self.card(card_id)
