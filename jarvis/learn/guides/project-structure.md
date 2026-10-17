---
title: File structure for Python, PHP, JavaScript and TypeScript projects
summary: Where files go in real projects (scripts, APIs, web apps, Laravel, React), naming rules for each language, the tools teams expect, and when to split a file.
tags: file structure, folders, project layout, python, php, javascript, typescript, laravel, react, node, naming, tooling
order: 2
---

# File structure for Python, PHP, JavaScript and TypeScript projects

## Principles that apply to every language

- **Group by responsibility.** Routes/controllers handle HTTP, services hold business logic, models/repositories
  talk to the database, views/templates render HTML. (This is the MVC pattern from DevNet Module 3.)
- **One entry point.** `main.py`, `public/index.php`, `src/index.js`/`src/main.ts`. Everyone knows where the program starts.
- **Configuration and secrets outside the code.** Settings come from environment variables or a `.env`
  file that is **never committed**; commit a `.env.example` with fake values instead.
- **Tests mirror the source.** `src/services/billing.py` → `tests/services/test_billing.py`.
- **Generated and downloaded things are not committed:** `node_modules/`, `vendor/`, `.venv/`, `dist/`,
  `build/`, `__pycache__/`. List them in `.gitignore`.
- **A README** that says what it is, how to install, how to run, how to test.
- **Start flat, split when it hurts.** A 3-file project doesn't need 12 folders. Follow your framework's
  conventions when you use one; teammates will look for files there.

## Python

### A script or small tool
```text
weather-tool/
├── weather.py          # the code
├── test_weather.py     # pytest finds files named test_*.py
├── requirements.txt    # pip install -r requirements.txt
├── README.md
└── .gitignore          # .venv/  __pycache__/  .env
```

### A package or API (the "src layout")
```text
inventory-api/
├── pyproject.toml          # name, version, dependencies, tool settings
├── README.md
├── .env.example
├── src/
│   └── inventory/
│       ├── __init__.py
│       ├── main.py         # creates the FastAPI/Flask app
│       ├── config.py       # reads environment variables
│       ├── routers/        # HTTP endpoints, one file per resource (devices.py, users.py)
│       ├── services/       # business logic, no HTTP code here
│       ├── models.py       # database tables (SQLAlchemy) / data classes
│       └── schemas.py      # request/response shapes (Pydantic)
└── tests/
    ├── conftest.py         # shared pytest fixtures
    ├── test_devices_api.py
    └── test_inventory_service.py
```
- **Virtual environment per project:** `python -m venv .venv`, then activate it
  (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` on macOS/Linux), then `pip install ...`.
  Save dependencies with `pip freeze > requirements.txt` (the DevNet lab does exactly this).
- **Django** has its own layout: a project folder plus one "app" folder per feature (`models.py`, `views.py`,
  `urls.py`, `templates/`, `tests.py`).

## PHP

### Plain PHP with Composer (modern style)
```text
shop/
├── composer.json        # dependencies + autoload rules
├── composer.lock        # exact versions: commit it
├── public/              # the ONLY folder the web server exposes
│   ├── index.php        # front controller: every request starts here
│   └── assets/          # css, js, images
├── src/                 # your classes, autoloaded (PSR-4): namespace App\ → src/
│   ├── Controller/ProductController.php
│   ├── Service/CartService.php
│   └── Repository/ProductRepository.php
├── templates/           # HTML views
├── config/
├── tests/               # PHPUnit or Pest
├── vendor/              # installed by Composer: never commit, never edit
└── .env                 # secrets: never commit
```
```json
{ "autoload": { "psr-4": { "App\\": "src/" } } }
```
Run `composer dump-autoload` after changing it, then `require __DIR__ . '/../vendor/autoload.php';` in `public/index.php`.

Why `public/`: if the web root were the project folder, anyone could download `.env` or `config/`.
**Only `public/` should be reachable from a browser.**

### Laravel (the most common PHP framework at work)
```text
app/Http/Controllers/    # handle requests (thin: validate, call a service, return a response)
app/Models/              # Eloquent models (one per table)
app/Services/            # your business logic (create this folder yourself)
routes/web.php           # pages     routes/api.php  # JSON API (prefixed /api)
resources/views/         # Blade templates
database/migrations/     # table changes, in order (php artisan migrate)
database/seeders/        # sample data
tests/Feature/ tests/Unit/
.env                     # never commit
```
Laragon (which you have) runs PHP + MySQL locally; `laragon/www/<project>` is served at `http://<project>.test`.

## JavaScript (Node.js)

### An Express API
```text
todo-api/
├── package.json         # scripts + dependencies (npm install)
├── package-lock.json    # exact versions: commit it
├── src/
│   ├── index.js         # starts the server
│   ├── app.js           # creates the app, adds middleware and routes (easy to test)
│   ├── routes/          # todos.js: URL → controller
│   ├── controllers/     # read the request, call a service, send the response
│   ├── services/        # business logic
│   ├── db/              # connection pool + queries/models
│   └── middleware/      # auth, error handling, logging
├── tests/               # vitest, jest or node:test
└── .env                 # never commit
```
`package.json` scripts are how teams run things: `npm run dev`, `npm test`, `npm run build`, `npm run lint`.

### A frontend (React + Vite)
```text
src/
├── main.jsx             # entry
├── App.jsx
├── pages/               # one component per route/page
├── components/          # reusable UI pieces (Button.jsx, TaskCard.jsx)
├── hooks/               # useAuth.js, useFetch.js
├── api/                 # functions that call the backend (one place for fetch + error handling)
├── assets/              # images, fonts
└── styles/
public/                  # copied as-is (favicon, robots.txt)
```

## TypeScript

Same folders as JavaScript, plus:
```text
├── tsconfig.json        # compiler settings: turn on "strict": true
├── src/
│   ├── types/           # shared interfaces/types (User, ApiResponse<T>)
│   └── ...              # .ts / .tsx files
└── dist/                # compiled JavaScript (npm run build): don't commit
```
```json
{ "compilerOptions": { "target": "ES2022", "module": "NodeNext", "strict": true, "outDir": "dist", "rootDir": "src" } }
```
Run `npx tsc --noEmit` to type-check without building. Node 22.6+ can run `.ts` files directly
(it strips the types), but **only `tsc` actually checks them**.

## Full stack in one repository
```text
my-app/
├── backend/      # Python, PHP or Node API, with its own dependencies and tests
├── frontend/     # React/Vue app
├── docs/
├── docker-compose.yml   (optional)
└── README.md     # how to run both
```

## Naming rules by language

| | Python (PEP 8) | PHP (PSR-1/PSR-12) | JavaScript | TypeScript |
|---|---|---|---|---|
| Files | `snake_case.py` | `PascalCase.php` (= class name) | `camelCase.js` or `kebab-case.js` (pick one); components `PascalCase.jsx` | same as JS |
| Variables, functions | `snake_case` | `$camelCase`, `camelCase()` | `camelCase` | `camelCase` |
| Classes | `PascalCase` | `PascalCase` | `PascalCase` | `PascalCase`; types/interfaces too |
| Constants | `UPPER_SNAKE` | `UPPER_SNAKE` | `UPPER_SNAKE` | `UPPER_SNAKE` |
| Indentation | 4 spaces | 4 spaces | 2 spaces (most teams) | 2 spaces |

## Tools each team will expect you to know

| | Python | PHP | JavaScript / TypeScript |
|---|---|---|---|
| Package manager | `pip` (+ `venv`), or `uv`/`poetry` | `composer` | `npm` (or `pnpm`, `yarn`) |
| Formatter | `black` or `ruff format` | `php-cs-fixer` / `phpcbf` | `prettier` |
| Linter | `ruff`, `flake8` | `phpstan`, `phpcs` | `eslint` (+ `typescript-eslint`) |
| Tests | `pytest` (or `unittest`) | `phpunit`, `pest` | `vitest`, `jest`, `node:test` |
| Run a dev server | `uvicorn app.main:app --reload`, `flask run` | `php -S localhost:8000 -t public`, `php artisan serve` | `npm run dev` |

## When to split a file or folder

- A file is over ~300–400 lines, or you scroll a lot to find things.
- It does two jobs (e.g. HTTP handling **and** SQL **and** formatting): split by job.
- Two people keep getting merge conflicts in it.
- You copy-paste the same code in a third place: extract a function/module (DRY).

## .gitignore starter (combine what you need)
```gitignore
# secrets
.env
*.pem
# Python
.venv/
__pycache__/
*.pyc
# PHP
vendor/
# JS/TS
node_modules/
dist/
build/
coverage/
# editors / OS
.vscode/
.idea/
.DS_Store
Thumbs.db
```
