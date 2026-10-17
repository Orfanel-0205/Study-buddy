"""Coding practice exercises in Python, JavaScript, TypeScript and PHP.

Each exercise has a task, starter code, hidden tests, a reference solution and hints that work
without a model. Tests call `check(name, fn)` and `eq(actual, expected)` from the language's
harness in practice.py. Topics follow the guides (APIs, DevNet, performance, structure).
"""

from __future__ import annotations

EXERCISES: list[dict] = [
    # ------------------------------------------------------------------ Python
    {
        "id": "py-status-category",
        "language": "python",
        "title": "Classify HTTP status codes",
        "topic": "APIs",
        "level": "easy",
        "guide": "devnet-apis",
        "task": """Write `status_category(code)` that returns the class of an HTTP status code:
`"informational"` (1xx), `"success"` (2xx), `"redirection"` (3xx), `"client error"` (4xx) or `"server error"` (5xx).

Raise `ValueError` for anything outside 100–599.""",
        "starter": r'''def status_category(code: int) -> str:
    """Return the class of an HTTP status code."""
    raise NotImplementedError("write me")
''',
        "solution": r'''def status_category(code: int) -> str:
    """Return the class of an HTTP status code."""
    if not 100 <= code <= 599:
        raise ValueError(f"not an HTTP status code: {code}")
    return {1: "informational", 2: "success", 3: "redirection",
            4: "client error", 5: "server error"}[code // 100]
''',
        "tests": r'''
check("200 is success", lambda: eq(solution.status_category(200), "success"))
check("201 is success", lambda: eq(solution.status_category(201), "success"))
check("100 is informational", lambda: eq(solution.status_category(100), "informational"))
check("304 is redirection", lambda: eq(solution.status_category(304), "redirection"))
check("404 is client error", lambda: eq(solution.status_category(404), "client error"))
check("429 is client error", lambda: eq(solution.status_category(429), "client error"))
check("503 is server error", lambda: eq(solution.status_category(503), "server error"))
check("99 raises ValueError", lambda: raises(ValueError, solution.status_category, 99))
check("600 raises ValueError", lambda: raises(ValueError, solution.status_category, 600))
''',
        "hints": ["Integer division `code // 100` gives the first digit.",
                  "Check the range first and `raise ValueError(...)` before anything else."],
    },
    {
        "id": "py-basic-auth",
        "language": "python",
        "title": "Build a Basic auth header",
        "topic": "APIs",
        "level": "easy",
        "guide": "devnet-apis",
        "task": """Write `basic_auth_header(username, password)` that returns a dict with one header:
`{"Authorization": "Basic <base64 of 'username:password'>"}`.

Encode the text as UTF-8 before Base64. (This is exactly what `requests` does for `auth=(user, password)`.)""",
        "starter": r'''import base64


def basic_auth_header(username: str, password: str) -> dict:
    raise NotImplementedError("write me")
''',
        "solution": r'''import base64


def basic_auth_header(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}
''',
        "tests": r'''
check("learner / devnet123", lambda: eq(solution.basic_auth_header("learner", "devnet123"),
                                        {"Authorization": "Basic bGVhcm5lcjpkZXZuZXQxMjM="}))
check("viewer / viewer123", lambda: eq(solution.basic_auth_header("viewer", "viewer123")["Authorization"],
                                       "Basic dmlld2VyOnZpZXdlcjEyMw=="))
check("non-English letters and a colon in the password", lambda: eq(
    solution.basic_auth_header("josé", "päss:word")["Authorization"], "Basic am9zw6k6cMOkc3M6d29yZA=="))
''',
        "hints": ["Join with a colon: `f\"{username}:{password}\"`.",
                  "`base64.b64encode` needs bytes: call `.encode(\"utf-8\")` first, and `.decode()` the result back to text."],
    },
    {
        "id": "py-fetch-all-pages",
        "language": "python",
        "title": "Fetch every page of an API",
        "topic": "APIs",
        "level": "medium",
        "guide": "api-strategies",
        "task": """`get_page(n)` calls an API and returns a dict like `{"items": [...], "page": n, "pages": total_pages}`.
Pages start at 1.

Write `fetch_all(get_page)` that returns **all items from all pages, in order**, calling `get_page`
only as many times as needed (never for a page after the last one). If `pages` is 0, return `[]` after
the first call.""",
        "starter": r'''def fetch_all(get_page) -> list:
    raise NotImplementedError("write me")
''',
        "solution": r'''def fetch_all(get_page) -> list:
    items, page = [], 1
    while True:
        data = get_page(page)
        items.extend(data["items"])
        if page >= data["pages"]:
            return items
        page += 1
''',
        "tests": r'''
def fake_api(pages):
    calls = []
    def get_page(n):
        calls.append(n)
        return {"items": list(pages[n - 1]) if pages else [], "page": n, "pages": len(pages)}
    return get_page, calls

def three_pages():
    get_page, calls = fake_api([[1, 2], [3, 4], [5]])
    eq(solution.fetch_all(get_page), [1, 2, 3, 4, 5])
    eq(calls, [1, 2, 3])

def one_page():
    get_page, calls = fake_api([["a", "b"]])
    eq(solution.fetch_all(get_page), ["a", "b"])
    eq(calls, [1])

def empty():
    get_page, calls = fake_api([])
    eq(solution.fetch_all(get_page), [])
    eq(calls, [1])

check("three pages, in order, three calls", three_pages)
check("a single page", one_page)
check("no results (pages = 0)", empty)
''',
        "hints": ["Start with `page = 1` and loop until `page >= data[\"pages\"]`.",
                  "Use `items.extend(data[\"items\"])` to add a whole page at once."],
    },
    {
        "id": "py-token-bucket",
        "language": "python",
        "title": "Token bucket rate limiter",
        "topic": "Rate limits",
        "level": "medium",
        "guide": "devnet-apis",
        "task": """Implement the **token bucket** algorithm from DevNet 4.6.

`TokenBucket(capacity, refill_per_second)` starts **full**. `allow(now)` is called with the current time in
seconds (a float that only goes up). It first adds the tokens earned since the previous call
(`elapsed * refill_per_second`, never more than `capacity`), then: if at least one token is available,
remove one and return `True`; otherwise return `False`.""",
        "starter": r'''class TokenBucket:
    def __init__(self, capacity: int, refill_per_second: float):
        raise NotImplementedError("write me")

    def allow(self, now: float) -> bool:
        raise NotImplementedError("write me")
''',
        "solution": r'''class TokenBucket:
    def __init__(self, capacity: int, refill_per_second: float):
        self.capacity = capacity
        self.rate = refill_per_second
        self.tokens = float(capacity)
        self.last = None

    def allow(self, now: float) -> bool:
        if self.last is not None:
            self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False
''',
        "tests": r'''
def burst():
    b = solution.TokenBucket(3, 1)
    eq([b.allow(0.0) for _ in range(4)], [True, True, True, False])

def refill():
    b = solution.TokenBucket(3, 1)
    for _ in range(3):
        b.allow(0.0)
    eq(b.allow(0.5), False)          # only half a token earned so far
    eq(b.allow(1.0), True)           # one full token after one second
    eq(b.allow(1.0), False)

def capped():
    b = solution.TokenBucket(2, 1)
    b.allow(0.0); b.allow(0.0)
    eq([b.allow(100.0) for _ in range(3)], [True, True, False])   # never more than capacity

def fractional_rate():
    b = solution.TokenBucket(1, 0.5)  # one token every two seconds
    eq([b.allow(0.0), b.allow(1.0), b.allow(2.0)], [True, False, True])

check("starts full: a burst of 3, then rejected", burst)
check("refills over time", refill)
check("never holds more than capacity", capped)
check("works with fractional refill rates", fractional_rate)
''',
        "hints": ["Store `tokens` as a float and the time of the last call.",
                  "On each call: `tokens = min(capacity, tokens + elapsed * rate)`, then spend one if `tokens >= 1`."],
    },
    {
        "id": "py-up-interfaces",
        "language": "python",
        "title": "Parse a JSON device report",
        "topic": "Data formats",
        "level": "easy",
        "guide": "devnet-software-design",
        "task": """`json_text` is a JSON string like:
```json
{"device": "R1", "interfaces": [{"name": "Gi0/1", "status": "up"}, {"name": "Gi0/2", "status": "down"}]}
```
Write `up_interfaces(json_text)` returning the **names of interfaces whose status is "up"**, sorted alphabetically.
An interface without a `status` counts as down. Invalid JSON should raise `ValueError`
(`json.loads` already does: `JSONDecodeError` is a `ValueError`).""",
        "starter": r'''import json


def up_interfaces(json_text: str) -> list:
    raise NotImplementedError("write me")
''',
        "solution": r'''import json


def up_interfaces(json_text: str) -> list:
    data = json.loads(json_text)
    return sorted(i["name"] for i in data.get("interfaces", []) if i.get("status") == "up")
''',
        "tests": r'''
SAMPLE = '{"device": "R1", "interfaces": [{"name": "Gi0/3", "status": "up"}, {"name": "Gi0/2", "status": "down"}, {"name": "Gi0/1", "status": "up"}, {"name": "Lo0"}]}'
check("returns up interfaces sorted", lambda: eq(solution.up_interfaces(SAMPLE), ["Gi0/1", "Gi0/3"]))
check("no interfaces key gives []", lambda: eq(solution.up_interfaces('{"device": "R2"}'), []))
check("invalid JSON raises ValueError", lambda: raises(ValueError, solution.up_interfaces, "{device: R1}"))
''',
        "hints": ["`json.loads(text)` turns the JSON text into a dict.",
                  "Use `.get(\"status\")` so a missing key doesn't crash, and `sorted(...)` at the end."],
    },
    {
        "id": "py-n-plus-one",
        "language": "python",
        "title": "Fix an N+1 query",
        "topic": "Performance",
        "level": "medium",
        "guide": "performance",
        "task": """Tables: `authors(id, name)` and `books(id, title, author_id)`.
`db.query(sql, params=())` runs SQL (SQLite) and returns a list of dict rows. It also counts the queries.

Write `titles_by_author(db)` that returns `{author_name: [titles sorted A-Z]}` for **every** author
(authors without books get `[]`), using **at most 2 queries**. A query per author is the N+1 problem.""",
        "starter": r'''def titles_by_author(db) -> dict:
    # The slow way (N+1) would be: one query for authors, then one per author.
    raise NotImplementedError("write me")
''',
        "solution": r'''def titles_by_author(db) -> dict:
    result = {row["name"]: [] for row in db.query("SELECT name FROM authors")}
    rows = db.query("SELECT authors.name AS author, books.title AS title "
                    "FROM books JOIN authors ON authors.id = books.author_id ORDER BY books.title")
    for row in rows:
        result[row["author"]].append(row["title"])
    return result
''',
        "tests": r'''
import sqlite3

class CountingDB:
    def __init__(self, authors, books):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT)")
        self.conn.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, author_id INTEGER)")
        self.conn.executemany("INSERT INTO authors VALUES (?, ?)", authors)
        self.conn.executemany("INSERT INTO books VALUES (?, ?, ?)", books)
        self.queries = 0

    def query(self, sql, params=()):
        self.queries += 1
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

def make_db(n_authors=30):
    authors = [(i, f"Author {i:02d}") for i in range(1, n_authors + 1)]
    books = [(i, f"Book {chr(90 - i % 26)}{i}", (i % (n_authors - 1)) + 1) for i in range(1, 60)]
    return CountingDB(authors, books), authors, books

def correct():
    db, authors, books = make_db()
    expected = {name: sorted(t for (_, t, a) in books if a == aid) for aid, name in authors}
    eq(solution.titles_by_author(db), expected)

def few_queries():
    db, _, _ = make_db()
    solution.titles_by_author(db)
    if db.queries > 2:
        raise AssertionError(f"used {db.queries} queries for 30 authors; that's N+1. Use a JOIN (at most 2 queries).")

def author_without_books():
    db = CountingDB([(1, "Ada"), (2, "Linus")], [(1, "Notes", 1)])
    eq(solution.titles_by_author(db), {"Ada": ["Notes"], "Linus": []})

check("correct titles for every author", correct)
check("at most 2 queries (no N+1)", few_queries)
check("authors without books get []", author_without_books)
''',
        "hints": ["First query: all authors, to start every list as `[]`.",
                  "Second query: `SELECT authors.name, books.title FROM books JOIN authors ON authors.id = books.author_id ORDER BY books.title`, then group in Python."],
    },
    # ------------------------------------------------------------------ JavaScript
    {
        "id": "js-build-url",
        "language": "javascript",
        "title": "Build an API URL with query parameters",
        "topic": "APIs",
        "level": "easy",
        "guide": "devnet-apis",
        "task": """Write `buildUrl(base, path, params)` that joins `base` and `path` with exactly one `/` between them,
and adds `params` as a query string (properly encoded). Skip params whose value is `undefined` or `null`.
No `?` when there are no params.

`buildUrl("https://api.example.com/v1/", "/books", { page: 2, author: "Roy Fielding" })`
→ `"https://api.example.com/v1/books?page=2&author=Roy+Fielding"` (`%20` instead of `+` is fine too).""",
        "starter": r'''export function buildUrl(base, path, params = {}) {
  throw new Error("write me");
}
''',
        "solution": r'''export function buildUrl(base, path, params = {}) {
  const url = new URL(base.replace(/\/+$/, "") + "/" + path.replace(/^\/+/, ""));
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) url.searchParams.append(key, String(value));
  }
  return url.toString();
}
''',
        "tests": r'''
function parts(u) { const x = new URL(u); return { path: x.origin + x.pathname, query: [...x.searchParams.entries()], raw: u }; }
await check("joins base and path with one slash", () => eq(parts(solution.buildUrl("https://api.example.com/v1/", "/books")).path, "https://api.example.com/v1/books"));
await check("works without slashes too", () => eq(parts(solution.buildUrl("https://api.example.com/v1", "books")).path, "https://api.example.com/v1/books"));
await check("adds encoded params", () => eq(parts(solution.buildUrl("https://api.example.com/v1/", "/books", { page: 2, author: "Roy Fielding" })).query, [["page", "2"], ["author", "Roy Fielding"]]));
await check("encodes & and = inside values", () => eq(parts(solution.buildUrl("https://x.test", "search", { q: "a&b=c" })).query, [["q", "a&b=c"]]));
await check("skips undefined and null", () => eq(parts(solution.buildUrl("https://x.test", "books", { a: undefined, b: null, c: 0 })).query, [["c", "0"]]));
await check("no ? without params", () => eq(solution.buildUrl("https://x.test/", "books", {}).includes("?"), false));
''',
        "hints": ["`new URL(...)` plus `url.searchParams.append(key, value)` does the encoding for you.",
                  "Trim slashes: `base.replace(/\\/+$/, \"\")` and `path.replace(/^\\/+/, \"\")`."],
    },
    {
        "id": "js-debounce",
        "language": "javascript",
        "title": "Debounce an input handler",
        "topic": "Performance",
        "level": "medium",
        "guide": "performance",
        "task": """Write `debounce(fn, ms)` that returns a new function. Calling it schedules `fn` to run after `ms`
milliseconds; calling it again before that **restarts the wait**. `fn` gets the arguments of the **last** call.
(Used for search-as-you-type: search once the user pauses.)""",
        "starter": r'''export function debounce(fn, ms) {
  throw new Error("write me");
}
''',
        "solution": r'''export function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
''',
        "tests": r'''
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await check("rapid calls run fn once, with the last arguments", async () => {
  const calls = [];
  const d = solution.debounce((x) => calls.push(x), 40);
  d("a"); d("ab"); d("abc");
  eq(calls, []);
  await sleep(120);
  eq(calls, ["abc"]);
});
await check("calls spaced apart each run", async () => {
  const calls = [];
  const d = solution.debounce((x) => calls.push(x), 20);
  d(1); await sleep(80); d(2); await sleep(80);
  eq(calls, [1, 2]);
});
await check("passes all arguments", async () => {
  let got = null;
  const d = solution.debounce((...args) => { got = args; }, 10);
  d(1, "two", { three: 3 }); await sleep(60);
  eq(got, [1, "two", { three: 3 }]);
});
''',
        "hints": ["Keep the timer id in a variable outside the returned function (a closure).",
                  "Each call: `clearTimeout(timer)` then `timer = setTimeout(() => fn(...args), ms)`."],
    },
    {
        "id": "js-retry",
        "language": "javascript",
        "title": "Retry with exponential backoff",
        "topic": "APIs",
        "level": "medium",
        "guide": "api-strategies",
        "task": """Write `async retryRequest(send, { retries = 3, baseMs = 100, sleep })`.
`send()` returns a promise of `{ status, retryAfter }` (`retryAfter` in seconds, or undefined).

- Status **429, 502, 503 or 504** is temporary: wait, then call `send()` again, at most `retries` extra times.
- Wait `retryAfter * 1000` ms when given, otherwise `baseMs * 2 ** attempt` (100, 200, 400… for attempt 0, 1, 2…).
- Any other status: return the response immediately (don't retry a 404!).
- When retries run out, return the last response.

Use the `sleep(ms)` function you're given to wait (the tests use it to check your delays).""",
        "starter": r'''export async function retryRequest(send, { retries = 3, baseMs = 100, sleep } = {}) {
  throw new Error("write me");
}
''',
        "solution": r'''const TEMPORARY = [429, 502, 503, 504];

export async function retryRequest(send, { retries = 3, baseMs = 100, sleep } = {}) {
  for (let attempt = 0; ; attempt++) {
    const res = await send();
    if (!TEMPORARY.includes(res.status) || attempt >= retries) return res;
    await sleep(res.retryAfter !== undefined ? res.retryAfter * 1000 : baseMs * 2 ** attempt);
  }
}
''',
        "tests": r'''
function scripted(statuses) {
  const queue = statuses.map((s) => (typeof s === "number" ? { status: s } : s));
  let calls = 0;
  return { send: async () => { calls++; return queue.shift() ?? { status: 200 }; }, calls: () => calls };
}
function recorder() { const delays = []; return { sleep: async (ms) => { delays.push(ms); }, delays }; }

await check("success first time: no waiting", async () => {
  const s = scripted([200]); const r = recorder();
  eq((await solution.retryRequest(s.send, { sleep: r.sleep })).status, 200);
  eq(r.delays, []);
});
await check("503, 503, 200: waits 100 then 200 ms", async () => {
  const s = scripted([503, 503, 200]); const r = recorder();
  eq((await solution.retryRequest(s.send, { sleep: r.sleep })).status, 200);
  eq(r.delays, [100, 200]);
});
await check("uses Retry-After when given", async () => {
  const s = scripted([{ status: 429, retryAfter: 2 }, 200]); const r = recorder();
  await solution.retryRequest(s.send, { sleep: r.sleep });
  eq(r.delays, [2000]);
});
await check("404 is returned at once, never retried", async () => {
  const s = scripted([404, 200]); const r = recorder();
  eq((await solution.retryRequest(s.send, { sleep: r.sleep })).status, 404);
  eq(s.calls(), 1);
});
await check("gives up after `retries` extra attempts", async () => {
  const s = scripted([503, 503, 503, 503, 503]); const r = recorder();
  eq((await solution.retryRequest(s.send, { retries: 2, sleep: r.sleep })).status, 503);
  eq(s.calls(), 3);
  eq(r.delays, [100, 200]);
});
''',
        "hints": ["A `for (let attempt = 0; ; attempt++)` loop that returns when done works well.",
                  "Return immediately if the status isn't temporary OR `attempt >= retries`; otherwise `await sleep(...)`."],
    },
    {
        "id": "js-link-header",
        "language": "javascript",
        "title": "Parse a pagination Link header",
        "topic": "APIs",
        "level": "medium",
        "guide": "api-strategies",
        "task": """APIs like GitHub's return pagination links in a header:
```
<https://api.x.test/books?page=3>; rel="next", <https://api.x.test/books?page=9>; rel="last"
```
Write `parseLinkHeader(header)` returning an object mapping each `rel` to its URL:
`{ next: "https://api.x.test/books?page=3", last: "https://api.x.test/books?page=9" }`.
Return `{}` for an empty, `null` or `undefined` header. Ignore extra spaces.""",
        "starter": r'''export function parseLinkHeader(header) {
  throw new Error("write me");
}
''',
        "solution": r'''export function parseLinkHeader(header) {
  const links = {};
  if (!header) return links;
  for (const part of header.split(",")) {
    const match = part.match(/<([^>]+)>\s*;\s*rel="?([^";]+)"?/);
    if (match) links[match[2].trim()] = match[1].trim();
  }
  return links;
}
''',
        "tests": r'''
await check("next and last", () => eq(solution.parseLinkHeader('<https://api.x.test/books?page=3>; rel="next", <https://api.x.test/books?page=9>; rel="last"'),
  { next: "https://api.x.test/books?page=3", last: "https://api.x.test/books?page=9" }));
await check("four links with extra spaces", () => eq(Object.keys(solution.parseLinkHeader(' <a?page=1>;  rel="first" ,<a?page=2>; rel="prev",  <a?page=4>; rel="next", <a?page=9>; rel="last" ')).sort(),
  ["first", "last", "next", "prev"]));
await check("empty or missing header gives {}", () => { eq(solution.parseLinkHeader(""), {}); eq(solution.parseLinkHeader(null), {}); eq(solution.parseLinkHeader(undefined), {}); });
''',
        "hints": ["Split the header on `,` to get each link.",
                  "A regular expression like `/<([^>]+)>\\s*;\\s*rel=\"?([^\";]+)\"?/` captures the URL and the rel."],
    },
    # ------------------------------------------------------------------ TypeScript
    {
        "id": "ts-parse-book",
        "language": "typescript",
        "title": "Validate untrusted JSON with types",
        "topic": "APIs",
        "level": "medium",
        "guide": "api-strategies",
        "task": """Data from an API or a request body is `unknown` until you check it. Write
`parseBook(input: unknown): Result<Book>` (types are in the starter).

Rules:
- `input` must be a non-null object (not an array), else errors `["body must be a JSON object"]`.
- `title` and `author` must be non-empty strings after trimming (store them trimmed), else
  `"title is required"` / `"author is required"`.
- `year` is optional: missing or `null` → `null`; otherwise it must be a whole number from 0 to 2100,
  else `"year must be a whole number between 0 and 2100"`.
- Return `{ ok: true, value }` when valid, or `{ ok: false, errors }` with errors in the order title, author, year.

(Node runs your TypeScript by removing the types; it doesn't type-check. In a real project run `npx tsc --noEmit`.)""",
        "starter": r'''export interface Book {
  title: string;
  author: string;
  year: number | null;
}

export type Result<T> = { ok: true; value: T } | { ok: false; errors: string[] };

export function parseBook(input: unknown): Result<Book> {
  throw new Error("write me");
}
''',
        "solution": r'''export interface Book {
  title: string;
  author: string;
  year: number | null;
}

export type Result<T> = { ok: true; value: T } | { ok: false; errors: string[] };

export function parseBook(input: unknown): Result<Book> {
  if (typeof input !== "object" || input === null || Array.isArray(input)) {
    return { ok: false, errors: ["body must be a JSON object"] };
  }
  const data = input as Record<string, unknown>;
  const errors: string[] = [];
  const title = typeof data.title === "string" ? data.title.trim() : "";
  const author = typeof data.author === "string" ? data.author.trim() : "";
  if (!title) errors.push("title is required");
  if (!author) errors.push("author is required");
  let year: number | null = null;
  if (data.year !== undefined && data.year !== null) {
    if (typeof data.year === "number" && Number.isInteger(data.year) && data.year >= 0 && data.year <= 2100) {
      year = data.year;
    } else {
      errors.push("year must be a whole number between 0 and 2100");
    }
  }
  return errors.length ? { ok: false, errors } : { ok: true, value: { title, author, year } };
}
''',
        "tests": r'''
await check("valid book, trimmed", () => eq(solution.parseBook({ title: "  REST in Practice ", author: "Webber", year: 2010 }),
  { ok: true, value: { title: "REST in Practice", author: "Webber", year: 2010 } }));
await check("year is optional", () => eq(solution.parseBook({ title: "T", author: "A" }), { ok: true, value: { title: "T", author: "A", year: null } }));
await check("missing title and author", () => eq(solution.parseBook({ title: "  ", year: 1999 }), { ok: false, errors: ["title is required", "author is required"] }));
await check("bad year", () => eq(solution.parseBook({ title: "T", author: "A", year: 19.5 }), { ok: false, errors: ["year must be a whole number between 0 and 2100"] }));
await check("year as a string is invalid", () => eq(solution.parseBook({ title: "T", author: "A", year: "2001" }).ok, false));
await check("not an object", () => { for (const bad of [null, "book", 42, ["T", "A"]]) eq(solution.parseBook(bad), { ok: false, errors: ["body must be a JSON object"] }); });
''',
        "hints": ["Check `typeof input === \"object\" && input !== null && !Array.isArray(input)` first.",
                  "Then treat it as `Record<string, unknown>` and check each field's `typeof`; `Number.isInteger` checks whole numbers."],
    },
    {
        "id": "ts-collect-cursor",
        "language": "typescript",
        "title": "Collect all pages with a cursor",
        "topic": "APIs",
        "level": "medium",
        "guide": "api-strategies",
        "task": """Some APIs page with a **cursor**: each response gives the cursor for the next page.

Write `collectAll<T>(fetchPage, maxPages = 100)`. `fetchPage(cursor?)` returns a promise of
`{ items: T[]; nextCursor?: string | null }`. Call it first with no cursor, then with each `nextCursor`,
until `nextCursor` is missing, `null` or `""`. Return all items in order.
If more than `maxPages` pages would be fetched, throw an `Error` (protects against an endless loop).""",
        "starter": r'''export interface Page<T> {
  items: T[];
  nextCursor?: string | null;
}

export async function collectAll<T>(fetchPage: (cursor?: string) => Promise<Page<T>>, maxPages = 100): Promise<T[]> {
  throw new Error("write me");
}
''',
        "solution": r'''export interface Page<T> {
  items: T[];
  nextCursor?: string | null;
}

export async function collectAll<T>(fetchPage: (cursor?: string) => Promise<Page<T>>, maxPages = 100): Promise<T[]> {
  const all: T[] = [];
  let cursor: string | undefined = undefined;
  for (let pages = 1; ; pages++) {
    if (pages > maxPages) throw new Error(`stopped after ${maxPages} pages`);
    const page: Page<T> = await fetchPage(cursor);
    all.push(...page.items);
    if (!page.nextCursor) return all;
    cursor = page.nextCursor;
  }
}
''',
        "tests": r'''
function api(pages) {
  const cursors = [];
  return { cursors, fetchPage: async (cursor) => { cursors.push(cursor); const i = cursor ? Number(cursor) : 0; return pages[i]; } };
}
await check("three pages in order", async () => {
  const a = api([{ items: [1, 2], nextCursor: "1" }, { items: [3], nextCursor: "2" }, { items: [4, 5] }]);
  eq(await solution.collectAll(a.fetchPage), [1, 2, 3, 4, 5]);
  eq(a.cursors, [undefined, "1", "2"]);
});
await check("stops on null or empty cursor", async () => {
  eq(await solution.collectAll(api([{ items: ["a"], nextCursor: null }]).fetchPage), ["a"]);
  eq(await solution.collectAll(api([{ items: ["b"], nextCursor: "" }]).fetchPage), ["b"]);
});
await check("throws after maxPages pages instead of looping forever", async () => {
  let calls = 0;
  const endless = async () => { calls++; return { items: [1], nextCursor: "again" }; };
  let threw = false;
  try { await solution.collectAll(endless, 5); } catch (e) { threw = e instanceof Error; }
  eq({ threw, calls }, { threw: true, calls: 5 });
});
''',
        "hints": ["Keep a `cursor` variable that starts `undefined` and is replaced by `page.nextCursor`.",
                  "Count pages and `throw new Error(...)` when the count passes `maxPages`."],
    },
    {
        "id": "ts-rate-limit",
        "language": "typescript",
        "title": "Read rate-limit headers",
        "topic": "Rate limits",
        "level": "easy",
        "guide": "devnet-apis",
        "task": """Write `parseRateLimit(headers, nowSeconds)`. `headers` is an object of header names to values; names can
be in **any letter case**. Read `X-RateLimit-Limit`, `X-RateLimit-Remaining` and `X-RateLimit-Reset`
(the reset time in Unix seconds) and return `{ limit, remaining, resetInSeconds }` as numbers, where
`resetInSeconds = max(0, reset - nowSeconds)`. Return `null` if any of the three is missing or not a number.""",
        "starter": r'''export interface RateLimit {
  limit: number;
  remaining: number;
  resetInSeconds: number;
}

export function parseRateLimit(headers: Record<string, string | undefined>, nowSeconds: number): RateLimit | null {
  throw new Error("write me");
}
''',
        "solution": r'''export interface RateLimit {
  limit: number;
  remaining: number;
  resetInSeconds: number;
}

export function parseRateLimit(headers: Record<string, string | undefined>, nowSeconds: number): RateLimit | null {
  const lower: Record<string, string | undefined> = {};
  for (const [name, value] of Object.entries(headers)) lower[name.toLowerCase()] = value;
  const read = (name: string) => {
    const raw = lower[name];
    const n = raw === undefined || raw.trim() === "" ? NaN : Number(raw);
    return Number.isFinite(n) ? n : null;
  };
  const limit = read("x-ratelimit-limit");
  const remaining = read("x-ratelimit-remaining");
  const reset = read("x-ratelimit-reset");
  if (limit === null || remaining === null || reset === null) return null;
  return { limit, remaining, resetInSeconds: Math.max(0, reset - nowSeconds) };
}
''',
        "tests": r'''
await check("reads the three headers", () => eq(solution.parseRateLimit({ "X-RateLimit-Limit": "10", "X-RateLimit-Remaining": "3", "X-RateLimit-Reset": "1700000060" }, 1700000000),
  { limit: 10, remaining: 3, resetInSeconds: 60 }));
await check("header names in any case", () => eq(solution.parseRateLimit({ "x-ratelimit-limit": "5", "X-RATELIMIT-REMAINING": "0", "x-RateLimit-Reset": "100" }, 90),
  { limit: 5, remaining: 0, resetInSeconds: 10 }));
await check("reset in the past gives 0", () => eq(solution.parseRateLimit({ "X-RateLimit-Limit": "5", "X-RateLimit-Remaining": "5", "X-RateLimit-Reset": "50" }, 90).resetInSeconds, 0));
await check("missing or invalid header gives null", () => {
  eq(solution.parseRateLimit({ "X-RateLimit-Limit": "5", "X-RateLimit-Remaining": "5" }, 0), null);
  eq(solution.parseRateLimit({ "X-RateLimit-Limit": "lots", "X-RateLimit-Remaining": "5", "X-RateLimit-Reset": "9" }, 0), null);
});
''',
        "hints": ["Copy the headers into a new object with lower-case names first.",
                  "`Number(\"10\")` is 10; `Number(\"lots\")` is NaN; check with `Number.isFinite`."],
    },
    # ------------------------------------------------------------------ PHP
    {
        "id": "php-status-category",
        "language": "php",
        "title": "Classify HTTP status codes (PHP)",
        "topic": "APIs",
        "level": "easy",
        "guide": "devnet-apis",
        "task": """Write `statusCategory(int $code): string` returning `"informational"`, `"success"`, `"redirection"`,
`"client error"` or `"server error"`. Throw an `InvalidArgumentException` for codes outside 100–599.""",
        "starter": r'''<?php

function statusCategory(int $code): string
{
    throw new Exception('write me');
}
''',
        "solution": r'''<?php

function statusCategory(int $code): string
{
    if ($code < 100 || $code > 599) {
        throw new InvalidArgumentException("Not an HTTP status code: $code");
    }
    return match (intdiv($code, 100)) {
        1 => 'informational',
        2 => 'success',
        3 => 'redirection',
        4 => 'client error',
        5 => 'server error',
    };
}
''',
        "tests": r'''
check('200 is success', fn() => eq(statusCategory(200), 'success'));
check('102 is informational', fn() => eq(statusCategory(102), 'informational'));
check('301 is redirection', fn() => eq(statusCategory(301), 'redirection'));
check('403 is client error', fn() => eq(statusCategory(403), 'client error'));
check('504 is server error', fn() => eq(statusCategory(504), 'server error'));
check('42 throws InvalidArgumentException', fn() => throws(InvalidArgumentException::class, fn() => statusCategory(42)));
check('700 throws InvalidArgumentException', fn() => throws(InvalidArgumentException::class, fn() => statusCategory(700)));
''',
        "hints": ["`intdiv($code, 100)` gives the first digit.",
                  "PHP 8's `match` expression is a neat way to map 1–5 to the names."],
    },
    {
        "id": "php-validate-book",
        "language": "php",
        "title": "Validate a POST body",
        "topic": "APIs",
        "level": "easy",
        "guide": "api-strategies",
        "task": """An API endpoint receives `$input` (from `json_decode($body, true)`). Write `validateBook(array $input): array`
returning a list of error messages (an empty array when valid), in this order:
- `"title is required"` if `title` is missing or blank after trimming (or not a string),
- `"author is required"` likewise for `author`,
- `"year must be a whole number between 0 and 2100"` if `year` is present, not `null`, and not an integer in that range.

The endpoint would answer **400** with these errors, or **201** when there are none.""",
        "starter": r'''<?php

function validateBook(array $input): array
{
    throw new Exception('write me');
}
''',
        "solution": r'''<?php

function validateBook(array $input): array
{
    $errors = [];
    foreach (['title', 'author'] as $field) {
        $value = $input[$field] ?? null;
        if (!is_string($value) || trim($value) === '') {
            $errors[] = "$field is required";
        }
    }
    if (array_key_exists('year', $input) && $input['year'] !== null) {
        $year = $input['year'];
        if (!is_int($year) || $year < 0 || $year > 2100) {
            $errors[] = 'year must be a whole number between 0 and 2100';
        }
    }
    return $errors;
}
''',
        "tests": r'''
check('valid book has no errors', fn() => eq(validateBook(['title' => 'REST', 'author' => 'Fielding', 'year' => 2000]), []));
check('year is optional', fn() => eq(validateBook(['title' => 'REST', 'author' => 'Fielding']), []));
check('null year is fine', fn() => eq(validateBook(['title' => 'REST', 'author' => 'Fielding', 'year' => null]), []));
check('missing title and author', fn() => eq(validateBook([]), ['title is required', 'author is required']));
check('blank title', fn() => eq(validateBook(['title' => '   ', 'author' => 'A']), ['title is required']));
check('year out of range', fn() => eq(validateBook(['title' => 'T', 'author' => 'A', 'year' => 3000]), ['year must be a whole number between 0 and 2100']));
check('year as text is invalid', fn() => eq(validateBook(['title' => 'T', 'author' => 'A', 'year' => '1999']), ['year must be a whole number between 0 and 2100']));
''',
        "hints": ["`$input['title'] ?? null` avoids warnings for missing keys.",
                  "Use `is_string`, `trim`, `array_key_exists` and `is_int`."],
    },
    {
        "id": "php-paginate",
        "language": "php",
        "title": "Paginate a list",
        "topic": "Performance",
        "level": "easy",
        "guide": "performance",
        "task": """Write `paginate(array $items, int $page, int $perPage): array` that returns
`['items' => ..., 'page' => ..., 'per_page' => ..., 'total' => ..., 'pages' => ...]`.

- `$page` below 1 becomes 1; `$perPage` is limited to 1–100.
- `pages` = number of pages needed (0 when there are no items).
- `items` = that page's items as a list (re-indexed from 0); `[]` for a page past the end.""",
        "starter": r'''<?php

function paginate(array $items, int $page, int $perPage): array
{
    throw new Exception('write me');
}
''',
        "solution": r'''<?php

function paginate(array $items, int $page, int $perPage): array
{
    $page = max(1, $page);
    $perPage = min(100, max(1, $perPage));
    $total = count($items);
    return [
        'items' => array_values(array_slice($items, ($page - 1) * $perPage, $perPage)),
        'page' => $page,
        'per_page' => $perPage,
        'total' => $total,
        'pages' => (int) ceil($total / $perPage),
    ];
}
''',
        "tests": r'''
$letters = range('a', 'k'); // 11 items
check('first page', fn() => eq(paginate($letters, 1, 5)['items'], ['a', 'b', 'c', 'd', 'e']));
check('last partial page', fn() => eq(paginate($letters, 3, 5)['items'], ['k']));
check('totals', function () use ($letters) { $p = paginate($letters, 2, 5); eq([$p['page'], $p['per_page'], $p['total'], $p['pages']], [2, 5, 11, 3]); });
check('page past the end is empty', fn() => eq(paginate($letters, 9, 5)['items'], []));
check('page 0 becomes 1', fn() => eq(paginate($letters, 0, 5)['page'], 1));
check('per_page limited to 1..100', function () use ($letters) { eq(paginate($letters, 1, 0)['per_page'], 1); eq(paginate($letters, 1, 500)['per_page'], 100); });
check('no items', fn() => eq(paginate([], 1, 10)['pages'], 0));
''',
        "hints": ["`array_slice($items, ($page - 1) * $perPage, $perPage)` cuts out one page.",
                  "`(int) ceil($total / $perPage)` counts pages; clamp with `max` and `min`."],
    },
    {
        "id": "php-match-route",
        "language": "php",
        "title": "A tiny router (front controller)",
        "topic": "File structure",
        "level": "medium",
        "guide": "project-structure",
        "task": """In a front controller (`public/index.php`), every URL is matched against route patterns.
Write `matchRoute(string $pattern, string $path): ?array`:
- Patterns look like `/books/{id}` or `/users/{userId}/orders/{orderId}`.
- Return the parameters as an array (`['id' => '42']`) when the path matches, `[]` for a match without
  parameters, and `null` when it doesn't match.
- A parameter matches exactly one non-empty path segment. A trailing `/` on the path is ignored.""",
        "starter": r'''<?php

function matchRoute(string $pattern, string $path): ?array
{
    throw new Exception('write me');
}
''',
        "solution": r'''<?php

function matchRoute(string $pattern, string $path): ?array
{
    $patternParts = explode('/', trim($pattern, '/'));
    $pathParts = explode('/', trim($path, '/'));
    if (count($patternParts) !== count($pathParts)) {
        return null;
    }
    $params = [];
    foreach ($patternParts as $i => $part) {
        if (preg_match('/^\{(\w+)\}$/', $part, $m)) {
            if ($pathParts[$i] === '') {
                return null;
            }
            $params[$m[1]] = $pathParts[$i];
        } elseif ($part !== $pathParts[$i]) {
            return null;
        }
    }
    return $params;
}
''',
        "tests": r'''
check('one parameter', fn() => eq(matchRoute('/books/{id}', '/books/42'), ['id' => '42']));
check('two parameters', fn() => eq(matchRoute('/users/{userId}/orders/{orderId}', '/users/7/orders/99'), ['userId' => '7', 'orderId' => '99']));
check('static route', fn() => eq(matchRoute('/books', '/books'), []));
check('trailing slash is ignored', fn() => eq(matchRoute('/books/{id}', '/books/42/'), ['id' => '42']));
check('different path does not match', fn() => eq(matchRoute('/books/{id}', '/authors/42'), null));
check('extra segment does not match', fn() => eq(matchRoute('/books/{id}', '/books/42/reviews'), null));
check('missing parameter does not match', fn() => eq(matchRoute('/books/{id}', '/books/'), null));
''',
        "hints": ["Split both on `/` after `trim($x, '/')`, and compare the segment counts first.",
                  "A segment like `{id}` matches anything non-empty: `preg_match('/^\\{(\\w+)\\}$/', $part, $m)` gives the name in `$m[1]`."],
    },
    {
        "id": "php-basic-auth",
        "language": "php",
        "title": "Read a Basic auth header",
        "topic": "APIs",
        "level": "easy",
        "guide": "devnet-apis",
        "task": """Write `parseBasicAuth(?string $header): ?array` for the server side of Basic authentication.
Given `"Basic bGVhcm5lcjpkZXZuZXQxMjM="`, return `['user' => 'learner', 'pass' => 'devnet123']`.
Return `null` when the header is missing, isn't `Basic` (the word is case-insensitive), isn't valid Base64,
or has no `:`. The password itself may contain `:` (split on the **first** colon only).""",
        "starter": r'''<?php

function parseBasicAuth(?string $header): ?array
{
    throw new Exception('write me');
}
''',
        "solution": r'''<?php

function parseBasicAuth(?string $header): ?array
{
    if ($header === null || !preg_match('/^Basic\s+(\S+)$/i', trim($header), $m)) {
        return null;
    }
    $decoded = base64_decode($m[1], true);
    if ($decoded === false || !str_contains($decoded, ':')) {
        return null;
    }
    [$user, $pass] = explode(':', $decoded, 2);
    return ['user' => $user, 'pass' => $pass];
}
''',
        "tests": r'''
check('decodes user and password', fn() => eq(parseBasicAuth('Basic bGVhcm5lcjpkZXZuZXQxMjM='), ['user' => 'learner', 'pass' => 'devnet123']));
check('password may contain a colon', fn() => eq(parseBasicAuth('Basic ' . base64_encode('ana:p:w')), ['user' => 'ana', 'pass' => 'p:w']));
check('"basic" in lower case works', fn() => eq(parseBasicAuth('basic ' . base64_encode('a:b')), ['user' => 'a', 'pass' => 'b']));
check('missing header', fn() => eq(parseBasicAuth(null), null));
check('Bearer is not Basic', fn() => eq(parseBasicAuth('Bearer abc.def'), null));
check('invalid Base64', fn() => eq(parseBasicAuth('Basic !!!'), null));
check('no colon', fn() => eq(parseBasicAuth('Basic ' . base64_encode('justuser')), null));
''',
        "hints": ["`base64_decode($text, true)` returns `false` for invalid input (strict mode).",
                  "`explode(':', $decoded, 2)` splits on the first colon only."],
    },
    # ------------------------------------------------------------------ business rules
    {
        "id": "py-shipping-rules",
        "language": "python",
        "title": "Business rules: shipping fee decision table",
        "topic": "Business rules",
        "level": "medium",
        "guide": "business-rules",
        "task": """Implement this decision table as `shipping_fee(total, member, region)`, returning a tuple
`(fee, rule_id)`. `region` is `"metro"` or `"province"`. Rows are checked from the top; the first match wins.

| Rule | Member? | Order total | Region | Fee |
|---|---|---|---|---|
| R1 | any | 5,000 or more | any | 0 |
| R2 | yes | under 5,000 | metro | 0 |
| R3 | yes | under 5,000 | province | 80 |
| R4 | no | under 5,000 | metro | 100 |
| R5 | no | under 5,000 | province | 180 |

Raise `ValueError` for a negative total or an unknown region.""",
        "starter": r'''def shipping_fee(total: float, member: bool, region: str) -> tuple:
    """Return (fee, rule_id) following the decision table."""
    raise NotImplementedError("write me")
''',
        "solution": r'''FREE_FROM = 5000


def shipping_fee(total: float, member: bool, region: str) -> tuple:
    """Return (fee, rule_id) following the decision table."""
    if total < 0:
        raise ValueError("total cannot be negative")
    if region not in ("metro", "province"):
        raise ValueError(f"unknown region: {region}")
    if total >= FREE_FROM:
        return 0, "R1"
    if member:
        return (0, "R2") if region == "metro" else (80, "R3")
    return (100, "R4") if region == "metro" else (180, "R5")
''',
        "tests": r'''
check("R1: exactly 5,000 ships free (the boundary)", lambda: eq(solution.shipping_fee(5000, False, "province"), (0, "R1")))
check("R1 applies to members too", lambda: eq(solution.shipping_fee(12000, True, "metro"), (0, "R1")))
check("R2: member in metro", lambda: eq(solution.shipping_fee(4999.99, True, "metro"), (0, "R2")))
check("R3: member in the province", lambda: eq(solution.shipping_fee(1200, True, "province"), (80, "R3")))
check("R4: non-member in metro", lambda: eq(solution.shipping_fee(1200, False, "metro"), (100, "R4")))
check("R5: non-member in the province", lambda: eq(solution.shipping_fee(0, False, "province"), (180, "R5")))
check("negative total raises ValueError", lambda: raises(ValueError, solution.shipping_fee, -1, False, "metro"))
check("unknown region raises ValueError", lambda: raises(ValueError, solution.shipping_fee, 100, False, "moon"))
''',
        "hints": ["Check the invalid inputs first, then R1 (it wins over everything), then members, then everyone else.",
                  "`5000` itself must match R1, so use `>=`."],
    },
    {
        "id": "php-leave-rules",
        "language": "php",
        "title": "Business rules: approve a leave request",
        "topic": "Business rules",
        "level": "medium",
        "guide": "business-rules",
        "task": """HR's leave policy. Write `decideLeave(int $days, int $balance, int $noticeDays): array` returning
`['decision' => ..., 'rule' => ...]`, checking the rules in this order:

- **BR-1** `$days` must be at least 1, otherwise `decision` `"invalid"`.
- **BR-2** More days than the remaining `$balance` → `"rejected"`.
- **BR-3** Fewer than 3 days of notice for a leave of 3 days or more → `"rejected"`.
- **BR-4** Leaves longer than 5 days need a manager → `"needs_manager"`.
- Otherwise **BR-0** → `"approved"`.

`rule` is the id of the rule that decided (`"BR-1"` … `"BR-4"`, or `"BR-0"`).""",
        "starter": r'''<?php

function decideLeave(int $days, int $balance, int $noticeDays): array
{
    throw new Exception('write me');
}
''',
        "solution": r'''<?php

function decideLeave(int $days, int $balance, int $noticeDays): array
{
    if ($days < 1) {
        return ['decision' => 'invalid', 'rule' => 'BR-1'];
    }
    if ($days > $balance) {
        return ['decision' => 'rejected', 'rule' => 'BR-2'];
    }
    if ($days >= 3 && $noticeDays < 3) {
        return ['decision' => 'rejected', 'rule' => 'BR-3'];
    }
    if ($days > 5) {
        return ['decision' => 'needs_manager', 'rule' => 'BR-4'];
    }
    return ['decision' => 'approved', 'rule' => 'BR-0'];
}
''',
        "tests": r'''
check('BR-1: zero days is invalid', fn() => eq(decideLeave(0, 10, 7), ['decision' => 'invalid', 'rule' => 'BR-1']));
check('BR-2: more than the balance is rejected', fn() => eq(decideLeave(4, 3, 10), ['decision' => 'rejected', 'rule' => 'BR-2']));
check('BR-2: exactly the balance is fine', fn() => eq(decideLeave(3, 3, 10)['rule'], 'BR-0'));
check('BR-3: 3 days with 2 days notice is rejected', fn() => eq(decideLeave(3, 10, 2), ['decision' => 'rejected', 'rule' => 'BR-3']));
check('BR-3 does not apply to 2-day leaves', fn() => eq(decideLeave(2, 10, 0)['decision'], 'approved'));
check('BR-4: 6 days needs a manager', fn() => eq(decideLeave(6, 10, 14), ['decision' => 'needs_manager', 'rule' => 'BR-4']));
check('BR-4: exactly 5 days is approved', fn() => eq(decideLeave(5, 10, 14), ['decision' => 'approved', 'rule' => 'BR-0']));
check('rule order: balance is checked before notice', fn() => eq(decideLeave(8, 2, 0)['rule'], 'BR-2'));
''',
        "hints": ["Write one `if` per rule, in the order given, and `return` as soon as one decides.",
                  "Watch the boundaries: \"longer than 5\" is `> 5`; \"3 days or more\" is `>= 3`."],
    },
    {
        "id": "ts-discount-rules",
        "language": "typescript",
        "title": "Business rules: pick the best discount",
        "topic": "Business rules",
        "level": "medium",
        "guide": "business-rules",
        "task": """A shop's promo rules. Discounts **don't stack**: the customer gets the **single best** one.
Write `bestDiscount(cart: Cart): Discount` where the cart has `subtotal`, `items` (number of items),
`student` (boolean) and `coupon` (a string, or `null`).

- **STUDENT10**: students get 10% off.
- **BULK15**: 10 or more items get 15% off.
- **SAVE200**: coupon `"SAVE200"` gives ₱200 off, only if the subtotal is at least ₱1,000.
- No rule applies → `{ rule: "NONE", amount: 0 }`.

Return `{ rule, amount }` where `amount` is the money saved, rounded to 2 decimals. If two rules save the
same amount, prefer the one listed first above.""",
        "starter": r'''export interface Cart {
  subtotal: number;
  items: number;
  student: boolean;
  coupon: string | null;
}

export interface Discount {
  rule: "STUDENT10" | "BULK15" | "SAVE200" | "NONE";
  amount: number;
}

export function bestDiscount(cart: Cart): Discount {
  throw new Error("write me");
}
''',
        "solution": r'''export interface Cart {
  subtotal: number;
  items: number;
  student: boolean;
  coupon: string | null;
}

export interface Discount {
  rule: "STUDENT10" | "BULK15" | "SAVE200" | "NONE";
  amount: number;
}

const round2 = (n: number) => Math.round(n * 100) / 100;

export function bestDiscount(cart: Cart): Discount {
  const options: Discount[] = [];
  if (cart.student) options.push({ rule: "STUDENT10", amount: round2(cart.subtotal * 0.1) });
  if (cart.items >= 10) options.push({ rule: "BULK15", amount: round2(cart.subtotal * 0.15) });
  if (cart.coupon === "SAVE200" && cart.subtotal >= 1000) options.push({ rule: "SAVE200", amount: 200 });
  let best: Discount = { rule: "NONE", amount: 0 };
  for (const option of options) {
    if (option.amount > best.amount) best = option;  // ties keep the earlier rule
  }
  return best;
}
''',
        "tests": r'''
const cart = (over) => ({ subtotal: 1000, items: 1, student: false, coupon: null, ...over });
await check("no rule applies", () => eq(solution.bestDiscount(cart({})), { rule: "NONE", amount: 0 }));
await check("student gets 10%", () => eq(solution.bestDiscount(cart({ student: true, subtotal: 850 })), { rule: "STUDENT10", amount: 85 }));
await check("bulk beats student (15% > 10%)", () => eq(solution.bestDiscount(cart({ student: true, items: 12, subtotal: 2000 })), { rule: "BULK15", amount: 300 }));
await check("coupon needs a subtotal of at least 1,000", () => eq(solution.bestDiscount(cart({ coupon: "SAVE200", subtotal: 999.99 })), { rule: "NONE", amount: 0 }));
await check("coupon beats student on a small cart", () => eq(solution.bestDiscount(cart({ coupon: "SAVE200", student: true, subtotal: 1500 })), { rule: "SAVE200", amount: 200 }));
await check("a tie keeps the rule listed first", () => eq(solution.bestDiscount(cart({ student: true, coupon: "SAVE200", subtotal: 2000 })), { rule: "STUDENT10", amount: 200 }));
await check("amounts are rounded to 2 decimals", () => eq(solution.bestDiscount(cart({ student: true, subtotal: 333.33 })).amount, 33.33));
''',
        "hints": ["Collect every discount that applies into a list, then keep the largest amount.",
                  "Only replace the best when the new amount is strictly bigger: that keeps the earlier rule on a tie."],
    },
    {
        "id": "js-borrow-rules",
        "language": "javascript",
        "title": "Business rules: can this member borrow a book?",
        "topic": "Business rules",
        "level": "easy",
        "guide": "business-rules",
        "task": """A library's borrowing rules. Write `canBorrow(member, book)` returning
`{ allowed, reasons }`, where `reasons` lists **every** rule that blocks the loan (so the librarian can
explain all of them at once), in this order:

- `"MAX_LOANS"`: the member already has 5 or more books (`member.loans`).
- `"UNPAID_FINES"`: the member owes more than ₱100 in fines (`member.fines`).
- `"REFERENCE_ONLY"`: the book is a reference book (`book.reference === true`).
- `"NOT_AVAILABLE"`: the book has no copies left (`book.available === 0`).

`allowed` is `true` only when `reasons` is empty.""",
        "starter": r'''export function canBorrow(member, book) {
  throw new Error("write me");
}
''',
        "solution": r'''export function canBorrow(member, book) {
  const reasons = [];
  if (member.loans >= 5) reasons.push("MAX_LOANS");
  if (member.fines > 100) reasons.push("UNPAID_FINES");
  if (book.reference === true) reasons.push("REFERENCE_ONLY");
  if (book.available === 0) reasons.push("NOT_AVAILABLE");
  return { allowed: reasons.length === 0, reasons };
}
''',
        "tests": r'''
const member = (over) => ({ loans: 0, fines: 0, ...over });
const book = (over) => ({ reference: false, available: 2, ...over });
await check("an ordinary loan is allowed", () => eq(solution.canBorrow(member(), book()), { allowed: true, reasons: [] }));
await check("5 loans already: blocked", () => eq(solution.canBorrow(member({ loans: 5 }), book()), { allowed: false, reasons: ["MAX_LOANS"] }));
await check("4 loans is still fine", () => eq(solution.canBorrow(member({ loans: 4 }), book()).allowed, true));
await check("fines of exactly 100 are allowed", () => eq(solution.canBorrow(member({ fines: 100 }), book()).allowed, true));
await check("every blocking rule is listed, in order", () => eq(solution.canBorrow(member({ loans: 7, fines: 150 }), book({ reference: true, available: 0 })),
  { allowed: false, reasons: ["MAX_LOANS", "UNPAID_FINES", "REFERENCE_ONLY", "NOT_AVAILABLE"] }));
''',
        "hints": ["Don't return early: check every rule and push its code into a `reasons` array.",
                  "\"More than 100\" is `> 100`, so 100 itself is allowed."],
    },
]


def by_id(exercise_id: str) -> dict:
    for ex in EXERCISES:
        if ex["id"] == exercise_id:
            return ex
    raise FileNotFoundError(f"There is no exercise called '{exercise_id}'.")
