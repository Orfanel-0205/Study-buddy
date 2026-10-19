# Jarvis — a local AI assistant for studying, tasks and software development

Jarvis is a personal assistant that runs **entirely on your own computer**. It uses a local
language model (through [Ollama](https://ollama.com) or any OpenAI-compatible local server such as
llama.cpp or LM Studio) to help you:

- plan, analyze, design, write, test, debug and maintain software (the whole SDLC)
- understand an existing project's code and documentation
- propose code changes that you review as a diff before anything is written, with undo
- run your project's tests and builds, then debug them using the real output
- keep a local task list, break big tasks into steps, and pick a sensible order
- explain technical topics in plain language, and be your **study companion**: hints instead of
  answers, quizzes, and **flashcards with spaced repetition**, including flashcards made from a
  photo of your notes
- understand **pictures**: photos of notes, textbook pages, slides or screenshots
- **learn to code for work**: built-in guides (DevNet modules 3 and 4, API strategies, Git, file
  structure, speed optimizations and when to apply them, coping at work and when to apply for jobs),
  coding practice in **Python, JavaScript, TypeScript and PHP** checked by real tests, an offline
  **API Lab** for DevNet-style REST labs, **business rules** (policies → decision tables → tested code),
  and a **chart helper** that suggests the right chart for your data
- see your **progress**, with studying and developing tracked separately, in charts
- keep you company: a floating **study buddy** (the Jarvis robot or study-buddy stickers) and a **Bible
  verse or quote** when you open the app, picked for what you're going through
- use all of this from your **phone** over your home Wi-Fi (optional Android app; tasks and flashcard
  reviews also work offline), or on the phone alone with Jarvis running inside Termux

Your prompts, code, files and personal information never leave your computer.

> **Honest expectations:** Jarvis is only as knowledgeable as the local model you run. Small models
> (1–4B parameters) are fast but make more mistakes than large cloud models, and their knowledge has
> a cut-off date. Jarvis doesn't browse the web. It tells the model to admit uncertainty, to base
> project claims on the files it was shown, and never to claim code works without proof. Always
> review code before applying it.

---

## Quick start (Windows)

You need an internet connection **once** for steps 1 and 2. After that, Jarvis works offline.

1. **Install Python packages** (Python 3.10+). In a terminal in this folder:

   ```powershell
   python -m pip install -r requirements.txt
   ```

   *Optional but tidy:* create a private environment first with `python -m venv .venv` and then
   `.venv\Scripts\python -m pip install -r requirements.txt`. `run_jarvis.bat` will use it automatically.

2. **Install a local model** (see the next section): install Ollama, then for example

   ```powershell
   ollama pull qwen3:1.7b
   ```

3. **Start Jarvis**: double-click `run_jarvis.bat` (or run `python -m jarvis`).
   Your browser opens at `http://127.0.0.1:8765`. Press **Ctrl+C** in the terminal window to stop Jarvis.

macOS/Linux: use `./run_jarvis.sh` (or `python3 -m jarvis`).

Options: `--port 8800` (another port), `--no-browser` (don't open the browser), `--data-dir PATH`
(store data elsewhere).

---

## First-time model installation

Jarvis talks to a model server on your computer. It never downloads models by itself.

### Ollama (recommended)

1. Download and install Ollama from <https://ollama.com/download>.
2. Download a model that fits your computer:

   | Your computer | Suggested model | Download size (about) |
   |---|---|---|
   | 8 GB RAM | `ollama pull qwen3:1.7b` or `ollama pull llama3.2:3b` | 1.4 GB / 2.0 GB |
   | 16 GB RAM | `ollama pull qwen2.5-coder:7b` (good at code) or `ollama pull gemma3:4b` | 4.7 GB / 3.3 GB |
   | 32 GB+ RAM or a large GPU | `ollama pull qwen2.5-coder:14b` | 9 GB |

3. Make sure Ollama is running (Windows/macOS: start the Ollama app; Linux: `ollama serve`).
4. In Jarvis → **Settings**, choose the model, or leave **Automatic** to pick the best one installed.

The model status pill at the top shows **green** when ready. If Ollama isn't running, or the model
is missing, Jarvis shows what to do instead. Tasks, project browsing, commands and file changes keep
working without a model.

### llama.cpp, LM Studio, or another OpenAI-compatible local server

In **Settings**, set *Model server type* to **OpenAI-compatible server** and enter its local
address, including `/v1`:

- llama.cpp: `llama-server -m path\to\model.gguf --port 8080` → `http://127.0.0.1:8080/v1`
- LM Studio: start its local server → `http://127.0.0.1:1234/v1`

No API key or account is used.

### Choosing settings for your machine

- **Context size** (default 8192 tokens): how much text the model sees at once. Lower it if
  answers are slow or you run out of memory; raise it for big files if you have memory to spare.
- **Thinking** (off by default): models such as qwen3 can "reason" before answering. It's slower
  but sometimes better. You can read the reasoning in a collapsible panel. Thinking has its own budget
  (about 1,500 tokens) on top of the answer's: if a model is still thinking past it, Jarvis stops the
  thinking and answers directly. Requests to *write* code (an app, a script, a function…) skip thinking
  and get twice the answer length, because a small model can otherwise spend the whole limit thinking
  (measured: qwen3:1.7b thought for 3,000 tokens and wrote 0 lines of a to-do app; without thinking it
  wrote 189 lines in 26 seconds).
- **Continue**: an answer that reaches the length limit ends with a note and a **Continue** button,
  which carries on exactly where it stopped (in the same mode and with the same model).

---

## Offline use

| Needs internet once | Works offline afterwards |
|---|---|
| Installing Python and `requirements.txt` | Chat, all SDLC modes, explanations |
| Installing Ollama (or llama.cpp / LM Studio) | Project reading, search, code change proposals, undo |
| Downloading a model (`ollama pull …`) | Running tests/builds that don't fetch dependencies |
| | Tasks, AI task breakdown and ordering, activity log, settings |
| | Study companion, flashcards, reading pictures (image recognition) |
| | The phone app on your home Wi-Fi (no internet needed) |
| | On the phone even with no Jarvis reachable at all: see *The phone with no connection* below |

Things that inherently need the internet still need it, such as installing packages
(`npm install`, `pip install`), `git push`, or a build tool's first dependency download. Jarvis flags
those commands as risky and asks before running them.

**The phone with no connection.** When the phone app can't reach any Jarvis (the laptop is off, or
the phone's own Jarvis is still starting or stopped), it opens from the copy saved on the phone and
these keep working: Study Buddy, focus sessions and breaks (with their reminders), check-ins (saved and
sent later), tasks (changes sync later), flashcard reviews, **the guides** (all 12, with search),
**Build** (Plan an idea and Hackathon are made on the phone from a saved copy of the catalog; Decide and
Numbers need nothing), and the verse or quote. Chat, AI flashcards and checking code need a Jarvis to
answer. The saved copy (guides, catalog, verses; none of your own data) is refreshed once a day while
Jarvis is reachable. Inside the Android app, if the phone's Jarvis takes more than a few seconds to
start, the app opens from its saved copy right away and connects when Jarvis is up.

The **"Offline · local only"** badge means Jarvis itself never contacts the internet. It talks only
to the model server on this computer and refuses non-local model addresses unless you explicitly
allow one in Settings.

---

## Features

### Chat with SDLC modes
Jarvis starts in **Auto**: it reads your question and picks the mode that fits (it says which, e.g.
"Auto: answering as Business & startup advisor"). You can still pick a **mode** yourself:

| Mode | What you get |
|---|---|
| Auto (default) | Jarvis picks one of the modes below for each question (simple keyword rules, `jarvis/assistant/router.py`) |
| General | Anything: questions, planning, code |
| Business & startup advisor | A direct answer to what you asked, options compared, what to do this week, word-for-word scripts for talking to customers (Mom Test style: ask about their problems, not your idea), money broken down, risks and a stop rule. Leans on the startup and decision guides |
| Tech stack & build planner | A stack table (layer, choice, why, cost), an alternative, third-party services and APIs, a file tree, the first tables, MVP steps and risks. Uses Jarvis's built-in catalog of well-known tools so it doesn't invent services |
| Hackathon coach | Picking a problem, the demo path, roles, a pitch outline, what to cut |
| Requirements | User stories, functional and non-functional requirements, assumptions, acceptance criteria (Given/When/Then), edge cases, risks, open questions |
| Architecture & design | Simplest fitting architecture, components, data model, API design, auth, deployment, tradeoffs, diagrams (Mermaid/ASCII), implementation plan |
| Implementation | Code that follows your project's conventions, with where each change goes |
| Testing & debugging | Root-cause analysis from real errors and logs, meaningful tests |
| Release & maintenance | Docs, release notes, migrations, deployment and rollback steps, security, performance and accessibility reviews |
| Explain & learn | Plain-language explanations with examples and definitions |
| Study companion | Tutoring: simple explanations, hints step by step (full solutions only when you ask), quizzes one question at a time, summaries of your notes, language-learning help |
| Task planning | Breaking goals into small, ordered steps |
| Business rules analyst | Numbered, testable business rules, a decision table checked for gaps and conflicts, questions for the rule owner, Given/When/Then, and a tested implementation in your language |
| Career & workplace coach | Workload, stand-ups, estimates, asking for help, Git habits, when and how to apply for jobs |

**Why answers got better in 1.6:** before, a business question could land in a rigid mode (decision tables
and code), unrelated guide sections were pasted in because one word matched, and small models invented
prices. Now Auto picks the mode, guides are added only when they really answer the question, the
business/stack/hackathon modes get notes from the built-in catalog, and every mode is told to answer the
latest message directly, not repeat itself, and label any number it isn't sure of as an estimate. A
bigger model still answers better than a small one; check prices on the provider's own page.

With **Japanese** chosen in Settings, answers come in Japanese (quality depends on the model; Qwen and
Gemma models handle Japanese reasonably well).

Answers are **concise** by default. Switch to **Detailed**, or press **More detail** under any answer.
Conversations are saved locally (left sidebar). **Stop** halts an answer immediately; the partial
answer is kept and marked "stopped".

### Study companion and flashcards
- **Chat in "Study companion" mode** to learn a topic, get hints on an exercise, or say "quiz me on…".
- **Attach a picture** (📷 Image button, or paste/drag a screenshot) of your notes, a textbook page or a
  slide, and ask about it. Pictures are read by a model that can see. Jarvis picks one automatically
  (gemma3:4b if installed), even when your chat model can't see images. Pictures are stored only in your
  data folder (`images\`).
- **Study page → Make flashcards with AI:** paste notes and/or add photos. Jarvis first reads the text in
  the photo (shown to you, so you can spot misreadings), then writes question-and-answer cards. You
  check and edit them before saving.
- **Spaced repetition:** review due cards each day and answer *Again / Hard / Good / Easy*. Cards you know
  come back after longer gaps (1 day, 3 days, about ×2.5 each time); cards you miss come back soon. This is
  a simplified version of the SM-2 method that Anki uses. Keyboard on the computer: Space shows the
  answer, 1–4 grades it.
- **Import and export:** decks import from CSV or tab-separated text (Anki and Quizlet exports work: one
  card per line, front and back separated by a comma or tab) and export to CSV.
- On the **phone**: the Study tab shows due cards, and reviews work **offline**; they sync, with the day
  you reviewed, when your computer is reachable again.

### Learn: guides, coding practice and the API Lab
Open **Learn** in the sidebar (on the phone: **Study** tab → Guides / Practice / API Lab). Everything
works offline, on the computer and on Jarvis on the phone.

**Guides.** Eight built-in, searchable guides written for a student who's starting work as a developer:
| Guide | What it covers |
|---|---|
| Making apps fast: what to apply, and when | The usual speed checklist (caching, indexes, N+1 queries, compression, lazy loading, code splitting, re-renders, CDN, load balancer, connection pooling) sorted into *always*, *when you see a symptom* and *at scale*, with how to measure first |
| File structure | Python (src layout, venv), PHP (Composer, `public/`, PSR-4, Laravel), Node/Express, React, TypeScript; naming rules and the tools teams expect |
| Git | DevNet 3.3 basics, GitHub flow, commit messages, pull requests, merge conflicts step by step, undoing mistakes, secrets |
| Coping at work | First weeks, workload, estimating, when and how to ask for help, saying no politely, stand-ups, burnout, and **when you're ready to apply** for internships/jobs |
| DevNet Module 4: APIs | Sync vs async, RPC/SOAP/REST, REST constraints, requests/responses, status codes, auth vs authorization, OAuth, rate-limit algorithms, webhooks, troubleshooting, exam traps |
| DevNet Module 3: Software development | SDLC, Waterfall/Agile/Lean, Scrum, design patterns (Observer, MVC), version control, clean code, unit testing, JSON/XML/YAML |
| API strategies in practice | A reusable client, timeouts, retries with backoff, pagination, rate limits, async jobs, verifying webhooks, designing your own REST API, in all four languages |
| Business rules: from policy to tested code | Kinds of rules, writing testable rules, decision tables, where rules live in code, examples in all four languages, table-driven tests, changing rules safely |

In Chat, **Use guides** (on by default in *Study companion*, *Explain & learn* and the new *Career &
workplace coach* mode) adds the matching guide sections to your question, so even a small model answers
from correct notes. The guide sections used are shown under the answer; click one to read it.

**Starter flashcard decks.** Seven ready-made decks (about 190 cards): DevNet 4, DevNet 3, HTTP status
codes, Git, *Speed: what to apply and when*, file structure & tooling, and business rules. Adding a deck on the laptop and
on the phone is safe: each card has a fixed id, so syncing merges them into one deck.

**Coding practice.** 22 exercises (7 Python, 5 JavaScript, 4 TypeScript, 6 PHP) on the topics above:
status codes, Basic auth, pagination, token-bucket rate limiting, retries with backoff, parsing JSON,
validating request bodies, a tiny router, fixing an N+1 query. Write the code, press **Check** and your
code runs against hidden tests **on the device Jarvis runs on** (a temporary folder, a 15-second limit),
with each test's result and your program's output. **Hint** shows built-in hints first, then asks the
model to look at your code without giving the answer away. Progress and your latest code are saved.
- Needs Python (always there), Node.js 22.6+ for JavaScript/TypeScript, and PHP 8 for PHP. Jarvis shows
  what's missing. TypeScript runs through Node's type stripping, so it isn't type-checked; in real
  projects run `npx tsc --noEmit`.
- A phone connected to the laptop can read the exercises but can't run code on the laptop (by design);
  Jarvis on the phone runs it on the phone.

**API Lab.** A practice REST API (a book catalogue) built into Jarvis at `/practice/api/v1`, so the
DevNet labs work without the internet. 17 guided steps show real responses: 401 vs 403, Basic → Bearer
token, API keys, 400/404/409/415, 201 + `Location`, pagination headers (`X-Total-Count`, `Link`), a
token-bucket rate limit (429 + `Retry-After`), an asynchronous job (202, then poll), a flaky endpoint for
retries (503), signed webhooks delivered to a built-in inbox, plus SOAP and JSON-RPC for comparison. Every
request can be shown as curl, Python (`requests`), JavaScript, TypeScript or PHP code, and you can call it
from your own scripts at `http://127.0.0.1:8765/practice/api/v1` (logins: `learner`/`devnet123` read and
write, `viewer`/`viewer123` read only, header `X-API-Key: practice-key-123`). It only answers on this
device: never over Wi-Fi, and webhooks are only delivered to addresses on the same device. Data is in
memory and resets on restart (or with *Reset the practice data*).

**Stand-up note.** Tasks → **Stand-up note** drafts *yesterday / today / blockers* from your tasks
(without the model), ready to copy into your team chat.

**Business rules.** The *Business rules: from policy to tested code* guide covers the kinds of rules,
writing them so they can be tested ("₱5,000 or more", not "large orders"), decision tables, where rules
belong in code (once, on the server, returning the reason), database constraints, and table-driven tests,
with the same rule in Python, PHP, JavaScript and TypeScript. Practise with four exercises (shipping-fee
decision table, leave approval, best discount, library borrowing rules), a flashcard deck, and the
**Business rules analyst** chat mode, which turns a policy you've been given into rules, a decision table,
open questions, acceptance criteria and tested code.

**Chart helper** (Learn → Chart helper). Paste a table (CSV/TSV) or open a CSV file (read on your device,
never uploaded). Jarvis works out what each column holds (dates, numbers, categories, names/IDs) and
suggests the charts that fit, best first, each with a one-line reason and a preview: a line for a trend
over time, sorted bars to compare categories, a scatter plot (with the correlation *r*) for two numbers, a
histogram for how values spread, stat tiles for a single row. Each suggestion includes the code to make the
same chart in your own project (Python with pandas + matplotlib, JavaScript/TypeScript with Chart.js, and
how to feed it from PHP/Laravel). *Ask Jarvis what this data shows* sends a summary to the local model.

### Progress: studying and developing
**Progress** in the sidebar (on the phone: **More → Your progress**) shows two separate views, for the
last 7, 30 or 90 days:
| | What's counted |
|---|---|
| **Studying** | flashcard reviews (and how they went: Again/Hard/Good/Easy → retention), practice exercises checked and solved per language, questions in Study / Explain / Coach modes, tasks whose **Area** is *Studying* |
| **Developing** | tasks whose Area is *Developing* (or that have a project), code changes applied, test and build runs (passed vs failed), questions in the SDLC modes (Requirements, Business rules, Design, Implementation, Testing, Release) |

Each view has headline numbers (streak, this week, retention, pass rate), a daily activity chart, and a
short "what the numbers say" list (for example "Retention is 62%: review a bit every day"). Every chart has
hover details and **Show as table**, and the colours are a colorblind-safe palette checked in light and
dark mode. Nothing is estimated: it only counts what Jarvis recorded. Set a task's **Area** (task editor)
to *Studying* or *Developing* so it's counted in the right place; steps inherit their task's area.
Flashcard reviews and tasks sync with Jarvis on the phone, so both devices show them; practice, commands
and chats are counted on the device where they happened.

### Build: plan an idea, decide, check the numbers, plan a hackathon
The **Build** page (computer and phone) works without the model:
- **Plan an idea:** describe what you want to make and the language you're best at. Jarvis matches it to
  a blueprint (restaurant site with a menu admin, ordering, booking, learning app, inventory, chatbot,
  dashboard, mobile app, network automation) and shows two or three stacks with the services and APIs to
  use (with links and honest cost notes), a file structure you can copy, the first tables, what to build
  first and what to skip. **Ask Jarvis to refine this plan** sends it to the Tech stack planner.
- **Decide:** a weighted decision matrix (options x criteria, weights 1-5). It ranks the options, says when
  it's too close to call, and asks for a **pre-mortem** ("it's 6 months later and this failed: why?").
- **Numbers:** price, cost per sale, fixed and startup costs, expected sales and growth give break-even,
  payback month and a 12-month chart. It reminds you these are your guesses, not market data.
- **Hackathon:** event length, team and judging criteria give a timeline with times, roles, judging tips, a
  checklist for before the event, a pitch outline and a cut list. **Add to my tasks** creates one task
  per phase.
The four guides behind this (startup playbook, decisions, building concepts incl. the DevNet module 3-4
ideas, hackathons) are in Learn → Guides.

### Study Buddy, check-ins and focus sessions
- **Study Buddy** (the anime study companion; the robot was retired) floats in a corner. She is drawn
  from your original sticker art; the extra frames (her eyes half and fully closed, a relaxed pose with
  her eyes closed, and a pouty face with narrowed eyes and a small frown) are made from those same
  stickers by `tools/make_brand_assets.py`, so her face, hair, outfit and colours stay the same. She
  breathes, blinks every few seconds (sometimes twice), sways, tilts her head, glances toward your
  pointer, hops when her expression changes, tilts while you drag her and squashes when she lands. Tap
  her for quick actions; drag her anywhere. With your system's *reduce motion* setting she stays still.
- **Her states follow Jarvis's own:**
  | State | What she does |
  |---|---|
  | Idle | breathing, blinking, a slow sway and the odd head tilt |
  | Coding session | her laptop pose, a small typing bob, leaning toward the screen |
  | Study session | reading and writing, with a thoughtful nod every few seconds |
  | Break | relaxed, eyes peacefully closed, a music note; the session waits |
  | Session gone quiet | a playful pout (pulsing anger mark), one reminder, then she calms down |
  | Session complete | a cheerful jump with sparkles |
  | Thinking / late night | the light-bulb pose while Jarvis answers; sleepy after 11 pm |
- **Focus sessions:** tap her → *Start a coding session* or *Start a study session* (25 minutes by
  default, or what the check-in suggested). Her menu shows the time left and has *Pause/Resume*, *No
  reminders for 15 minutes*, *End the session* and a *5-minute break* (which pauses the session).
  **What counts as inactive:** no taps, typing or scrolling in Jarvis for the grace period (default
  5 minutes), or Jarvis in the background that long. Study Buddy doesn't look at other apps, your screen
  or what you type. After the grace period she pouts and sends **one** reminder (a desktop notification
  if the Jarvis tab is in the background; on Android a notification with *Snooze 15 min*, *Pause* and
  *End session*). She stays quiet until you come back ("You're back!"), and never more than one reminder
  per cooldown (default 15 minutes). Settings → Study Buddy → *Focus sessions* sets the length, grace
  period and cooldown. On Android the session runs in the app itself, so the reminder and the end of the
  session still come while Jarvis is in the background.
- **Check-in before you start** (metalearning): once a day when you open Jarvis (or before every focus
  session, or off), she asks your **mood, energy, stress, sleep and how your body feels**. Jarvis then
  suggests how long and how hard to work (gentle 20 min, steady 25, or deep 50), with tips, a one-minute
  breathing exercise when you're stressed, and a gentle pointer to support if you say you're in a bad
  place. Chat answers (coach, study, business, general) take today's check-in into account, the
  verse/quote leans on it, and Progress → **Wellbeing** shows how you felt next to what you got done.
- **Optional on Windows: Coding Focus** (Settings → Study Buddy, off by default). If you turn it on,
  Jarvis checks **only which program is in front** (e.g. `code.exe`), so time in your coding apps counts
  as activity during a session and shows in Progress → Developing. It never reads keystrokes, window
  titles, the screen or your code. Leave it off if you don't want Jarvis to know which program is open;
  sessions work the same without it (only activity in Jarvis counts). The phone has no such feature.
- **Over other apps:** *Float over other apps* puts her on the Windows desktop above your editor (a small
  always-on-top window that shows what the Jarvis page shows, blinks, and has a menu). On Android, turn
  on *Float over other apps (Android)* in More and allow **Display over other apps**: she floats over
  every other app with the same expressions and motion while the app shows a small "Study Buddy"
  notification (Android requires it). Tap her for the session controls; drag her anywhere.
- **English / Japanese:** Settings → Study Buddy → Language switches the menus, Study Buddy, check-ins,
  reminders and notifications, and makes answers come in Japanese. Other screens are still in English.
  *Read aloud* uses an offline Japanese voice for Japanese text if one is installed (Windows: Settings →
  Time & language → Speech → Add voices).

### A word for today
- **When you open Jarvis** it shows a passage from **Stoicism or philosophy** (most often), a **Bible verse**
  (King James Version, public domain), a **quote** (only well-documented attributions), or a short note from
  Jarvis. The Stoics and philosophers are quoted exactly from public-domain translations, named under each
  passage: Marcus Aurelius's *Meditations* (George Long), Epictetus's *Enchiridion* and *Discourses* (Elizabeth
  Carter, T. W. Higginson, George Long), Seneca's *Letters to Lucilius* (Richard M. Gummere), Aristotle (W. D.
  Ross), Plato's *Apology* (Benjamin Jowett), Pascal (W. F. Trotter) and Confucius (James Legge). Choose *Only
  Stoicism and philosophy* in Settings to see nothing else. It leans on the time of day (rest late at
  night), on today's check-in (peace when you're stressed, rest when your energy is low, your worth when
  the day feels heavy), on what you've been doing (long sessions, overdue tasks, failing tests, a streak)
  and on what matters most to you, which you can choose: success, security, freedom, recognition or peace.
  Recent ones aren't repeated. Choose *every time*, *once a day* or *off*, and *everything* (mostly
  philosophy), *only Stoicism and philosophy*, *only verses* or *only quotes*.
- Settings → **Study Buddy and encouragement** (phone: More). The look, check-in and verse settings are
  stored on each device, so the phone and the laptop can differ; Coding Focus settings are Jarvis's own
  (`config.json`). All of it works offline; nothing is sent anywhere.

**The app icon and stickers** come from your images. To regenerate them after changing the pictures:
```powershell
python tools/make_brand_assets.py --logo "Futuristic JARVIS AI Companion Logo.png" `
  --stickers "Anime Motivation, Coding And Study Stickers.png" "Anime Girl Study and Coding Stickers-2.png"
```
It crops the round emblem for the browser, phone and Android icons, finds and cuts out each sticker on
the transparent sheets, draws her blink frames, relaxed and pouty faces from the stickers (her eye and
mouth positions are listed at the top of the tool), and writes the
pictures for the Windows floating window and the Android app (`jarvis/static/icons`,
`jarvis/static/companion`, `android/app/res`, `android/app/assets/companion`). Then rebuild the Android app.

### Getting better answers (measured)
Small local models make mistakes, so Jarvis gives them evidence and uses each model for what it does best:
- **Real test output as evidence.** In *Testing & debugging* mode, the latest test run's real output is
  given to the model. Tick **Run tests first** to have Jarvis run the project's one-click test command
  before answering.
- **A separate model for code.** Settings → *Model for Implementation and Testing & debugging*.
- **Search by meaning** (with `nomic-embed-text`) finds relevant files that use different words than
  your question.
- **Measure it yourself:** `python evals/run_eval.py` asks each installed model the same questions
  through Jarvis's real prompts and grades the answers automatically (multiple choice, and code run
  against hidden tests). Raw answers are saved in `evals/results/` so the grading can be checked.
  After fixing the grader, `--regrade FILE` re-scores saved answers without asking the models again.

Results on this computer (28 questions, one try each, so small differences may be luck):

| Model | Project questions | …with real test output | General | Code | Total | Seconds per answer |
|---|---|---|---|---|---|---|
| qwen2.5-coder:7b | 4/8 | 7/8 | 5/6 | 4/6 | 20/28 | 4.9 |
| gemma3:4b | 4/8 | 6/8 | 6/6 | 3/6 | 19/28 | 2.1 |
| llama3.2 (3B) | 6/8 | 7/8 | 5/6 | 2/6 | 20/28 | 1.5 |
| qwen3:1.7b | 6/8 | 6/8 | 5/6 | 3/6 | 20/28 | 1.2 |
| **qwen3:1.7b + thinking** | **8/8** | **8/8** | **6/6** | **4/6** | **26/28** | 5.2 |

Search by meaning found the right file in the top 3 for 11 of 14 questions, versus 10 of 14 with keywords only.
The setup chosen from this: **gemma3:4b** for chat and study (fast, best general knowledge, can read
pictures) and **qwen3:1.7b with thinking** for Implementation and Testing & debugging.

### Project-aware help
- **Project → Browse…** (or paste a path) to choose a folder. Jarvis reads **only inside that folder**.
  It refuses `..` tricks, symlinks or junctions that point outside it, drive roots, and your whole home folder.
- Files that may contain secrets are **hidden and never read**: `.env*` (except `.env.example`),
  private keys (`*.pem`, `*.key`, `id_rsa`…), credential/secret files, `.aws/`, `.ssh/`,
  Terraform state, and more. They show with a 🔒 in the file tree. Add your own patterns in Settings.
- Text sent to the model is also scanned, and values that look like API keys, tokens, passwords
  or private keys are replaced with `[REDACTED]`.
- With **Use project files** on, Jarvis searches the project (keyword search, works offline) and
  includes the most relevant excerpts. **Attach to chat** includes a whole file. Each answer lists
  the files it used ("Used: …"). Click one to open it.

### Reviewable code changes
- On any code block in an answer: **Propose as file change…** → choose or confirm the path → see a
  **diff** and warnings → **Apply**, **Reject**, or **Decide later**.
- Jarvis warns, and requires you to tick a confirmation, when a change would delete a file,
  replace a large part of a file (for example a snippet pasted over a whole file), contain placeholders
  such as `# ... existing code ...`, or write `[REDACTED]` over your real secrets.
- Before writing, the original is backed up. **Project → Changes** lists every change, and applied
  ones can be **undone**. If the file changed after the proposal, Jarvis refuses to apply it, so
  your newer work is never overwritten.
- You can also **Edit** any file in the viewer. Your edits go through the same review.

### Running commands safely
- **Project → Commands** lists detected test/build/lint commands (npm/pnpm/yarn scripts, pytest,
  ruff, mypy, cargo, go, dotnet, Maven, Gradle, make, git status) with an explanation of each.
- Commands run inside the project folder without a shell (no pipes, redirects or `&&`), with a time
  limit and a **Stop** button.
- **Safe** commands (detected tests/builds, `git status`, `--version`) run with one click. **Unknown**
  commands need your approval. **Risky** ones need you to acknowledge the risk explicitly: deleting,
  installing packages, migrations, system settings, network access, or running inline code.
- **Ask Jarvis about this output** sends the real output to the chat in debugging mode.
- **Run…** on shell code blocks in answers opens the same approval dialog.

### Tasks
- Title, description, due date, priority, status, project label, notes, and optional subtasks.
  Optionally link a task to the open project folder. Tasks are stored separately from your projects.
- Default order: overdue → priority → due date. Overdue and due-today tasks are highlighted.
- **Break down** asks the model for ordered steps you can edit before adding them as subtasks.
- **Suggest order (AI)** asks the model for a practical order with reasons. It doesn't change your tasks.
- **Export** downloads all tasks as JSON.
- **Reminders:** due dates are highlighted while Jarvis is open. Jarvis does **not** send operating-system
  notifications, and nothing runs while it's closed.

### Activity log
**Activity** records what Jarvis did: projects opened, which files were shared with the model,
changes proposed/applied/undone, commands run (with exit codes), task and settings changes.

### Mobile app (phone access)
Use Jarvis from your phone while it runs on your computer. The model, projects and chats stay on
the computer; the phone is a remote screen for it. There are two ways to use it:

- **Android app (recommended on Android):** a real installed app with its own icon. It trusts only
  your computer's Jarvis certificate, so there are no browser warnings. See *Android app* below.
- **Web app (any phone, including iPhone):** open an address in the phone's browser and add it to
  the home screen. Steps below.

**Set up the web app (once):**
1. On the computer: **Settings → Phone access** → tick **Let my phone connect over my home Wi-Fi**.
   The first time, Windows may ask whether Python may use the network. Choose **Private networks**.
2. Click **Pair a phone**. Jarvis shows an address like `https://192.168.1.23:8766/m/` and a 6-digit code.
3. On the phone (same Wi-Fi), open that address. The browser warns that the connection isn't
   private. That's expected, because your computer made the certificate itself: tap
   *Advanced → Proceed* (Android) or *Show Details → visit this website* (iPhone).
4. Type the code. Done. Add it to your home screen (Android: ⋮ → *Add to Home screen / Install app*;
   iPhone: Share → *Add to Home Screen*) and it opens full-screen like an app.

**What the phone can do:** chat in every mode, with answers that use the project open on the computer
(the phone sees which files were used), plus conversation history, tasks (add, edit, complete,
AI breakdown, suggested order) and the model status.

**What stays on the computer:** applying file changes, running commands, opening projects, browsing
files and changing settings. A lost phone can't change your code.

**How it's protected:**
- Phone access is **off by default**. When it's off, nothing on your network can reach Jarvis.
- It uses a separate listener that accepts **HTTPS only**. Traffic is encrypted with a certificate made
  on your computer by its own small certificate authority (stored in the `phone` folder of the data
  folder). Optionally install that certificate on the phone (**More → Download Jarvis's certificate**)
  to remove the warning. Then the app can also keep its own files on the phone and open faster.
- Phones must be **paired**. Codes work once, expire after 5 minutes, and are destroyed after 5 wrong
  guesses. Pairing attempts are rate-limited. Each phone gets its own long random key, and Jarvis stores
  only a hash of it.
- The phone may only call an explicit allow-list of features. Everything else is refused, even for a
  paired phone.
- **Settings → Phone access** lists paired phones with **Remove** buttons, and removal takes effect
  immediately. Everything a phone does appears in **Activity** marked *(from phone '…')*.
- Chats and code are not stored on the phone. It keeps its pairing key and, for offline use, a copy of
  your tasks; unpairing deletes both.

**Offline on the phone:** if the computer can't be reached (it's off, Jarvis isn't running, or you're
away from home), the app still opens. The **Tasks** tab works from the copy on the phone: you can add,
edit, complete and delete tasks, and they're marked "waiting to sync". When the computer is reachable
again, the app sends those changes automatically, in order, and refreshes. If a task was deleted on the
computer meanwhile, that change is skipped. Chat and the AI features need the computer's model, so they
say so while offline. No internet connection is needed at any point; only your Wi-Fi.

### Android app
Built on your computer by two scripts (no Android Studio needed):

```powershell
python android/setup_toolchain.py          # once: downloads Java + Android build tools (~300 MB)
python android/build_apk.py --install      # builds android/dist/Jarvis-<version>.apk and installs it over USB
```

- `setup_toolchain.py` downloads Eclipse Temurin JDK 17 and Google's Android build-tools and platform
  into `%LOCALAPPDATA%\JarvisAndroidTools`, verifying checksums. Using the Android SDK pieces means
  accepting the Android SDK License, as you would in Android Studio.
- `build_apk.py` bundles **this computer's** Jarvis certificate authority and Wi-Fi address into the
  app. It signs the app with a key kept in your data folder (`android\`), so later builds install as
  updates and keep the app's data.
- **Installing:** `--install` needs USB debugging on the phone. On Xiaomi/POCO phones, also turn on
  *Install via USB* in Developer options. Without it, copy the `.apk` to the phone (for example into
  Downloads) and tap it in the Files app; Android asks you to allow installing from that app.
- **If your computer's address changes**, the app notices it can't connect and searches your Wi-Fi for
  your Jarvis. It accepts only a computer whose certificate was made by your Jarvis, then reconnects
  without re-pairing: the pairing and offline copies are kept in the app's own storage. You can also
  tap *Search the Wi-Fi for my computer* or *Change computer address* (More tab).
- **Pictures:** the 📷 buttons offer the camera or your gallery. Photos taken with the camera are saved
  in `Pictures/Jarvis` on the phone.
- `--debuggable` builds a test version whose screen can be inspected over USB. Don't use it day to day.

### Jarvis on the phone itself (no laptop needed)
The Android app can also use a copy of Jarvis that runs **on the phone**, inside the free
[Termux](https://github.com/termux/termux-app/releases) app, with small models:
`qwen3:1.7b` for chat and study, and `qwen3-vl:2b` for photos. Answers are slower and simpler than on
the laptop, but everything still stays on your device and works with no internet.

**Measured on a POCO X7 Pro (8 cores, 12 GB):** `qwen3:1.7b` writes about 11 tokens per second, so a
two-sentence answer takes about 9 seconds (plus about 6 seconds to load the model the first time).
With *thinking* on, the same model needed 3 minutes for a simple arithmetic question (about 1,500
tokens of reasoning at 8.6 tokens per second), so thinking is **off** on the phone.

**Setup (once, from the computer, phone plugged in with USB debugging on):**
1. Install Termux from its GitHub releases page (the Play Store version is outdated and can't be set up over USB).
2. Make sure Jarvis is running on the computer with phone access on, then run:
   ```powershell
   python android/setup_pocket.py
   ```
   It installs Python, Ollama and Termux's Rust compiler inside Termux (about 600 MB, so the phone
   needs internet this once; one library, pydantic-core, is compiled on the phone because Termux has no
   ready-made copy), copies Jarvis and the two models from your computer over USB (about 3 GB, no
   download), and pairs the phone's copy with the laptop's for syncing. Each step can be run again safely.
   If Android stops Jarvis on the phone while it works, run it again with `--allow-background`: that also
   turns off Android's "phantom process" limit (a system setting; the undo command is printed).
3. On the phone: **Settings → Apps → Termux → Battery saver → No restrictions**, and turn on
   **Autostart** for Termux (do the same for the Jarvis app). This matters: without it, Android
   (HyperOS especially) *freezes* Termux in the background, and Jarvis then takes connections but never
   answers ("Jarvis on this phone isn't answering yet"). Since 1.6.2 the app wakes Termux up when you come
   back and whenever Jarvis doesn't answer, and the start script replaces a Jarvis that is still stuck,
   so it recovers by itself; the setting stops it happening in the first place.
4. Open the Jarvis app. The first time it starts Jarvis on the phone, allow it to *run commands in Termux*.

**Bigger models and a fully independent phone.** Any model installed on the computer can be copied to the
phone over USB (no download), then chosen for chat, coding or photos; `--no-sync` stops the phone syncing
with the laptop, so it depends on nothing:
```powershell
python android/setup_pocket.py --copy-models gemma3:4b qwen2.5-coder:7b
python android/setup_pocket.py --chat-model gemma3:4b --code-model qwen2.5-coder:7b --no-sync
```
Bigger models answer better but more slowly and use more of the phone's memory (see the measurements
above). The phone keeps its own tasks, flashcards, chats and check-ins; nothing goes to the laptop.

**Faster answers on the phone (1.6.4).** Before writing a word, the model reads the whole prompt, and on a
phone that takes most of the wait. So Jarvis on the phone uses a *short prompt*: brief instructions, a
short guide note only when one matches, and about the last exchange (`lean_prompt`). It also uses 4 CPU
threads (`num_threads`), one per fast core. Measured on the POCO X7 Pro with qwen3:1.7b in the middle of a
conversation: the first word came after **14 s instead of 59 s**, then about 22 tokens per second.

The number of threads matters most when the Jarvis app is on screen, because the app needs some CPU too.
With Ollama's default (8 threads, every core) the model wrote **5.6 tokens per second**. With 4 threads it
wrote **16-18**: only about 20% slower than with Termux on screen, the home screen or the screen off (21-22).
2 threads was slower (13). Android doesn't otherwise slow Termux down, as long as its battery setting is
*No restrictions*. Since 1.6.5 the phone page also redraws a streaming answer at most 5 times a second
instead of once per word, which leaves a little more CPU to the model.
qwen3:1.7b answers text (it scored about the same as gemma3:4b in the evaluation and is about twice as
fast on the phone) and gemma3:4b reads photos:
```powershell
python android/setup_pocket.py --chat-model qwen3:1.7b --code-model "" --vision-model gemma3:4b --threads 4 --prompt lean
```
`--prompt full` brings back the laptop's full prompt. For long code, the laptop is much faster.

**How the app chooses** (More → *Where Jarvis runs*):
- *This phone* (default once Termux is installed; 1.6.2 also switches *Automatic* to it once, for an
  independent phone): always Jarvis on the phone, so nothing depends on the laptop.
- *Automatic*: uses the laptop when it's reachable (bigger models), otherwise starts Jarvis on the phone.
- *Laptop*: always the laptop.

**Checking code never needs the laptop:** even while the app shows the laptop's Jarvis, **Check** in
Study → Practice runs your code's tests on the phone's own Jarvis (the app starts it in Termux if needed;
the first check can take up to a minute). Code typed on the phone still never runs on the laptop. The
app allows only the practice-exercise calls for this.

**Syncing** (off with `--no-sync`): tasks and flashcard decks/cards made on either side are copied to the other whenever
the phone's Jarvis can reach the laptop (every few minutes, or tap *Sync now*). If the same item was
changed on both sides, the most recent change wins. Deletions sync too. Chats, project files and
settings are **not** synced; each side keeps its own.

**What's different on the phone:** no project folders, code changes or commands; meaning-based search
is off; answers are limited to about 4,000 tokens of context. The Learn features all work there:
setup also installs Node.js 24 and PHP 8.5 inside Termux, so practice exercises run in all four
languages on the phone, and the API Lab runs on the phone too.

**After updating Jarvis on the computer**, copy the new code to the phone with
`python android/setup_pocket.py --code-only` (no downloads; the running phone Jarvis is stopped so the
app restarts it with the new code). Jarvis on the phone listens only to the
phone itself (`127.0.0.1:8766`), never to the network. It keeps running in Termux's background
notification until you stop it there (*Exit*), which also frees the phone's memory.

### Voice (optional)
Turn on **Read aloud** in Settings to have answers spoken using **offline voices only**. Jarvis
ignores online voices. Voice *input* is not included, because browser speech recognition sends audio
to online services.

**Study Buddy's own voice (recorded once).** Study Buddy can speak her fixed lines (greetings, the
check-in, session start and end, the "still with me?" reminder, breaks, test results) in English and
Japanese. They're recorded **once** on your computer and then played from Jarvis's own files, on the
laptop and the phone (also from the floating Study Buddy), with no internet.

*Free, on your PC: VOICEVOX.* Install and open the [VOICEVOX](https://voicevox.hiroshiba.jp/) app (its
engine runs on 127.0.0.1:50021; nothing leaves your PC), then:
1. `python tools/make_companion_voice.py --samples 四国めたん 九州そら ずんだもん` writes
   *Downloads\Study Buddy voices.html* to compare characters (`--list-voicevox` lists them all).
2. `python tools/make_companion_voice.py --voicevox 四国めたん` records every line. Each line uses the
   character's style for its mood (annoyed for the reminder, whispering late at night, sweet for a
   check-in); `--speed`, `--pitch` and `--intonation` change how she talks.
3. Rebuild the Android app (`python android/build_apk.py --install`) and copy the code to the phone
   (`python android/setup_pocket.py --code-only`).

VOICEVOX reads English with a Japanese accent. VOICEVOX's terms ask for the credit
"VOICEVOX:<character>", which Settings shows, and each character has its own terms of use.

*Or ElevenLabs* (an outside service, only when you run the tool; it sends just those 34 fixed lines):
put your API key in `%APPDATA%\Jarvis\elevenlabs.key` and run the tool with no options (a paid plan is
needed for library voices), or use the free website with `--website` and `--import`.

In Settings → Study Buddy, *Study Buddy's voice* turns her voice off and *She speaks* picks the language
she speaks: the app's, Japanese or English. While she speaks, her bubble stays up with a small sound
wave. When she speaks a different language from the app, the bubble also shows her exact words under
the message. The recordings are for your own use and are kept out of the Git repository.

---

## Your data: where it lives, backup and removal

| What | Where (Windows default) |
|---|---|
| Data folder | `%APPDATA%\Jarvis` (macOS: `~/Library/Application Support/Jarvis`, Linux: `~/.local/share/jarvis`) |
| Settings | `config.json` in the data folder |
| Tasks, chats, change history, activity | `jarvis.db` (SQLite) in the data folder |
| Backups of files Jarvis changed | `backups\<change id>\` in the data folder |
| Logs | `logs\jarvis.log` in the data folder |
| Phone certificates (if phone access was used) | `phone\` in the data folder |
| Pictures you attached | `images\` in the data folder |
| Automatic daily backups of `jarvis.db` (last 7 days) | `backups\daily\` in the data folder |

The exact paths are shown in **Settings → Your data**. Use the `JARVIS_DATA_DIR` environment variable
or `--data-dir` to put it somewhere else.

- **Automatic backups:** once a day, Jarvis copies `jarvis.db` (tasks, flashcards, chats, activity) into
  `backups\daily\`, keeping the last 7 days. To restore one, close Jarvis and copy it over `jarvis.db`.
- **Back up everything:** close Jarvis and copy the data folder.
- **Remove everything:** close Jarvis and delete the data folder. Your project folders are untouched.
  To uninstall the model too, run `ollama rm <model>` (and uninstall Ollama if you like).

---

## Configuration

Everything is editable in **Settings**, or in `config.json` (restart Jarvis after editing by hand).
`config.example.json` in this folder shows the defaults. Invalid values fall back to the defaults.

| Key | Default | Meaning |
|---|---|---|
| `provider` | `ollama` | `ollama` or `openai_compatible` |
| `endpoint` | `http://127.0.0.1:11434` | Model server address |
| `model` | `""` | Model name; empty = best installed model |
| `code_model` | `""` | Model for Implementation and Testing & debugging modes; empty = same as `model` |
| `semantic_search` | `true` | Also search project files by meaning (needs `embedding_model` installed) |
| `embedding_model` | `nomic-embed-text` | Local model used for search by meaning |
| `temperature` | `0.3` | Randomness (0–2). Lower is more focused |
| `context_window` | `8192` | Tokens the model sees at once |
| `think` | `false` | Let thinking-capable models reason first |
| `lean_prompt` | `false` | Short instructions, guide notes and history, for slow devices (on for the phone) |
| `num_threads` | `0` | CPU threads for the model; `0` = Ollama decides (4 on the phone) |
| `request_timeout` | `600` | Seconds to wait for the model |
| `allow_remote_endpoint` | `false` | Allow a model server on another machine (sends your data there) |
| `detail` | `concise` | Default answer length: `concise` / `detailed` |
| `max_context_chars` | `12000` | Max project text included per question |
| `max_file_bytes` | `300000` | Larger files are not read or indexed |
| `max_index_files` | `4000` | Max files indexed for search |
| `extra_exclude_patterns` | `[]` | Extra files/folders to hide, e.g. `["private/*", "*.sqlite"]` |
| `command_timeout` | `600` | Seconds before a running command is stopped |
| `voice_output` | `false` | Show "Read aloud" on answers |
| `phone_access` | `false` | Let paired phones connect over your home network (HTTPS) |
| `phone_port` | `8766` | Port for the phone connection |
| `vision_model` | `""` | Model that reads pictures; empty = the chat model if it can, else the best installed one |
| `daily_backup` | `true` | Back up `jarvis.db` once a day, keeping 7 copies |

---

## How Jarvis is built

A small Python web server (FastAPI) that serves a plain HTML/CSS/JavaScript interface. No build step,
no CDN, so every asset is local.

```
jarvis/
  __main__.py        start-up: python -m jarvis
  server.py          HTTP API + security guard (localhost only, session token, Host/Origin checks)
  config.py          settings model, config.json, local-endpoint guard
  db.py              SQLite schema
  tasks.py           task storage and default ordering
  conversations.py   chat history
  activity.py        activity log
  llm/               replaceable model providers
    base.py            LLMProvider interface (status, chat_stream)
    ollama.py          Ollama
    openai_compat.py   llama.cpp / LM Studio / any OpenAI-style local server
  assistant/
    prompts.py         system prompts for each mode, structured-output schemas
    context.py         builds project context (budgeted, redacted, with sources)
    service.py         chat streaming, cancellation, task breakdown/ordering
  project/
    workspace.py       sandboxed file access
    secrets.py         secret-file rules and redaction
    index.py           offline keyword search (BM25)
    commands.py        command detection, risk classification, runner
    changes.py         change proposals, diffs, apply/undo with backups
  study.py           flashcards and spaced-repetition scheduling
  sync.py            two-way sync of tasks and flashcards between the laptop and Jarvis on the phone
  progress.py        progress counts for studying vs developing
  motivation.py      the verse/quote on opening: entries, themes, and how one is picked
  learn/             Learn features
    guides/*.md        the built-in guides (plain Markdown: edit or add your own)
    guides.py          guide sections + keyword search, and guide notes for chat
    decks.py           starter flashcard decks (fixed ids, so laptop and phone merge)
    exercises.py       practice exercises: task, starter code, hidden tests, solution, hints
    practice.py        runs your code against the tests (python / node / php), saves progress
    api_lab.py         the practice REST API, webhook inbox, SOAP and JSON-RPC endpoints
    standup.py         stand-up note from your tasks
  images.py          attached pictures (validated, stored by content hash)
  reliability.py     daily backups, start-with-Windows shortcut
  phone/             phone access (off by default)
    devices.py         pairing codes, device keys, removal
    certs.py           local certificate authority + HTTPS certificate
    listener.py        the separate HTTPS listener for phones
  static/            index.html, app.js, study.js, learn.js, progress.js, images.js, markdown.js (safe renderer), style.css
                     charts.js + charts.css (offline SVG charts), companion.js + companion.css, companion/ (stickers)
                     mobile.html, mobile.js, mobile.css, manifest, sw.js, icons/ (phone app)
  project/embeddings.py  search by meaning (local embedding model, cached in jarvis.db)
android/             Android app: app/ (Java, resources), setup_toolchain.py, build_apk.py
evals/               answer-quality measurements: cases.py, run_eval.py, fixtures/
tests/               pytest suite + tests/js (Node test for the Markdown renderer)
```

**To add another model backend**, implement `LLMProvider` (two methods) in `jarvis/llm/` and
register it in `create_provider()`.

**Security model of the local server:** it listens on `127.0.0.1` only. Every API call needs a random
token generated at start-up and embedded in the page, so other websites open in your browser
can't use Jarvis. Host and Origin headers are checked to block DNS-rebinding attacks. Phone access, when
turned on, is a second HTTPS-only listener whose requests go through stricter rules: a pairing key plus
an allow-list (see `jarvis/phone/__init__.py`).

---

## Running the tests

```powershell
python -m pytest -q                       # Python tests (uses a fake model; no Ollama needed)
node --test tests/js/markdown.test.js tests/js/sessions.test.js   # Markdown safety, focus-session rules
python android/test_focus_session.py      # the phone's focus-session rules (same cases, in Java)
```

If Ollama is running with `gemma3:1b`, `qwen3:1.7b` or `llama3.2`, three extra live tests also run
against the real model. Otherwise they are skipped. Choose the model with `JARVIS_TEST_MODEL`.

`tests/test_learn.py` also runs every practice exercise's reference solution (it must pass) and starter
code (it must fail) with the real Python, Node and PHP on your machine; a language that isn't installed
is skipped. If you add an exercise, those tests check it automatically.

**Security of the Learn features:** practice code runs only when you press *Check*, on the device where
Jarvis runs, in a temporary folder with a time limit (it's your own code, run like any script you'd run).
A phone connected to the laptop can't trigger it. The API Lab (`/practice/...`) needs no session token
because your own scripts call it, so it has its own practice logins, keeps the Host/Origin checks, is
refused on the Wi-Fi listener, and only delivers webhooks to addresses on the same device.

---

## Limitations

- Answer quality depends on the local model. Small models can be wrong, vague, or ignore
  formatting instructions. Review everything, especially code and commands.
- Project search combines keywords with meaning (when `nomic-embed-text` is installed), but very vague
  questions can still miss relevant files. Attach the files you care about for best results.
- One project folder is open at a time, and Jarvis can't access folders outside it.
- Code changes replace whole files. For small edits to big files, edit in the viewer or ask for the
  complete file.
- Commands run without a shell: no pipes, redirects or chained commands. Interactive programs that
  wait for keyboard input won't work.
- Reminders only happen while Jarvis is running: on the computer a session lives in the open Jarvis tab
  (closing the tab ends it; the notification needs that tab open in the background); on Android it lives in
  the Study Buddy service while its notification is showing. There are no scheduled reminders for when Jarvis
  is closed. Because a session only notices activity in Jarvis, coding in VS Code or reading docs elsewhere
  counts as inactive (on Windows you can turn on the optional Coding Focus to count your coding apps).
- Her extra expressions are drawn by a script from the original stickers: at full size the edited eyelids
  can look a little smoother than the hand-drawn art; at her normal size it isn't noticeable.
- The Windows floating Study Buddy uses a see-through color key, so her outline can look slightly jagged on
  some backgrounds; the in-page and Android versions are smooth. On Xiaomi/POCO phones (HyperOS), also allow
  *Display pop-up windows while running in the background* for Jarvis if she doesn't appear.
- Only the menus, Study Buddy, check-ins, reminders and the Build tabs are translated to Japanese so far.
- Diagrams are shown as Mermaid/ASCII text, not rendered.
- The desktop interface is designed for a desktop browser; use the phone app on phones.
- The phone apps aren't from an app store: the Android app is built on your computer, and on iPhone
  the web app is used. Chat needs the phone and computer on the same network with Jarvis running; tasks
  also work offline (see above). If the computer's network address changes, update it in the app and
  pair again; a fixed address in your router avoids this.
- The phone can't browse files, apply changes or run commands (by design).
- Without the Termux setup, there is no AI on the phone itself: answers come from your computer's model.
- Practice exercises check behaviour with fixed tests; passing them doesn't prove the code is perfect.
  The API Lab is a simulation for learning, not a real service. The guides are written for learning and
  can't cover every version of every tool; check official documentation for details that matter at work.
  With it, the phone runs small models that are slower and make more mistakes than the laptop's.
- Reading pictures depends on the model: clear, well-lit photos of printed or neat text work best;
  messy handwriting, tiny text and complex diagrams are often misread. Check the transcription.
- Flashcard reviews work offline on the phone, but creating decks, cards and AI flashcards needs the computer.
- If the computer sleeps, the phone can't reach it; set Windows to not sleep while plugged in if you rely
  on the phone.

## Do I need hosting or a cloud server?
No. Jarvis is designed so that nothing needs hosting: the model runs on your computer, and the phone
talks to it directly over your Wi-Fi. A free hosting tier would actually make things worse:
- **Privacy:** your prompts, code and tasks would live on someone else's server. Avoiding that is the
  main point of Jarvis.
- **It can't run the model well:** free tiers have no GPU and little memory (often 0.5–1 GB). Even the
  ones with more memory run a 4B model slowly on a CPU, put idle apps to sleep, and need an account.
- **It doesn't help offline use:** a cloud server needs the internet, and Jarvis doesn't.

If you want to use Jarvis away from home, the safer option is a private VPN between your phone and
your own computer (for example WireGuard on your router). That's your choice to set up; Jarvis doesn't
need or configure it.

## Reliability

- **Start with Windows** (Settings → Reliability): adds a shortcut to your Startup folder that starts
  Jarvis quietly, without a window, when you sign in. Turn it off there, or delete
  `Jarvis.lnk` from `shell:startup`. To stop a running background Jarvis, end *pythonw.exe* in Task Manager.
- Starting Jarvis while it's already running just opens the existing one, so you never get two copies.
- **Daily backups** of your data (see *Your data*).
- If the computer's network address changes, phone access restarts with a matching certificate within
  5 minutes, and the Android app finds the computer again by itself.
- Phone and browser always re-check app files, so after an update they never keep running an old copy.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Ollama not running" | Start the Ollama app (or `ollama serve`), then click the status pill or **Check again**. |
| "Model … is not installed" | `ollama pull <model>` once while online, or pick another model in Settings. |
| First answer is very slow | The model is loading into memory. Later answers are faster. Try a smaller model or context size. |
| Browser didn't open | Go to `http://127.0.0.1:8765` yourself. If that port was busy, Jarvis prints the port it used. |
| "Missing or outdated session token" | Jarvis was restarted; reload the page. |
| `python` not found | Install Python 3.10+ from python.org and tick "Add Python to PATH". |
| A command fails with "not installed or not on your PATH" | Install that tool, or run it with its full path. |
| "None of your installed models can look at images" | `ollama pull gemma3:4b` once while online (it is also a good chat model). |
| A picture was misread | Retake it closer and with better light, or paste the text instead. |
| A file shows 🔒 | Its name suggests secrets. Jarvis won't read it by design. |
| Phone can't connect | Same Wi-Fi as the computer? Phone access on (green "Phone access on" pill)? Windows Firewall: allow Python on **Private** networks (Windows Security → Firewall → Allow an app). Guest or "isolated" Wi-Fi networks block devices from reaching each other. |
| Phone says "not paired" | It was removed, or you opened a different address. Pair again with a new code. |
| "Phone access couldn't start" | The phone port is in use. Pick another port in Settings → Phone access. |
| Something else | See `logs\jarvis.log` in the data folder. |
