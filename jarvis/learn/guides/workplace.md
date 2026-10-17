---
title: Coping at work: workload, teamwork and when to apply for jobs
summary: How junior developers manage workload (breaking down tasks, estimating, asking for help, standups, saying no politely), avoid burnout, keep learning, and know when they're ready to apply for internships and jobs.
tags: workplace, career, workload, junior developer, standup, estimation, burnout, job, internship, apply, portfolio, interview, agile, scrum
order: 4
---

# Coping at work: workload, teamwork and when to apply for jobs

Nobody expects a junior developer to know everything. They expect you to **make steady progress,
communicate early, and learn**. Most people who struggle don't lack skill; they stay stuck too long in silence.

## Your first weeks on a team

- **Get the project running locally** and write down every step that wasn't in the README (then improve the README: an easy first PR).
- **Ask for a "good first ticket"**: a small bug fix that touches the whole flow (code → test → review → deploy).
- **Learn the map:** where requests come in (routes/controllers), where the business logic lives, how the
  database is changed (migrations), how tests are run, how code gets to production (CI/CD).
- **Find your people:** who reviews your code, who knows the database, who to ask about the product.
- **Keep a work log** (what you did, what you learned, links). It makes standups, reviews and your CV easy.

## Managing your workload

1. **One list.** Every request ("can you also…") goes into your task tracker (Jira, Trello, or Jarvis Tasks)
   so nothing lives only in your head.
2. **Break tasks down** until each step takes about ≤ 2 hours (Jarvis Tasks → *Break into steps* does this).
   A task you can't start is a task that isn't broken down enough.
3. **Prioritize:** ask "what's most important this week?" when unsure. Use urgent/important: important-but-not-urgent
   work (tests, learning) is what gets skipped and then hurts later.
4. **Limit work in progress:** 1–2 tasks at a time. Five half-finished tasks are worth zero finished ones (Lean: "partially done work" is waste).
5. **Plan the day:** pick 1–3 must-do items each morning. Protect a 90-minute block for focused coding.
6. **Timebox:** "I'll try this approach for 45 minutes." When the time is up, step back or ask.

### Estimating
- Break the work down first, estimate each piece, add them up, then **add 50–100%** for unknowns, testing and review.
- Give ranges: "2–3 days, mostly depending on how the payment API behaves."
- **Re-estimate out loud** as soon as you learn it's bigger: "This is taking longer because X. New estimate: Thursday."
  Late news is worse than bad news.

### When and how to ask for help
- **The 15-minute / 1-hour rule:** try on your own for at least 15 minutes (read the error, search the codebase,
  read the docs). If you're still stuck after about an hour with no progress, ask.
- Ask a **good question** so people can answer quickly:
  > I'm trying to **[goal]**. I expected **[X]** but got **[Y / exact error message]**.
  > I tried **[A]** and **[B]**. Here's the relevant code/log: … Could you point me in the right direction?
- Ask in the team channel rather than private messages when possible; others learn from the answer.

### Saying no (politely) when you're overloaded
> "I can do that. To fit it in, the reporting task would move to next week. Which one is more important?"

You're not refusing; you're making the trade-off visible so your lead can decide.

## Agile in real life (DevNet Module 3)

- **Standup** (≤ 15 minutes, daily): *yesterday / today / blockers*. Jarvis can draft yours from your tasks
  (Tasks → *Standup note*).
- **Sprint** (usually 2 weeks): the team commits to a set of backlog items (user stories).
- **User story:** "As a *student*, I want *to reset my password* so that *I can log in again*", plus
  **acceptance criteria** (Given/When/Then) that define "done".
- **Retrospective:** what went well, what didn't, one thing to change. Speak up; it's how processes improve.
- **Definition of done:** code + tests + review + docs + deployed (check what your team's is).

## Habits that save time

- **Read the whole error message** and the first line of your code in the stack trace.
- **Debug systematically:** reproduce → isolate (smallest failing case) → form one hypothesis → test it → fix →
  add a test so the bug can't come back.
- **Small PRs**, merged often. They're reviewed faster and break less.
- **Write it down** once you've figured something out (README, wiki, comment).
- **Don't gold-plate:** finish what was asked, ship it, then suggest improvements.
- **Automate the third repetition:** a script, an alias, a snippet.

## Avoiding burnout

- Work at a **sustainable pace** (an Agile principle, not a luxury). Long hours produce bugs.
- Take real breaks: e.g. 50 minutes focus / 10 minutes away from the screen.
- End the day with a 2-line note: where you stopped and the next step. Tomorrow-you starts faster and today-you can switch off.
- Feeling like everyone knows more than you (impostor syndrome) is normal, especially in your first year.
  Compare yourself with yourself three months ago.
- Sleep is part of debugging. Many bugs are solved the next morning in 10 minutes.

## Keep learning while working

- **30–60 minutes a day** of deliberate practice beats a weekend binge (Jarvis: flashcards + one practice exercise).
- Learn **your team's stack deeply** first, then widen ("T-shaped": deep in one area, broad elsewhere).
- Read code from good projects and your seniors' PRs; ask why they did it that way.
- Certifications such as **Cisco DevNet Associate (200-901)** help for network-automation and infrastructure
  roles; projects matter more for general developer roles.

## When are you ready to apply for internships and jobs?

You're ready to apply **earlier than you think.** If you meet about **60–70% of a posting's requirements**, apply.
Postings describe the ideal candidate, not the minimum.

**A practical readiness checklist:**
- [ ] 2–3 **finished** projects (not tutorials copied line by line) on GitHub, each with a README, screenshots
      or a demo link, and a sensible commit history.
- [ ] At least one project with a **database** and an **API** (CRUD + authentication), and one with a **frontend**.
- [ ] Some **tests** in at least one project.
- [ ] You can explain every part of your projects: why you chose that structure, what you'd improve.
- [ ] Fundamentals: Git (branch, PR, conflicts), HTTP/REST and status codes, SQL (JOIN, index), one backend
      language (Python or PHP) and JavaScript/TypeScript basics.
- [ ] Basic problem solving: arrays, strings, dictionaries/maps, loops, simple recursion (practice small exercises).

**Timing:**
- Internships/OJT: start applying **3–6 months before** you want to start; many companies recruit early.
- Graduate jobs: start applying in your **final semester**, not after graduation.
- Apply steadily (e.g. 5 good applications a week) rather than 50 in one night. Tailor the first lines of your
  CV/cover letter to each role.
- Rejections are normal and rarely personal. Ask for feedback; keep building in between.

**In interviews:** think out loud, ask clarifying questions, say "I don't know, but here's how I'd find out",
and talk about a bug you solved and what you learned.

## A weekly rhythm for a student who codes

| When | What |
|---|---|
| Every day, 15 min | Jarvis flashcards (DevNet, Git, HTTP codes) |
| Every day, 30–45 min | One practice exercise (Jarvis → Learn → Practice), rotating Python / PHP / JS / TS |
| 2–3 evenings | Build your portfolio project, one small feature per session, committed to Git |
| Weekend, 1 hour | One DevNet lab or API Lab scenario |
| Sunday, 15 min | Plan the week in Jarvis Tasks; review what you finished |
