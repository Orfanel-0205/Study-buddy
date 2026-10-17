---
title: Building concepts: the ideas behind every app
summary: Plain-language explanations of the concepts you meet when building software - client/server, HTTP and APIs (the DevNet ideas), data and databases, security, architecture, testing, deployment and scaling - each with when it matters.
tags: concepts, basics, client server, http, api, rest, json, authentication, authorization, jwt, session, database, sql, nosql, index, transaction, orm, migration, mvc, cache, queue, webhook, security, owasp, xss, sql injection, csrf, testing, ci cd, docker, hosting, dns, https, cdn, scaling, logging, mvp, technical debt, devnet
order: 11
---

# Building concepts: the ideas behind every app

Short definitions you can come back to. Each says **what it is** and **when it matters**.

## How apps talk (the DevNet Module 4 ideas)

- **Client and server:** the client (browser, phone app, script) asks; the server answers. They're separate programs, often on separate machines.
- **HTTP:** the language of the web: a request (method, URL, headers, optional body) and a response (status code, headers, body).
- **API:** a set of rules for how one program asks another for data or actions. A REST API uses HTTP for this.
- **REST:** a style where each thing (resource) has a URL (`/books/42`) and methods say what to do: GET read, POST create, PUT replace, PATCH change part, DELETE remove. Every request carries everything needed (**stateless**).
- **JSON:** the usual text format for API data: `{"name": "Adobo", "price": 120}`.
- **Status codes:** 2xx it worked, 3xx go elsewhere, 4xx your request is wrong (401 not logged in, 403 not allowed, 404 not found), 5xx the server failed.
- **Synchronous vs asynchronous:** sync answers now; async says "accepted" (202) and finishes later, so you poll or receive a **webhook**.
- **Webhook:** the other system calls *your* URL when something happens (a payment succeeded). No polling needed.
- **Rate limit:** a cap on requests per minute; exceed it and you get 429. Slow down and retry later.
- **SOAP vs REST vs RPC:** SOAP is XML messages with an envelope; RPC calls a named function remotely; REST works with resources over HTTP. Most modern web APIs are REST with JSON.

## Software design (the DevNet Module 3 ideas)

- **SDLC:** requirements → design → implementation → testing → deployment → maintenance.
- **Waterfall vs Agile:** do each phase once in order, vs build in short cycles (sprints) and adjust with feedback.
- **MVC:** Model (data and rules), View (what users see), Controller (handles the request and connects them).
- **Design pattern:** a proven solution to a common problem (Observer: subscribers get notified of changes; Repository: one place that talks to the database; Strategy: swap an algorithm, such as a pricing rule).
- **Version control (Git):** history of every change, branches for parallel work, pull requests for review.
- **Unit vs integration test:** one function alone vs several parts together (code + database + API).

## Data

- **Database:** where data lives permanently. **SQL** databases (MySQL, PostgreSQL, SQLite) store tables with relations; **NoSQL** (MongoDB, Firestore) stores documents. Start with SQL for business data.
- **Schema and migrations:** the structure of your tables, changed through versioned migration files (`php artisan migrate`), never by hand on the live database.
- **Primary key / foreign key:** a row's unique id / a column pointing to a row in another table (menu_items.category_id → categories.id).
- **Index:** speeds up searching a column (like a book index). Add one to columns you filter or join on.
- **Transaction:** several changes that succeed or fail together (take payment *and* create the order). ACID = all-or-nothing, consistent, isolated, durable.
- **ORM:** code objects for tables (Laravel Eloquent, Django ORM, Prisma), so you write `MenuItem::where(...)` instead of raw SQL. It still runs SQL; watch for N+1 queries.
- **CRUD:** Create, Read, Update, Delete, the four basic things an admin panel does.

## Security (learn these early)

- **Authentication vs authorization:** proving who you are (login) vs what you're allowed to do (only the owner edits the menu).
- **Sessions vs tokens:** a server-side session with a cookie (classic web apps, Laravel) vs a signed token such as a JWT sent with each request (APIs, mobile apps).
- **Password hashing:** store `bcrypt`/`argon2` hashes, never passwords. Frameworks do this for you.
- **SQL injection:** user input changing your SQL. Prevent it with parameterized queries or the ORM, never string concatenation.
- **XSS:** user input running as JavaScript on your page. Prevent it by escaping output (Blade `{{ }}`, React do this by default).
- **CSRF:** another site making your logged-in browser send a request. Frameworks add CSRF tokens to forms.
- **Secrets:** API keys and passwords live in `.env` (never committed) and are only used on the server, never in frontend JavaScript.
- **HTTPS/TLS:** encrypts traffic; free certificates from Let's Encrypt or your host.
- **OWASP Top 10:** the standard list of common web security risks. Read it once a year.

## Architecture and quality

- **Frontend / backend / full-stack:** what runs in the browser / on the server / both.
- **Layers:** controller (HTTP) → service (business rules) → repository/model (database). Keeps rules in one place.
- **Validation vs business rules:** checking input format vs enforcing policy (see the Business rules guide).
- **Cache:** keep a computed answer for reuse (a popular page, an expensive query). Remember to clear it when data changes.
- **Queue / background job:** do slow work later (send emails, resize photos) so the user doesn't wait.
- **Logging and monitoring:** recording what happened (logs) and being alerted when it breaks (Sentry, uptime checks).
- **Technical debt:** shortcuts that slow you down later. Fine for a demo; pay it back before it hurts.
- **Refactoring:** improving code without changing what it does, with tests as a safety net.
- **MVP:** the smallest version that solves the core problem well enough to learn from real users.

## Deploying and running

- **Environments:** local (your laptop), staging (a test copy online), production (real users).
- **Hosting types:** static (just files, e.g. GitHub Pages), serverless/edge functions (Vercel, Netlify), PaaS (Render), shared hosting (PHP sites), VPS (your own server).
- **Domain and DNS:** the name (myresto.com) and the system that points it to your server's address.
- **CI/CD:** automatic tests on every push (CI) and automatic deploys when they pass (CD), e.g. GitHub Actions.
- **Docker / containers:** packaging your app with everything it needs so it runs the same everywhere.
- **CDN:** copies of your files near your users, so pages load fast.
- **Scaling:** vertical (a bigger server) vs horizontal (more servers behind a load balancer; needs stateless apps).
- **Backups:** automatic copies of the database, and a tested way to restore them.

## For websites that need customers

- **Responsive design:** works on phones first (most restaurant customers use phones).
- **SEO basics:** clear titles, real text (not only images), fast pages, a Google Business Profile, and links from social media.
- **Accessibility:** readable contrast, alt text on images, works with a keyboard and screen readers.
- **Analytics:** count visits and clicks (menu views, "call" button taps) to prove your work is useful to the client.
