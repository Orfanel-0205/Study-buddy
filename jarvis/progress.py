"""Your progress, counted separately for studying and for developing.

Studying:   flashcard reviews, practice exercises checked/solved, questions asked in Study / Explain /
            Coach mode, and tasks marked as Studying.
Developing: tasks marked as Developing (or with a project), code changes applied, test and build runs,
            and questions asked in the SDLC modes (requirements, design, implementation, testing, release).

Everything comes from what Jarvis already stores; nothing is estimated. Flashcard reviews and tasks
sync between the laptop and the phone, so both show up on either; practice, commands and chats are
counted on the device where they happened.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from .db import Database
from .learn.exercises import EXERCISES

STUDY_MODES = {"study", "explain", "coach"}
DEV_MODES = {"requirements", "rules", "design", "implement", "test", "release"}
GOOD_GRADES = {"good", "easy"}


def _local_day(ts: str | None) -> date | None:
    if not ts:
        return None
    try:
        when = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone().date()


def _streak(active_days: set[date], today: date) -> int:
    """Days in a row with activity, ending today (or yesterday, so the morning doesn't break it)."""
    day = today if today in active_days else today - timedelta(days=1)
    n = 0
    while day in active_days:
        n += 1
        day -= timedelta(days=1)
    return n


def progress(db: Database, days: int = 30, today: date | None = None) -> dict:
    days = max(7, min(int(days), 365))
    today = today or date.today()
    start = today - timedelta(days=days - 1)
    since = datetime.combine(start - timedelta(days=1), datetime.min.time()).astimezone().astimezone(timezone.utc).isoformat()
    span = [start + timedelta(days=i) for i in range(days)]

    study = defaultdict(Counter)   # day -> counts
    dev = defaultdict(Counter)
    grades: Counter = Counter()
    study_days: set[date] = set()
    dev_days: set[date] = set()
    dev_modes: Counter = Counter()
    test_runs = {"passed": 0, "failed": 0}

    with db.connect() as conn:
        # streaks look further back than the chart range
        for r in conn.execute("SELECT reviewed_at FROM study_reviews"):
            d = _local_day(r["reviewed_at"])
            if d:
                study_days.add(d)
        for r in conn.execute("SELECT grade, reviewed_at FROM study_reviews WHERE reviewed_at >= ?", (since,)):
            d = _local_day(r["reviewed_at"])
            if d and start <= d <= today:
                study[d]["reviews"] += 1
                grades[r["grade"]] += 1

        for r in conn.execute("SELECT area, project, completed_at FROM tasks WHERE status = 'done' AND completed_at IS NOT NULL"):
            d = _local_day(r["completed_at"])
            if not d:
                continue
            area = r["area"] or ("dev" if r["project"] else "")
            if area == "study":
                study_days.add(d)
                if start <= d <= today:
                    study[d]["tasks"] += 1
            elif area == "dev":
                dev_days.add(d)
                if start <= d <= today:
                    dev[d]["tasks"] += 1

        for r in conn.execute("SELECT m.mode, m.created_at FROM messages m WHERE m.role = 'user'"):
            d = _local_day(r["created_at"])
            if not d:
                continue
            if r["mode"] in STUDY_MODES:
                study_days.add(d)
                if start <= d <= today:
                    study[d]["questions"] += 1
            elif r["mode"] in DEV_MODES:
                dev_days.add(d)
                if start <= d <= today:
                    dev[d]["questions"] += 1
                    dev_modes[r["mode"]] += 1

        for r in conn.execute("SELECT kind, details, created_at FROM actions WHERE kind IN "
                              "('practice', 'change_applied', 'command_finished')"):
            d = _local_day(r["created_at"])
            if not d:
                continue
            try:
                details = json.loads(r["details"] or "{}")
            except ValueError:
                details = {}
            if r["kind"] == "practice":
                study_days.add(d)
                if start <= d <= today:
                    study[d]["practice"] += 1
            elif r["kind"] == "change_applied":
                dev_days.add(d)
                if start <= d <= today:
                    dev[d]["changes"] += 1
            else:
                dev_days.add(d)
                if start <= d <= today:
                    dev[d]["runs"] += 1
                    test_runs["passed" if details.get("exit_code") == 0 else "failed"] += 1

        for r in conn.execute("SELECT day, coding_seconds, alerts FROM focus_days WHERE day >= ?", (start.isoformat(),)):
            try:
                d = date.fromisoformat(r["day"])
            except ValueError:
                continue
            if d <= today:
                dev[d]["focus"] += r["coding_seconds"] // 60
                dev[d]["drifts"] += r["alerts"]
                if r["coding_seconds"] >= 300:
                    dev_days.add(d)
        solved = {r["exercise_id"] for r in conn.execute("SELECT exercise_id FROM practice WHERE solved_at IS NOT NULL")}
        cards_total = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        cards_learned = conn.execute("SELECT COUNT(*) FROM cards WHERE reps > 0").fetchone()[0]
        due = conn.execute("SELECT COUNT(*) FROM cards WHERE due <= ?", (today.isoformat(),)).fetchone()[0]
        open_dev = conn.execute("SELECT COUNT(*) FROM tasks WHERE status != 'done' AND parent_id IS NULL AND "
                                "(area = 'dev' OR (area = '' AND project != ''))").fetchone()[0]
        open_study = conn.execute("SELECT COUNT(*) FROM tasks WHERE status != 'done' AND parent_id IS NULL AND "
                                  "area = 'study'").fetchone()[0]

    by_language = Counter(e["language"] for e in EXERCISES)
    solved_by_language = Counter(e["language"] for e in EXERCISES if e["id"] in solved)
    week = [today - timedelta(days=i) for i in range(7)]
    reviewed = sum(grades.values())

    def series(store: dict, keys: list[str]) -> list[dict]:
        return [{"date": d.isoformat(), **{k: store[d][k] for k in keys}} for d in span]

    return {
        "days": days,
        "today": today.isoformat(),
        "study": {
            "daily": series(study, ["reviews", "practice", "questions", "tasks"]),
            "streak": _streak(study_days, today),
            "active_days": sum(1 for d in span if d in study_days),
            "reviews_week": sum(study[d]["reviews"] for d in week),
            "retention": round(100 * sum(grades[g] for g in GOOD_GRADES) / reviewed) if reviewed else None,
            "grades": {g: grades[g] for g in ("again", "hard", "good", "easy")},
            "cards": {"total": cards_total, "learned": cards_learned, "due": due},
            "exercises": {"solved": len(solved), "total": len(EXERCISES),
                          "by_language": [{"language": lang, "solved": solved_by_language[lang], "total": n}
                                          for lang, n in by_language.items()]},
            "open_tasks": open_study,
        },
        "dev": {
            "daily": series(dev, ["tasks", "changes", "runs", "questions", "focus", "drifts"]),
            "focus_week": sum(dev[d]["focus"] for d in week),
            "streak": _streak(dev_days, today),
            "active_days": sum(1 for d in span if d in dev_days),
            "tasks_week": sum(dev[d]["tasks"] for d in week),
            "test_runs": test_runs,
            "modes": [{"mode": m, "questions": dev_modes[m]} for m in ("requirements", "rules", "design", "implement", "test", "release")],
            "open_tasks": open_dev,
        },
    }
