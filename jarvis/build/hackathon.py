"""Hackathon planner: an hour-by-hour plan, checklists and a pitch outline from a few details."""

from __future__ import annotations

from datetime import datetime, timedelta

# Phases as fractions of the event, roughly what winning teams do: decide fast, build the demo path,
# freeze features early, and leave real time for the demo and pitch.
PHASES = [
    (0.00, 0.06, "Kick-off: pick ONE problem and who it's for", ["Read the judging criteria together", "Write the problem in one sentence",
     "Agree on the single demo flow (what judges will see, step by step)", "Assign roles"]),
    (0.06, 0.12, "Plan and set up", ["Draw the screens on paper/Figma", "Create the repo, branches and a README", "Set up hosting and any API keys",
     "Split the work so people don't block each other"]),
    (0.12, 0.55, "Build the demo path", ["Build the happy path end to end first, even if ugly", "Use sample data that tells a story",
     "Commit and push often; merge small changes", "Eat, drink water, take short breaks"]),
    (0.55, 0.70, "Make it work for real", ["Fix the bugs on the demo path", "Deploy it and test on another device",
     "Add the one 'wow' detail only if the core works"]),
    (0.70, 0.75, "Feature freeze", ["No new features from here", "Record a backup demo video and screenshots", "Write the README (what, how to run, team)"]),
    (0.75, 0.92, "Pitch and demo preparation", ["Slides: problem, who suffers, solution, live demo, impact, tech in one line, next steps, team",
     "Rehearse the demo three times with a timer", "Prepare answers: why this problem, how it scales, what's next"]),
    (0.92, 1.00, "Submit and present", ["Submit early (links, video, repo)", "Present calmly; show, don't tell", "Thank the judges; collect feedback"]),
]

ROLES = {
    2: ["Builder (frontend + backend)", "Builder + pitch lead (design, slides, demo script)"],
    3: ["Backend + data", "Frontend + design", "Pitch lead + testing + research"],
    4: ["Backend + data", "Frontend", "Design + slides", "Pitch lead + testing + research"],
}

CRITERIA = {
    "innovation": "Say what is new about your approach in one sentence.",
    "impact": "Name who benefits and how much (time saved, money, safety), with a source or a quick survey.",
    "technical": "Show one hard thing working live; mention the stack in one line.",
    "design": "A clean, simple flow; consistent colors and readable text on the projector.",
    "presentation": "Under the time limit, rehearsed, with a backup video if the live demo fails.",
    "feasibility": "Explain how it could launch for real: first users, cost, next 3 months.",
}


BEFORE = ["Charge laptops and phones; bring chargers and an extension cord",
          "Prepare a starter template you already know (login + database + deploy)",
          "Create accounts and API keys before the event", "Agree on Git rules (branches, who merges)",
          "Sleep well the night before"]
PITCH = ["Hook: one sentence about the problem, with a real example or number",
         "Who suffers and why current solutions fail", "Your solution in one sentence",
         "Live demo of the single flow (60-90 seconds)", "Impact and evidence", "Tech in one line",
         "What's next (pilot users, roadmap)", "Team and ask"]
CUT_LIST = ["login if the demo doesn't need it (use a demo account)", "settings pages", "perfect responsiveness on every screen",
            "a second user type", "anything the judges won't see in 3 minutes"]


def plan(name: str, start: str, hours: float, team: list[str], theme: str = "", criteria: list[str] | None = None) -> dict:
    begin = datetime.fromisoformat(start)
    hours = max(2.0, min(float(hours), 96.0))
    end = begin + timedelta(hours=hours)
    team = [m.strip() for m in team if m.strip()][:6] or ["You"]
    if len(team) == 1:
        roles = ["Everything (solo): build, design and pitch"]
    elif len(team) in ROLES:
        roles = ROLES[len(team)]
    else:
        roles = ROLES[4] + [f"Builder {i}" for i in range(5, len(team) + 1)]
    phases = []
    for a, b, title, todo in PHASES:
        s = begin + timedelta(hours=hours * a)
        e = begin + timedelta(hours=hours * b)
        phases.append({"title": title, "start": s.isoformat(timespec="minutes"), "end": e.isoformat(timespec="minutes"),
                       "hours": round(hours * (b - a), 1), "todo": todo})
    chosen = [c for c in (criteria or list(CRITERIA)) if c in CRITERIA]
    return {
        "name": name.strip() or "Hackathon", "theme": theme.strip(), "start": begin.isoformat(timespec="minutes"),
        "end": end.isoformat(timespec="minutes"), "hours": hours,
        "team": [{"name": m, "role": roles[i] if i < len(roles) else "Builder"} for i, m in enumerate(team)],
        "phases": phases,
        "criteria": [{"id": c, "tip": CRITERIA[c]} for c in chosen],
        "before": BEFORE,
        "pitch": PITCH,
        "cut_list": CUT_LIST,
    }


def offline_data() -> dict:
    """Everything the phone needs to make the same plan without Jarvis (static/build.js)."""
    return {"phases": [{"from": a, "to": b, "title": t, "todo": todo} for a, b, t, todo in PHASES], "roles": ROLES,
            "criteria": CRITERIA, "before": BEFORE, "pitch": PITCH, "cut_list": CUT_LIST}


def tasks(p: dict) -> list[dict]:
    """Task rows for Jarvis Tasks: one parent task and one step per phase, due at the phase end."""
    return [{"title": ph["title"], "due": ph["end"][:10], "description": "\n".join(f"- {t}" for t in ph["todo"])} for ph in p["phases"]]
