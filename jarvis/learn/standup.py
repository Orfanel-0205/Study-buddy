"""A daily stand-up note (yesterday / today / blockers) drafted from your tasks, without a model."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def _label(task: dict, by_id: dict[int, dict]) -> str:
    parent = by_id.get(task.get("parent_id") or 0)
    text = f"{parent['title']}: {task['title']}" if parent else task["title"]
    return text + (f" [{task['project']}]" if task.get("project") else "")


def standup(tasks: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now().astimezone()
    today = now.date()
    # "Yesterday" means the last working day: on Monday, look back to Friday.
    days_back = 3 if today.weekday() == 0 else 1
    since = datetime.combine(today - timedelta(days=days_back), datetime.min.time()).astimezone()
    by_id = {t["id"]: t for t in tasks}

    def completed_recently(t: dict) -> bool:
        if t["status"] != "done" or not t.get("completed_at"):
            return False
        try:
            when = datetime.fromisoformat(t["completed_at"])
        except ValueError:
            return False
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when >= since

    def due(t: dict) -> date | None:
        try:
            return date.fromisoformat(t["due_date"]) if t.get("due_date") else None
        except ValueError:
            return None

    done = [t for t in tasks if completed_recently(t)]
    open_tasks = [t for t in tasks if t["status"] != "done"]
    doing = [t for t in open_tasks if t["status"] == "in_progress"]
    due_now = [t for t in open_tasks if t["status"] != "in_progress" and due(t) and due(t) <= today]
    planned_ids = {t["id"] for t in doing + due_now}
    next_up = [t for t in open_tasks if t["status"] == "todo" and t["id"] not in planned_ids
               and t["priority"] in ("urgent", "high")][:3]
    blocked = [t for t in open_tasks if t["status"] == "blocked"]

    lines = [f"Stand-up – {today.strftime('%A %d %B')}", ""]
    lines.append("Yesterday" if days_back == 1 else "Since Friday")
    lines += [f"- Finished: {_label(t, by_id)}" for t in done] or ["- (nothing marked done in Jarvis)"]
    lines += ["", "Today"]
    today_lines = [f"- Continue: {_label(t, by_id)}" for t in doing]
    for t in due_now:
        when = "overdue" if due(t) < today else "due today"
        today_lines.append(f"- {_label(t, by_id)} ({when})")
    today_lines += [f"- Start: {_label(t, by_id)} ({t['priority']} priority)" for t in next_up]
    lines += today_lines or ["- (no tasks in progress or due; pick one from your list)"]
    lines += ["", "Blockers"]
    lines += [f"- {_label(t, by_id)}" + (f" – {t['notes'].strip().splitlines()[0][:120]}" if (t.get("notes") or "").strip() else "")
              for t in blocked] or ["- None"]
    return {"text": "\n".join(lines), "done": len(done), "today": len(today_lines), "blocked": len(blocked)}
