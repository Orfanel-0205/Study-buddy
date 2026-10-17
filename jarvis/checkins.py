"""Check-ins: how you feel before you study or code (mood, energy, stress, sleep, body), what Jarvis
suggests for the session, and the patterns over time ("metalearning": learning how you learn best).

Check-ins stay on your devices (they sync only between your own laptop and phone). They are a
self-care aid, not a medical tool.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .db import Database, now_iso

BODY = {"rested": "rested", "energetic": "energetic", "tired": "tired", "sleepy": "sleepy", "hungry": "hungry",
        "thirsty": "thirsty", "headache": "a headache", "eye_strain": "tired eyes", "sore": "sore or stiff",
        "sick": "unwell", "restless": "restless"}
SUPPORT = ("If you're going through something heavy, you don't have to carry it alone: talk to someone you trust. "
           "In the Philippines you can call the NCMH Crisis Hotline at 1553 (free, 24/7); in an emergency call 911.")


class CheckinIn(BaseModel):
    mood: int = Field(ge=1, le=5)        # 1 very low ... 5 great
    energy: int = Field(ge=1, le=5)      # 1 exhausted ... 5 full of energy
    stress: int = Field(ge=1, le=5)      # 1 calm ... 5 very stressed
    sleep_hours: float | None = Field(None, ge=0, le=24)
    body: list[str] = Field(default_factory=list, max_length=11)
    note: str = Field("", max_length=500)
    context: Literal["", "open", "focus", "study", "practice", "chat"] = ""

    @field_validator("body")
    @classmethod
    def _body(cls, v: list[str]) -> list[str]:
        return [b for b in dict.fromkeys(v) if b in BODY]


def advice(c: dict) -> dict:
    """What to do with this session, from the check-in. Simple, transparent rules."""
    body = set(json.loads(c["body"]) if isinstance(c.get("body"), str) else c.get("body") or [])
    tips: list[str] = []
    minutes, plan, kind = 25, "One focused 25-minute session, then a 5-minute break.", "steady"
    low_energy = c["energy"] <= 2 or (c.get("sleep_hours") is not None and c["sleep_hours"] < 5) or "sick" in body
    if low_energy:
        minutes, kind = 20, "gentle"
        plan = ("Your energy is low, so go gentle: 20 minutes of something light (review flashcards, tidy a task list) "
                "or rest first. New, hard topics will stick better after sleep.")
    elif c["mood"] >= 4 and c["energy"] >= 4 and c["stress"] <= 3:
        minutes, kind = 50, "deep"
        plan = "Great state for deep work: 50 minutes on your hardest task (a practice exercise or your project), then a 10-minute break."
    if c["stress"] >= 4:
        tips.append("Start with one minute of slow breathing (in 4, hold 4, out 4, hold 4), then pick the smallest next step.")
    if c["mood"] <= 2 and not low_energy:
        tips.append("Be kind to yourself today: pick one small win and count it.")
    if "hungry" in body or "thirsty" in body:
        tips.append("Eat or drink something first; your brain runs on it.")
    if "headache" in body or "eye_strain" in body:
        tips.append("Every 20 minutes, look at something 20 feet away for 20 seconds, and drink water.")
    if "sore" in body or "restless" in body:
        tips.append("Stand up and stretch for two minutes before you start, and between sessions.")
    if "sleepy" in body and not low_energy:
        tips.append("Feeling sleepy: a short walk or a 15-20 minute nap works better than more coffee.")
    support = c["mood"] == 1 or (c["mood"] <= 2 and c["stress"] >= 5)
    feelings = [f"mood {c['mood']}/5", f"energy {c['energy']}/5", f"stress {c['stress']}/5"]
    if c.get("sleep_hours") is not None:
        feelings.append(f"slept {c['sleep_hours']:g} h")
    if body:
        feelings.append("feels " + ", ".join(BODY[b] for b in body if b in BODY))
    return {"minutes": minutes, "kind": kind, "plan": plan, "tips": tips, "breathing": c["stress"] >= 4,
            "support": SUPPORT if support else "", "summary": "; ".join(feelings)}


class CheckinStore:
    def __init__(self, db: Database):
        self.db = db

    def add(self, data: CheckinIn) -> dict:
        with self.db.connect() as conn:
            cur = conn.execute("INSERT INTO checkins (at, mood, energy, stress, sleep_hours, body, note, context) "
                               "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               (now_iso(), data.mood, data.energy, data.stress, data.sleep_hours,
                                json.dumps(data.body), data.note.strip(), data.context))
            row = conn.execute("SELECT * FROM checkins WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def latest(self) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM checkins ORDER BY at DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def since(self, days: int) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM checkins WHERE at >= ? ORDER BY at", (cutoff,)).fetchall()
        return [dict(r) for r in rows]


def _day(ts: str) -> date:
    when = datetime.fromisoformat(ts)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone().date()


def insights(db: Database, days: int = 60) -> dict:
    """Patterns between how you felt and what you got done. Needs a few check-ins to say anything."""
    store = CheckinStore(db)
    rows = store.since(days)
    daily = defaultdict(list)
    for r in rows:
        daily[_day(r["at"])].append(r)
    # what got done each day (any study or development activity)
    done = defaultdict(int)
    with db.connect() as conn:
        for r in conn.execute("SELECT reviewed_at AS at FROM study_reviews"):
            done[_day(r["at"])] += 1
        for r in conn.execute("SELECT created_at AS at FROM actions WHERE kind IN ('practice', 'change_applied', 'command_finished')"):
            done[_day(r["at"])] += 3
        for r in conn.execute("SELECT completed_at AS at FROM tasks WHERE completed_at IS NOT NULL"):
            done[_day(r["at"])] += 3
        hours = defaultdict(int)
        for r in conn.execute("SELECT created_at AS at FROM actions WHERE kind IN ('practice', 'change_applied')"):
            when = datetime.fromisoformat(r["at"])
            hours[(when if when.tzinfo else when.replace(tzinfo=timezone.utc)).astimezone().hour] += 1
    series = [{"date": d.isoformat(), "mood": round(sum(x["mood"] for x in v) / len(v), 1),
               "energy": round(sum(x["energy"] for x in v) / len(v), 1),
               "stress": round(sum(x["stress"] for x in v) / len(v), 1), "done": done.get(d, 0)}
              for d, v in sorted(daily.items())]
    notes: list[str] = []
    if len(series) < 5:
        notes.append(f"Check in on {5 - len(series)} more day(s) and Jarvis will start showing your patterns.")
    else:
        def avg_done(pred):
            vals = [s["done"] for s in series if pred(s)]
            return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)
        hi, n_hi = avg_done(lambda s: s["energy"] >= 4)
        lo, n_lo = avg_done(lambda s: s["energy"] <= 2)
        if hi is not None and lo is not None and n_hi >= 2 and n_lo >= 2:
            if hi > lo * 1.3:
                notes.append(f"On high-energy days you get about {hi / max(lo, 0.5):.1f}× more done than on low-energy days. "
                             "Protect your sleep before big deadlines.")
            else:
                notes.append("You get about as much done on low-energy days as on high-energy ones: your routine carries you.")
        stressed, n_s = avg_done(lambda s: s["stress"] >= 4)
        calm, n_c = avg_done(lambda s: s["stress"] <= 2)
        if stressed is not None and calm is not None and n_s >= 2 and n_c >= 2 and calm > stressed * 1.3:
            notes.append("Stressful days are less productive for you. Breathing first and smaller steps help.")
        recent = series[-7:]
        if len(recent) >= 3 and sum(s["mood"] for s in recent) / len(recent) <= 2:
            notes.append("Your mood has been low this week. Rest, talk to someone you trust, and go easy on yourself.")
        if hours:
            best = max(hours.items(), key=lambda kv: kv[1])[0]
            notes.append(f"You solve and build most around {best:02d}:00. Schedule hard work near that time when you can.")
    return {"series": series, "notes": notes, "count": len(rows)}
