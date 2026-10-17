---
title: Hackathons: plan, build, pitch and win
summary: How to prepare for a hackathon, pick and scope a problem, split roles, plan the hours, build one polished demo path, pitch it, and learn from a loss.
tags: hackathon, hackathons, pitch, demo, judging, criteria, team, roles, mvp, timeline, presentation, slides
order: 12
---

# Hackathons: plan, build, pitch and win

Judges see dozens of projects in a few hours. They remember **a clear problem, a demo that works,
and a confident story**, not how many features you built. Use **Build → Hackathon** in Jarvis to turn
this into a timed plan with tasks.

## Before the event

- **Read the rules and judging criteria** (innovation, impact, technical difficulty, design, presentation…). Plan for them.
- **Know your stack.** Use what the team already knows; a hackathon is not the time to learn a new framework.
- **Prepare a starter**: a repo with login, database and deploy already working (that's allowed in most events; check the rules).
- **Create accounts and API keys** in advance (hosting, maps, payments sandbox, AI API).
- Agree on Git habits: small commits, one person merges, `main` always runs.
- Sleep. Tired teams make demo-breaking mistakes at 3 am.

## Picking the problem

- **One user, one painful problem, one moment.** "Small restaurants can't update menu prices online quickly" beats "a platform for restaurants".
- Check the theme and the sponsors' APIs: using a sponsor's tool well can win side prizes.
- Ask: can we show the value in **under 2 minutes**?

## Roles (for a team of 3)

| Role | Owns |
|---|---|
| Backend + data | API, database, integrations, the demo data |
| Frontend + design | screens of the demo path, looks on the projector |
| Pitch lead + QA | the story, slides, research for impact numbers, testing the demo path again and again |

Everyone codes when needed; the pitch lead starts the slides by the halfway point.

## The timeline (24 hours)

| When | What |
|---|---|
| 0-1.5 h | Problem, demo flow on paper, roles |
| 1.5-3 h | Setup: repo, hosting, keys, split tasks |
| 3-13 h | Build the **happy path end to end**, ugly first |
| 13-17 h | Make it real: fix demo-path bugs, deploy, test on another device |
| ~17 h | **Feature freeze**: record a backup demo video |
| 18-22 h | Slides, rehearse 3 times with a timer, prepare Q&A |
| 22-24 h | Submit early, present |

## Building

- Demo path first, edge cases never (during the event).
- Fake what the judges won't check: sample data, a demo login, hard-coded settings.
- Deploy early (by the halfway point), so "it worked on my laptop" never happens on stage.
- Keep a list of "nice to have" ideas instead of building them; mention them as next steps.

## The pitch (3-5 minutes)

1. **Hook:** a real person and a real problem (a number or a quick story).
2. **Why now / why existing options fail.**
3. **Your solution** in one sentence.
4. **Live demo** of the single flow (have the backup video ready).
5. **Impact:** who benefits and how much; evidence (a quick survey, an interview quote).
6. **Tech** in one line (judges like knowing it's real, not slides).
7. **What's next** and **the team**.

Answer questions honestly: "We haven't solved that yet; here's how we would."

## After a loss

- Ask the judges or organizers for feedback; it's the fastest way to improve.
- Write a short retro: what to keep, what to change, one thing to practise (often the pitch).
- Put the project on GitHub with a good README and screenshots; it's still portfolio work.
- Losing a hackathon is information about one weekend, not a verdict on you.
