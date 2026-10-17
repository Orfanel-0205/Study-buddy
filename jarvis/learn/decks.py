"""Starter flashcard decks that come with Jarvis, written from the built-in guides.

Installed decks and cards get fixed ids ("starter:<deck>" and "starter:<deck>:<hash of the front>"),
so installing a deck on the laptop and on the phone gives the *same* deck, and syncing merges them
instead of creating duplicates. Installing again only adds cards that are missing (cards you deleted
on purpose stay deleted).
"""

from __future__ import annotations

import hashlib
from datetime import date

from ..db import Database, now_iso

STARTER_DECKS: list[dict] = [
    {
        "key": "devnet-apis",
        "name": "DevNet 4 – APIs",
        "description": "Module 4: API styles, REST, requests/responses, auth, rate limits, webhooks, troubleshooting.",
        "guide": "devnet-apis",
        "cards": [
            ("What does an API let software do?", "Lets one program talk to another; it defines what data and functions an application exposes (and how), so it can share them securely."),
            ("Three common reasons to use APIs?", "Automation tasks, data integration, and adding another application's functionality."),
            ("Synchronous API: how does it respond, and what does the client do meanwhile?", "It responds immediately with the data; the client waits (is blocked) until the response arrives. Used when data is readily available."),
            ("Asynchronous API: what does the first response contain?", "Only an acknowledgement that the request was received (no data); the result comes later. Used when processing takes time. The client keeps working."),
            ("Which HTTP status code typically signals an asynchronous API accepted the request?", "202 Accepted"),
            ("The three most popular API architectural styles?", "RPC, SOAP and REST."),
            ("What is RPC?", "Remote Procedure Call: a request-response model where a client calls a procedure on another application, which runs it and returns the result. Transports include XML-RPC, JSON-RPC, NFS (and SOAP)."),
            ("SOAP messages are written in which format?", "XML"),
            ("The four elements of a SOAP message?", "Envelope (root, required), Header (optional, e.g. authorization), Body (the data, required), Fault (errors/status, optional)."),
            ("SOAP is 'independent, extensible, neutral'. What does neutral mean?", "It can run over any protocol: HTTP, SMTP, TCP, UDP or JMS."),
            ("Who defined REST?", "Roy Thomas Fielding."),
            ("The six REST constraints?", "Client-server, stateless, cacheable, uniform interface, layered system, code-on-demand (optional)."),
            ("REST 'stateless' means…", "Every request contains all the information the server needs; the server keeps no session state between requests."),
            ("Why is code-on-demand the optional REST constraint?", "Running third-party code (e.g. JavaScript) sent by the server is a security risk."),
            ("The four principles of REST's uniform interface?", "Identification of resources; manipulation of resources through representations; self-descriptive messages; hypermedia as the engine of application state (HATEOAS)."),
            ("The four parts of a REST request?", "URI, HTTP method, headers, body."),
            ("The parts of a URI?", "Scheme (http/https), authority (host + port), path (the resource), query (filtering/scope details)."),
            ("HTTP method for Create / Read / Replace / Partial update / Delete?", "POST / GET / PUT / PATCH / DELETE"),
            ("PUT vs PATCH?", "PUT replaces/updates the whole resource; PATCH updates only some of its fields."),
            ("Request header vs entity header?", "Request headers carry information not about the body (e.g. Authorization); entity headers describe the body (e.g. Content-Type: application/json)."),
            ("Which methods typically carry a body?", "POST, PUT and PATCH."),
            ("The three parts of a REST response?", "HTTP status, headers, body."),
            ("The five status code classes?", "1xx informational, 2xx success, 3xx redirection, 4xx client error, 5xx server error."),
            ("200 vs 201 vs 204?", "200 OK (usually with a body); 201 Created (resource created); 204 No Content (success, nothing returned)."),
            ("401 vs 403?", "401 Unauthorized = not authenticated (missing/wrong credentials). 403 Forbidden = authenticated but not allowed (insufficient privileges)."),
            ("What causes a 400 Bad Request?", "Malformed syntax: misspelled resources/fields, invalid JSON, missing required fields."),
            ("404?", "Not Found: the resource path/ID in the URI doesn't exist on the server."),
            ("407?", "Proxy Authentication Required: authenticate with the proxy first."),
            ("409?", "Conflict with the current state of the resource (e.g. edit conflict, duplicate). Retry after it's resolved."),
            ("415?", "Unsupported Media Type: the body's format isn't supported (e.g. XML sent to a JSON-only API); fix Content-Type."),
            ("429?", "Too Many Requests: rate limit exceeded."),
            ("500 vs 501?", "500 Internal Server Error (unexpected server failure); 501 Not Implemented (server doesn't support the function)."),
            ("502 vs 504?", "502 Bad Gateway: gateway/proxy got an invalid response from upstream. 504 Gateway Timeout: it got no timely response."),
            ("503?", "Service Unavailable: server overloaded or under maintenance; retry later."),
            ("How do you ask an API for a compressed response?", "Send the Accept-Encoding request header (gzip, compress, deflate, br, identity, *)."),
            ("What is response pagination?", "Splitting large results into chunks/pages, usually chosen with a query parameter (e.g. ?page=2)."),
            ("Authentication vs authorization?", "Authentication proves who you are (ID at the airport); authorization proves you're allowed to do the action (concert ticket)."),
            ("How does Basic authentication send credentials?", "username:password joined by a colon, Base64-encoded, in the Authorization header. Encoding, not encryption: needs HTTPS."),
            ("What is Bearer authentication?", "Sending a token generated by an authentication server (e.g. an Identity Service) as Authorization: Bearer <token>."),
            ("API key: public vs private?", "A server-generated unique string; public keys can be shared (identify the app), private keys must be kept secret like passwords."),
            ("What does OAuth add over simple auth?", "It combines authentication with authorization and gives third-party apps limited access via access tokens; the user gives credentials only to the authorization server (IdP/IdS)."),
            ("Is OAuth 2.0 backwards compatible with OAuth 1.0?", "No."),
            ("In OAuth, what is a 'flow'?", "The process of obtaining the access token."),
            ("Three reasons for API rate limits?", "Avoid server overload, give better service/response times to all users, protect against DoS attacks."),
            ("Leaky bucket algorithm?", "Requests queue in arrival order and are processed at a fixed rate; if the queue is full, new requests are rejected."),
            ("Token bucket algorithm?", "Each client gets tokens over time; each request uses one; with no token left the request is rejected. Allows bursts."),
            ("Fixed window counter algorithm?", "A counter per fixed time window; once the limit for that window is reached, further requests in it are rejected."),
            ("Sliding window counter algorithm?", "Counts requests made in the window ending now (e.g. the last 60 s) to decide whether to allow a new one."),
            ("Common rate-limit response headers?", "X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset."),
            ("Status codes used when a rate limit is exceeded?", "429 Too Many Requests (most common) or 403 Forbidden."),
            ("What is a webhook?", "An HTTP callback: an HTTP POST the provider sends to a URL you registered when an event occurs. Also called a reverse API; no polling needed."),
            ("Three requirements to consume a webhook?", "The app must run at all times to receive POSTs, register its URI with the provider, and handle the incoming notifications."),
            ("Two Cisco examples of webhooks?", "Cisco DNA Center sends network events to third-party apps; Webex notifies you of new messages in a room."),
            ("Client-side causes of 'no response' from an API?", "User error (mistyped URI, missing scheme), wrong domain name, connectivity (proxy/firewall/VPN), invalid SSL certificate."),
            ("How do you skip certificate checks in Python requests (lab only)?", "requests.get(url, verify=False). In production fix the certificate instead."),
            ("Server-side cause of a long silence then a timeout traceback?", "The API server isn't functioning (power, cabling, domain change, network down)."),
            ("Three steps to troubleshoot an HTTP error code?", "Check the return code, check the response body, then use a status code reference."),
            ("Who fixes server-side API problems?", "Not the client: contact the API server's administrator (check server logs / packet captures if you have access)."),
        ],
    },
    {
        "key": "devnet-software",
        "name": "DevNet 3 – Software development & design",
        "description": "Module 3: SDLC, Waterfall/Agile/Lean, Scrum, design patterns, version control, testing, data formats.",
        "guide": "devnet-software-design",
        "cards": [
            ("What does SDLC stand for?", "Software Development Life Cycle."),
            ("The six SDLC phases, in order?", "Requirements & analysis, design, implementation, testing, deployment, maintenance."),
            ("Which document ends the requirements phase in waterfall?", "SRS: Software Requirement Specification."),
            ("Which documents come out of the design phase?", "HLD (High-Level Design) and LLD (Low-Level Design)."),
            ("Which SDLC phase is the longest?", "Implementation (coding/development)."),
            ("Four kinds of testing in the testing phase?", "Functional, integration, performance and security testing."),
            ("What happens in the maintenance phase?", "Customer support, fixing production bugs, improvements, gathering new requests, then the next iteration."),
            ("The three most popular software development methodologies?", "Waterfall, Agile, Lean."),
            ("What decides which methodology to use?", "Type of project, length of project, size of team."),
            ("Who created the waterfall model, and how many phases did it have?", "Winston W. Royce; seven phases."),
            ("The four Agile Manifesto values?", "Individuals and interactions over processes and tools; working software over comprehensive documentation; customer collaboration over contract negotiation; responding to change over following a plan."),
            ("Agile Manifesto: year, number of authors, number of principles?", "2001, 17 developers, 12 principles."),
            ("Four Agile methods named in the course?", "Scrum, Lean, Extreme Programming (XP), Feature-Driven Development (FDD)."),
            ("How long is a sprint?", "Usually 2–4 weeks, set beforehand; at the end the software should be working and deliverable."),
            ("What is a backlog?", "All features of the software, as a prioritized list."),
            ("User story template?", "As a <user|role>, I would like to <action>, so that <value|benefit>."),
            ("Maximum Scrum team size and stand-up length?", "No more than 10 people; stand-up no more than 15 minutes, daily, same time."),
            ("Lean's most fundamental principle?", "Eliminate waste."),
            ("The seven Lean principles?", "Eliminate waste, amplify learning, decide as late as possible, deliver as fast as possible, empower the team, build integrity in, optimize the whole."),
            ("The seven wastes of software development?", "Partially done work, extra processes, extra features, task switching, waiting, motion, defects."),
            ("What are software design patterns?", "Proven, language-independent best-practice solutions to common software design problems."),
            ("Who are the Gang of Four and what did they publish?", "Gamma, Helm, Johnson, Vlissides: Design Patterns: Elements of Reusable Object-Oriented Software (1994)."),
            ("Two GoF design principles?", "Program to an interface, not an implementation; favor object composition over class inheritance."),
            ("GoF pattern categories and count?", "Creational, Structural, Behavioral; 23 patterns."),
            ("What does the Observer pattern do, and which category is it?", "Behavioral: a subscription mechanism; observers are notified of changes in the subject. The subject keeps a list of observers with add/remove methods."),
            ("Benefit of Observer over polling?", "Observers get real-time data when changes occur; subscription performs better than polling."),
            ("MVC: what do Model, View and Controller do?", "Model: data, logic and rules. View: visual representation. Controller: middleman that takes user input and converts it for the model or view."),
            ("Main benefit of MVC?", "Each component can be built (and changed) in parallel / independently."),
            ("Three types of version control systems?", "Local, centralized, distributed (Git is distributed)."),
            ("The three Git areas?", "Working directory, staging area (index), repository."),
            ("Unit test vs integration test?", "Unit: one small piece in isolation. Integration: several pieces working together."),
            ("TDD cycle?", "Red (write a failing test), green (make it pass), refactor."),
            ("Python standard-library unit test framework and how to run it?", "unittest: subclass unittest.TestCase, methods named test_*, run with python -m unittest."),
            ("Which Python modules parse JSON, XML and YAML?", "json (stdlib); xml.etree.ElementTree (stdlib) or xmltodict; PyYAML (yaml.safe_load)."),
            ("json.loads vs json.dumps?", "loads: JSON string → Python object. dumps: Python object → JSON string (load/dump for files)."),
            ("Two YAML rules that often break files?", "Indentation matters and must use spaces, never tabs."),
            ("Commands to create a venv and save dependencies?", "python -m venv <name>, activate it, pip install ..., pip freeze > requirements.txt."),
        ],
    },
    {
        "key": "http-status",
        "name": "HTTP status codes",
        "description": "The codes you'll meet every day, with what to check when you get them.",
        "guide": "devnet-apis",
        "cards": [
            ("200", "OK: success, usually with a body."),
            ("201", "Created: a new resource was created (look for the Location header)."),
            ("202", "Accepted: processing has started but isn't finished (asynchronous)."),
            ("204", "No Content: success with no body (common for DELETE)."),
            ("301 / 302", "Moved permanently / found (temporary redirect): follow the Location header."),
            ("304", "Not Modified: your cached copy is still valid (after If-None-Match / ETag)."),
            ("400", "Bad Request: fix the request (field names, JSON syntax, required fields)."),
            ("401", "Unauthorized: not authenticated. Check credentials/token and the Authorization header."),
            ("403", "Forbidden: authenticated but not allowed. Use an account with the right role/permissions."),
            ("404", "Not Found: check the path and the ID."),
            ("405", "Method Not Allowed: that method isn't supported on this resource."),
            ("409", "Conflict: duplicate or edit conflict with the current state."),
            ("415", "Unsupported Media Type: send the right Content-Type (e.g. application/json)."),
            ("422", "Unprocessable Content: valid JSON but the values fail validation (FastAPI, Laravel)."),
            ("429", "Too Many Requests: slow down; wait Retry-After seconds."),
            ("500", "Internal Server Error: a bug on the server; report the request you sent."),
            ("502", "Bad Gateway: a proxy/gateway got an invalid response from the upstream server."),
            ("503", "Service Unavailable: overloaded or maintenance; retry later."),
            ("504", "Gateway Timeout: a proxy/gateway got no timely response from upstream."),
            ("Which status codes are worth retrying automatically?", "429, 502, 503, 504 (and network errors/timeouts), with backoff. Not 400/401/403/404/409/415/422."),
        ],
    },
    {
        "key": "git",
        "name": "Git essentials",
        "description": "Everyday commands, team workflow and how to undo mistakes.",
        "guide": "git",
        "cards": [
            ("Command: see what changed and what's staged", "git status (and git diff / git diff --staged for the lines)."),
            ("Command: create a new branch and switch to it", "git switch -c <branch>  (older: git checkout -b <branch>)"),
            ("Command: stage a file / commit it", "git add <file>, then git commit -m \"message\""),
            ("Command: publish a new branch to GitHub", "git push -u origin <branch>"),
            ("git fetch vs git pull?", "fetch downloads remote changes without merging; pull = fetch + merge (or rebase) into your branch."),
            ("GitHub flow in one sentence?", "main is always deployable; every change is a short-lived branch merged through a reviewed pull request."),
            ("Conventional Commit prefixes?", "feat, fix, docs, refactor, test, chore (e.g. \"fix(api): return 404 for unknown id\")."),
            ("What makes a good pull request?", "Small, one purpose, a description (what/why/how to test), passing tests, linked ticket."),
            ("How to resolve a merge conflict?", "Edit the file to the right final code, delete the <<<<<<< ======= >>>>>>> markers, run tests, git add, then git commit."),
            ("How to cancel a merge that went wrong?", "git merge --abort"),
            ("Merge vs rebase: the golden rule?", "Only rebase commits that only you have; never rebase shared branches like main."),
            ("Discard changes in a file (unstaged)", "git restore <file>"),
            ("Unstage a file but keep the changes", "git restore --staged <file>"),
            ("Fix the last commit (not pushed yet)", "git add <forgotten files> then git commit --amend"),
            ("Undo the last commit but keep the changes (not pushed)", "git reset --soft HEAD~1"),
            ("Undo a commit that's already pushed", "git revert <commit>: a new commit that reverses it (history isn't rewritten)."),
            ("Set work aside to switch branches", "git stash, then git stash pop later."),
            ("Recover a 'lost' commit", "git reflog to find it, then git switch -c rescue <hash>."),
            ("You pushed an API key. What must you do first?", "Rotate it (revoke the old key, make a new one). Removing it from history isn't enough."),
            ("Semantic versioning MAJOR.MINOR.PATCH?", "MAJOR: breaking change. MINOR: new feature, compatible. PATCH: bug fix."),
            ("Fork vs clone?", "Fork: your own copy of a repository on GitHub. Clone: a local copy (with full history) of any repository."),
            ("Which files should never be committed?", "Secrets (.env, keys), dependencies (node_modules, vendor, .venv), build output (dist, build), caches."),
        ],
    },
    {
        "key": "performance",
        "name": "Speed: what to apply, and when",
        "description": "The performance checklist with the situation where each item pays off.",
        "guide": "performance",
        "cards": [
            ("The three-step habit before any optimization?", "Measure, fix the biggest bottleneck, measure again."),
            ("When should you paginate a list?", "Whenever it can grow without limit (users, orders, logs): from day one."),
            ("When should a column get a database index?", "When it's used in WHERE, JOIN or ORDER BY on a table that will have thousands of rows (foreign keys almost always)."),
            ("How do you check whether a query uses an index?", "Run EXPLAIN on it and look for a full table scan."),
            ("What is the N+1 query problem?", "1 query for a list plus 1 query per item for related data. Fix with a JOIN, IN (...) or eager loading (Laravel with())."),
            ("When should you compress/resize images?", "Always for large or uploaded images: serve the displayed size, WebP/AVIF, quality ~75."),
            ("When should you NOT lazy-load an image?", "The main image at the top of the page; it makes the page feel slower."),
            ("When is minifying JS/CSS needed?", "In production builds, always (npm run build does it); not during development."),
            ("defer vs async on a script tag?", "defer: runs after HTML parsing, in order. async: runs as soon as it downloads, order not guaranteed."),
            ("Why remove unused dependencies?", "Smaller bundles, faster installs, fewer security risks."),
            ("When to compress API payloads (gzip/br)?", "Almost always; it's usually one server setting. JSON shrinks 70–90%."),
            ("When to debounce an input handler?", "Search-as-you-type, autosave, resize/scroll: wait until the user pauses (~300 ms)."),
            ("Why use database connection pooling?", "Reusing connections avoids 20–100 ms per new connection; create the pool once at startup."),
            ("What do loading skeletons improve?", "Perceived speed and layout stability, not actual speed. Use when data takes > ~300 ms."),
            ("When should you cache expensive queries?", "When the same slow query runs often and the data changes rarely; plan how the cache is invalidated."),
            ("Which data must never be cached publicly?", "Personal/private data: use Cache-Control: private or no-store."),
            ("When does code splitting pay off?", "When the JS bundle is large (Lighthouse 'reduce unused JavaScript'), especially SPAs with many routes."),
            ("How do you find unnecessary React re-renders?", "React DevTools Profiler / highlight updates; then memo/useMemo/useCallback, smaller components, state closer to use."),
            ("When do you need a CDN?", "Users far from your server or many static files/media; not for a local/internal app."),
            ("What must be true before adding a load balancer?", "The app must be stateless (sessions/files in shared storage), and one optimized server must really be insufficient."),
        ],
    },
    {
        "key": "structure-tooling",
        "name": "File structure & tooling",
        "description": "Where things go in Python, PHP, JS and TS projects, and the tools teams use.",
        "guide": "project-structure",
        "cards": [
            ("Why must a PHP app's web root be public/ and not the project folder?", "So browsers can't download .env, config or source files; only public/ is exposed."),
            ("What is a front controller (PHP)?", "public/index.php: every request enters there and is routed to the right controller."),
            ("PSR-4 autoloading in one sentence?", "A namespace prefix maps to a folder (App\\ → src/), so classes load from their file paths via Composer."),
            ("Which Composer/npm files are committed and which folder is not?", "Commit composer.json + composer.lock / package.json + package-lock.json; never commit vendor/ or node_modules/."),
            ("Laravel: where do routes, controllers, models, views and migrations live?", "routes/web.php & api.php; app/Http/Controllers; app/Models; resources/views; database/migrations."),
            ("Python 'src layout'?", "Code in src/<package>/, tests in tests/, settings in pyproject.toml."),
            ("Why a virtual environment per Python project?", "Each project gets its own package versions without conflicts; recreate with requirements.txt."),
            ("Controller vs service vs repository/model?", "Controller: HTTP in/out. Service: business logic. Repository/model: database access."),
            ("Where do secrets go?", "Environment variables / .env (gitignored); commit .env.example with fake values."),
            ("TypeScript: which setting should be on, and what checks types?", "\"strict\": true in tsconfig.json; tsc (npx tsc --noEmit). Running .ts with Node only strips types."),
            ("Python naming: files, functions, classes, constants?", "snake_case.py, snake_case(), PascalCase, UPPER_SNAKE."),
            ("PHP naming (PSR-1/12): files, methods, classes?", "PascalCase.php matching the class, camelCase() methods, PascalCase classes."),
            ("Formatter + linter + test tool for Python / PHP / JS-TS?", "black or ruff, ruff, pytest / php-cs-fixer, phpstan, phpunit or pest / prettier, eslint, vitest or jest."),
            ("Signs that a file should be split?", "Over ~300–400 lines, does more than one job, frequent merge conflicts, copy-pasted code."),
            ("Where do tests go?", "A tests/ folder mirroring the source structure (tests/services/test_billing.py)."),
        ],
    },
    {
        "key": "business-rules",
        "name": "Business rules",
        "description": "Turning policies into clear, testable rules and code.",
        "guide": "business-rules",
        "cards": [
            ("What is a business rule?", "A statement of how the business works that software must respect, e.g. \"Orders of ₱5,000 or more ship free.\""),
            ("The five kinds of business rules?", "Constraint, computation, inference, action enabler (trigger), authorization."),
            ("Validation vs business rule?", "Validation checks the format of input (an email looks like an email); a business rule is policy (a member can borrow at most 5 books). Both must be enforced on the server."),
            ("Why give each rule an ID like BR-07?", "So code, tests, tickets and conversations can point to exactly the same rule."),
            ("Rewrite \"large orders get free shipping\" as a testable rule.", "\"Orders of ₱5,000 or more get free shipping.\" Exact number and boundary."),
            ("WHEN / IF / THEN template?", "WHEN <event> IF <conditions> THEN <outcome>."),
            ("When should you draw a decision table?", "When two or more conditions combine to decide an outcome."),
            ("Three checks for a decision table?", "Complete (every combination has an answer), no conflicts (or a clear priority), and the boundaries are stated."),
            ("Where should a business rule live in code?", "Once, on the server, in a service/domain/policy function; the UI may also check for a better experience."),
            ("Why should a rule return the reason, not just yes/no?", "Users and support need to know why (e.g. \"blocked by BR-12: 3 unpaid invoices\"), and logs can explain decisions later."),
            ("What is the last line of defense for data rules?", "Database constraints: NOT NULL, UNIQUE, CHECK, foreign keys."),
            ("When are values better in configuration than in code?", "When they change often (tax rates, fees, limits), ideally with an effective date."),
            ("When is a rule engine worth it?", "Only when rules change very often or non-developers must edit them; otherwise tested code is simpler."),
            ("How do you test a decision table?", "Table-driven tests: one test per row plus every boundary (e.g. 4,999.99 / 5,000 / 5,000.01), checking the reason too."),
            ("Safe order for changing a rule?", "Change the test first, see it fail, change the code, and note the change (with its effective date) in the release notes."),
        ],
    },
]


def _deck_uid(key: str) -> str:
    return f"starter:{key}"


def _card_uid(key: str, front: str) -> str:
    return f"starter:{key}:{hashlib.sha1(front.encode('utf-8')).hexdigest()[:12]}"


class StarterDecks:
    def __init__(self, db: Database):
        self.db = db

    def list(self) -> list[dict]:
        out = []
        with self.db.connect() as conn:
            for d in STARTER_DECKS:
                row = conn.execute("SELECT id FROM decks WHERE uid = ?", (_deck_uid(d["key"]),)).fetchone()
                have = 0
                if row:
                    uids = [_card_uid(d["key"], f) for f, _ in d["cards"]]
                    have = conn.execute(f"SELECT COUNT(*) FROM cards WHERE uid IN ({','.join('?' * len(uids))})",
                                        uids).fetchone()[0]
                out.append({"key": d["key"], "name": d["name"], "description": d["description"], "guide": d["guide"],
                            "cards": len(d["cards"]), "installed": bool(row), "deck_id": row["id"] if row else None,
                            "missing": len(d["cards"]) - have if row else len(d["cards"])})
        return out

    def install(self, key: str, today: date | None = None) -> dict:
        deck = next((d for d in STARTER_DECKS if d["key"] == key), None)
        if not deck:
            raise FileNotFoundError(f"There is no starter deck called '{key}'.")
        now = now_iso()
        due = (today or date.today()).isoformat()
        uid = _deck_uid(key)
        added = 0
        with self.db.connect() as conn:
            row = conn.execute("SELECT id FROM decks WHERE uid = ?", (uid,)).fetchone()
            if row:
                deck_id = row["id"]
            else:
                conn.execute("DELETE FROM deletions WHERE kind = 'deck' AND uid = ?", (uid,))  # re-added on purpose
                deck_id = conn.execute(
                    "INSERT INTO decks (uid, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (uid, deck["name"], deck["description"], now, now)).lastrowid
            fresh = not row
            for front, back in deck["cards"]:
                cuid = _card_uid(key, front)
                if conn.execute("SELECT 1 FROM cards WHERE uid = ?", (cuid,)).fetchone():
                    continue
                deleted = conn.execute("SELECT 1 FROM deletions WHERE kind = 'card' AND uid = ?", (cuid,)).fetchone()
                if deleted and not fresh:
                    continue  # the user deleted this card from the deck: leave it out
                conn.execute("DELETE FROM deletions WHERE kind = 'card' AND uid = ?", (cuid,))
                conn.execute("INSERT INTO cards (uid, deck_id, front, back, due, created_at, updated_at) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?)", (cuid, deck_id, front, back, due, now, now))
                added += 1
            if added:
                conn.execute("UPDATE decks SET updated_at = ? WHERE id = ?", (now, deck_id))
        return {"deck_id": deck_id, "added": added, "name": deck["name"]}
