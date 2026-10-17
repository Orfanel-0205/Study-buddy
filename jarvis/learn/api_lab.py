"""API Lab: a practice REST API that runs inside Jarvis, so DevNet-style labs work offline.

It behaves like a real API on purpose: Basic / Bearer / API-key authentication, roles (401 vs 403),
JSON validation (400), wrong content type (415), duplicates (409), pagination headers, a token-bucket
rate limit (429 + Retry-After), an asynchronous job (202 + polling), a flaky endpoint for retries (503),
webhooks signed with HMAC, plus small SOAP and JSON-RPC endpoints to compare API styles.

Everything is in memory and resets when Jarvis restarts (or with POST /practice/lab/reset).
It is only reachable from this device: the computer's own browser/scripts (127.0.0.1) or, for Jarvis
on the phone, apps on the phone. Webhooks can only be delivered to addresses on this same device.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import math
import secrets
import time
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

PREFIX = "/practice/api/v1"
USERS = {"learner": ("devnet123", "editor"), "viewer": ("viewer123", "reader")}
API_KEYS = {"practice-key-123": ("api-key-app", "reader")}
BUCKET_CAPACITY = 10
REFILL_PER_SECOND = 1.0
TOKEN_LIFETIME = 3600
REPORT_SECONDS = 3.0
EVENTS = ["book.created", "book.updated", "book.deleted"]
MAX_BOOKS = 2000
MAX_BODY = 64_000

SEED_BOOKS = [
    ("Architectural Styles and the Design of Network-based Software Architectures", "Roy Fielding", 2000, "fielding-2000"),
    ("Design Patterns", "Gamma, Helm, Johnson, Vlissides", 1994, "978-0201633610"),
    ("The Pragmatic Programmer", "Andrew Hunt, David Thomas", 1999, "978-0201616224"),
    ("Clean Code", "Robert C. Martin", 2008, "978-0132350884"),
    ("Network Programmability and Automation", "Edelman, Lowe, Oswalt", 2018, "978-1491931257"),
    ("Lean Software Development", "Mary Poppendieck, Tom Poppendieck", 2003, "978-0321150783"),
    ("Pro Git", "Scott Chacon, Ben Straub", 2014, "978-1484200773"),
    ("RESTful Web APIs", "Leonard Richardson, Mike Amundsen", 2013, "978-1449358068"),
    ("Python Crash Course", "Eric Matthes", 2019, "978-1593279288"),
    ("Eloquent JavaScript", "Marijn Haverbeke", 2018, "978-1593279509"),
    ("Programming TypeScript", "Boris Cherny", 2019, "978-1492037651"),
    ("Modern PHP", "Josh Lockhart", 2015, "978-1491905012"),
    ("Laravel: Up & Running", "Matt Stauffer", 2023, "978-1098153267"),
    ("Designing Data-Intensive Applications", "Martin Kleppmann", 2017, "978-1449373320"),
    ("The Phoenix Project", "Gene Kim, Kevin Behr, George Spafford", 2013, "978-0988262591"),
    ("Refactoring", "Martin Fowler", 2018, "978-0134757599"),
    ("Test Driven Development: By Example", "Kent Beck", 2002, "978-0321146533"),
    ("Extreme Programming Explained", "Kent Beck", 2004, "978-0321278654"),
    ("You Don't Know JS Yet", "Kyle Simpson", 2020, "978-1673562916"),
    ("Fluent Python", "Luciano Ramalho", 2022, "978-1492056355"),
    ("Cisco DevNet Associate Study Guide", "Various", 2020, "devnet-200-901"),
    ("HTTP: The Definitive Guide", "David Gourley, Brian Totty", 2002, "978-1565925090"),
    ("The Mythical Man-Month", "Frederick P. Brooks Jr.", 1975, "978-0201835953"),
    ("Code Complete", "Steve McConnell", 2004, "978-0735619678"),
]


def _error(status: int, message: str, hint: str = "", headers: dict | None = None) -> JSONResponse:
    body = {"error": {"code": status, "message": message}}
    if hint:
        body["error"]["hint"] = hint
    return JSONResponse(body, status_code=status, headers=headers)


def is_loopback_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and (parts.hostname or "").lower() in ("127.0.0.1", "localhost", "::1")


class Bucket:
    def __init__(self):
        self.tokens = float(BUCKET_CAPACITY)
        self.last = time.monotonic()

    def take(self) -> tuple[bool, int, float]:
        """(allowed, remaining, seconds until full)"""
        now = time.monotonic()
        self.tokens = min(BUCKET_CAPACITY, self.tokens + (now - self.last) * REFILL_PER_SECOND)
        self.last = now
        allowed = self.tokens >= 1
        if allowed:
            self.tokens -= 1
        return allowed, int(self.tokens), (BUCKET_CAPACITY - self.tokens) / REFILL_PER_SECOND


class PracticeApi:
    def __init__(self):
        self._sending: set = set()
        self.transport = None  # tests deliver webhooks in-process; normally real HTTP on this device
        self.reset()

    def reset(self) -> None:
        self.books: dict[int, dict] = {}
        self.next_id = 1
        for title, author, year, isbn in SEED_BOOKS:
            self._insert({"title": title, "author": author, "year": year, "isbn": isbn})
        self.tokens: dict[str, tuple[str, str, float]] = {}
        self.buckets: dict[str, Bucket] = {}
        self.jobs: dict[str, dict] = {}
        self.flaky: dict[str, int] = {}
        self.webhooks: dict[str, dict] = {}
        self.inbox: list[dict] = []
        self.deliveries: list[dict] = []

    def _insert(self, data: dict) -> dict:
        book = {"id": self.next_id, "title": data["title"], "author": data["author"], "year": data.get("year"),
                "isbn": data.get("isbn") or None}
        self.books[book["id"]] = book
        self.next_id += 1
        return book

    # ---------------------------------------------------------------- authentication
    def identify(self, request: Request) -> dict:
        """Who is calling: {'user', 'role', 'method'} or {'error': JSONResponse}."""
        auth = request.headers.get("authorization", "")
        key = request.headers.get("x-api-key", "")
        if auth.lower().startswith("basic "):
            try:
                user, _, password = base64.b64decode(auth[6:].strip(), validate=True).decode("utf-8").partition(":")
            except (ValueError, UnicodeDecodeError):
                return {"error": _error(401, "The Basic credentials aren't valid Base64.",
                                        "Send base64('username:password').", {"WWW-Authenticate": 'Basic realm="practice"'})}
            known = USERS.get(user)
            if not known or not hmac.compare_digest(known[0], password):
                return {"error": _error(401, "Wrong username or password.", "Try learner / devnet123.",
                                        {"WWW-Authenticate": 'Basic realm="practice"'})}
            return {"user": user, "role": known[1], "method": "basic"}
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            entry = self.tokens.get(token)
            if not entry:
                return {"error": _error(401, "Unknown token.", "Get one with POST /practice/api/v1/auth/login (Basic auth).")}
            if entry[2] < time.time():
                return {"error": _error(401, "This token has expired.", "Log in again to get a new token.")}
            return {"user": entry[0], "role": entry[1], "method": "bearer", "token": token}
        if key:
            known = API_KEYS.get(key)
            if not known:
                return {"error": _error(401, "Unknown API key.", "The practice key is practice-key-123.")}
            return {"user": known[0], "role": known[1], "method": "api-key"}
        return {"error": _error(401, "Authentication required.",
                                "Send Basic auth, a Bearer token, or an X-API-Key header.",
                                {"WWW-Authenticate": 'Basic realm="practice", Bearer'})}

    def rate_limit(self, request: Request, who: dict) -> tuple[dict, JSONResponse | None]:
        client = request.client.host if request.client else "local"
        key = who.get("token") or who.get("user") or f"anonymous:{client}"
        bucket = self.buckets.setdefault(key, Bucket())
        allowed, remaining, until_full = bucket.take()
        headers = {"X-RateLimit-Limit": str(BUCKET_CAPACITY), "X-RateLimit-Remaining": str(remaining),
                   "X-RateLimit-Reset": str(int(time.time() + math.ceil(until_full)))}
        if allowed:
            return headers, None
        wait = max(1, math.ceil((1 - bucket.tokens) / REFILL_PER_SECOND))
        return headers, _error(429, "Too many requests: you've used all your tokens for now.",
                               f"Wait {wait} second(s) (see Retry-After), then try again. The bucket holds "
                               f"{BUCKET_CAPACITY} tokens and refills {REFILL_PER_SECOND:g} per second.",
                               {**headers, "Retry-After": str(wait)})

    # ---------------------------------------------------------------- webhooks
    def fire(self, event: str, data: dict) -> None:
        for hook in list(self.webhooks.values()):
            if event in hook["events"]:
                payload = json.dumps({"id": str(uuid.uuid4()), "event": event, "created": int(time.time()),
                                      "data": data}).encode()
                task = asyncio.ensure_future(self._deliver(hook, event, payload))
                self._sending.add(task)  # keep a reference until it finishes
                task.add_done_callback(self._sending.discard)

    async def _deliver(self, hook: dict, event: str, payload: bytes) -> None:
        signature = "sha256=" + hmac.new(hook["secret"].encode(), payload, hashlib.sha256).hexdigest()
        record = {"webhook": hook["id"], "event": event, "url": hook["url"], "at": time.strftime("%H:%M:%S"),
                  "status": None, "error": ""}
        try:
            async with httpx.AsyncClient(timeout=3.0, trust_env=False, transport=self.transport) as client:
                r = await client.post(hook["url"], content=payload, headers={
                    "Content-Type": "application/json", "X-Jarvis-Event": event,
                    "X-Jarvis-Delivery": str(uuid.uuid4()), "X-Jarvis-Signature": signature,
                    "User-Agent": "Jarvis-API-Lab-Webhooks/1"})
            record["status"] = r.status_code
        except httpx.HTTPError as exc:
            record["error"] = f"{type(exc).__name__}: {exc}" or "delivery failed"
        self.deliveries.insert(0, record)
        del self.deliveries[50:]

    def signature_valid(self, body: bytes, signature: str) -> bool | None:
        if not signature:
            return None
        for hook in self.webhooks.values():
            expected = "sha256=" + hmac.new(hook["secret"].encode(), body, hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected, signature):
                return True
        return False


def _book_errors(data, partial: bool, existing: dict | None, books: dict[int, dict]) -> tuple[list[dict], dict]:
    errors, clean = [], {}
    if not isinstance(data, dict):
        return [{"field": "", "message": "The body must be a JSON object."}], {}
    for field in ("title", "author"):
        if field in data or not partial:
            value = data.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append({"field": field, "message": f"{field} is required (a non-empty string)."})
            else:
                clean[field] = value.strip()[:300]
    if "year" in data:
        year = data["year"]
        if year is not None and (not isinstance(year, int) or isinstance(year, bool) or not 0 <= year <= 2100):
            errors.append({"field": "year", "message": "year must be a whole number between 0 and 2100, or null."})
        else:
            clean["year"] = year
    elif not partial:
        clean["year"] = None
    if "isbn" in data:
        isbn = data["isbn"]
        if isbn is not None and not isinstance(isbn, str):
            errors.append({"field": "isbn", "message": "isbn must be a string or null."})
        else:
            clean["isbn"] = (isbn or "").strip()[:40] or None
    elif not partial:
        clean["isbn"] = None
    unknown = sorted(set(data) - {"title", "author", "year", "isbn", "id"})
    if unknown:
        errors.append({"field": unknown[0], "message": f"Unknown field(s): {', '.join(unknown)}. "
                                                         "Allowed: title, author, year, isbn."})
    if clean.get("isbn"):
        for other in books.values():
            if other["isbn"] == clean["isbn"] and (existing is None or other["id"] != existing["id"]):
                errors.append({"field": "isbn", "message": f"A book with isbn {clean['isbn']} already exists "
                                                           f"(id {other['id']}).", "conflict": True})
    return errors, clean


async def _json_body(request: Request) -> tuple[object, JSONResponse | None]:
    ctype = request.headers.get("content-type", "")
    if "application/json" not in ctype.lower():
        return None, _error(415, f"Unsupported Media Type: this API only accepts JSON, but Content-Type was "
                                 f"'{ctype or '(missing)'}'.", "Add the header Content-Type: application/json.")
    raw = await request.body()
    if len(raw) > MAX_BODY:
        return None, _error(413, "The body is too large for the practice API.")
    try:
        return json.loads(raw or b"null"), None
    except (ValueError, UnicodeDecodeError) as exc:
        return None, _error(400, f"The body isn't valid JSON: {exc}.",
                            "Check quotes (JSON needs double quotes), commas and brackets.")


def make_router(lab: PracticeApi) -> APIRouter:
    router = APIRouter()

    def with_headers(resp: Response, headers: dict) -> Response:
        for k, v in headers.items():
            resp.headers[k] = v
        return resp

    async def guard(request: Request, need_role: str | None = None, bearer_only: bool = False):
        who = lab.identify(request)
        if "error" in who:
            return None, {}, who["error"]
        headers, limited = lab.rate_limit(request, who)
        if limited:
            return None, headers, limited
        if bearer_only and who["method"] != "bearer":
            return None, headers, with_headers(_error(
                401, f"This action needs a Bearer token, not {who['method']} authentication.",
                "POST /practice/api/v1/auth/login with Basic auth, then send Authorization: Bearer <token>."), headers)
        if need_role == "editor" and who["role"] != "editor":
            return None, headers, with_headers(_error(
                403, f"Forbidden: '{who['user']}' can only read (role: {who['role']}).",
                "You are authenticated, but not authorized. Log in as learner / devnet123 to make changes."), headers)
        return who, headers, None

    # ---------------------------------------------------------------- index
    @router.get(PREFIX)
    @router.get(PREFIX + "/")
    async def index():
        return {
            "name": "Jarvis practice API (books)",
            "auth": {"basic_users": {"learner": "devnet123 (can read and write)", "viewer": "viewer123 (read only)"},
                     "api_key_header": "X-API-Key: practice-key-123 (read only)",
                     "bearer": f"POST {PREFIX}/auth/login with Basic auth"},
            "rate_limit": f"token bucket: {BUCKET_CAPACITY} requests, refilled {REFILL_PER_SECOND:g}/second, per user",
            "links": {"books": f"{PREFIX}/books", "login": f"{PREFIX}/auth/login", "reports": f"{PREFIX}/reports",
                      "flaky": f"{PREFIX}/flaky", "webhooks": f"{PREFIX}/webhooks", "soap": "/practice/soap",
                      "json_rpc": "/practice/rpc"},
        }

    @router.post(PREFIX + "/auth/login")
    async def login(request: Request):
        if not request.headers.get("authorization", "").lower().startswith("basic "):
            return _error(401, "Log in with Basic authentication.", "Authorization: Basic base64('learner:devnet123')",
                          {"WWW-Authenticate": 'Basic realm="practice"'})
        who, headers, err = await guard(request)
        if err:
            return err
        token = secrets.token_urlsafe(24)
        lab.tokens[token] = (who["user"], who["role"], time.time() + TOKEN_LIFETIME)
        return with_headers(JSONResponse({"token": token, "token_type": "Bearer", "expires_in": TOKEN_LIFETIME,
                                          "user": who["user"], "role": who["role"]}), headers)

    # ---------------------------------------------------------------- books
    @router.get(PREFIX + "/books")
    async def list_books(request: Request):
        who, headers, err = await guard(request)
        if err:
            return err
        q = request.query_params
        try:
            page = int(q.get("page", "1"))
            per_page = int(q.get("per_page", "10"))
        except ValueError:
            return with_headers(_error(400, "page and per_page must be whole numbers.", "e.g. ?page=2&per_page=5"), headers)
        if page < 1 or not 1 <= per_page <= 50:
            return with_headers(_error(400, "page must be 1 or more and per_page between 1 and 50."), headers)
        items = sorted(lab.books.values(), key=lambda b: b["id"])
        if q.get("author"):
            items = [b for b in items if q["author"].lower() in b["author"].lower()]
        if q.get("q"):
            items = [b for b in items if q["q"].lower() in b["title"].lower()]
        total = len(items)
        pages = math.ceil(total / per_page)
        chunk = items[(page - 1) * per_page: page * per_page]
        extra = {k: v for k, v in q.items() if k not in ("page", "per_page")}

        def link(p: int) -> str:
            return f"<{PREFIX}/books?{urlencode({**extra, 'page': p, 'per_page': per_page})}>"
        links = []
        if page < pages:
            links.append(f'{link(page + 1)}; rel="next"')
        if page > 1:
            links.append(f'{link(page - 1)}; rel="prev"')
        if pages:
            links += [f'{link(1)}; rel="first"', f'{link(pages)}; rel="last"']
        headers = {**headers, "X-Total-Count": str(total)}
        if links:
            headers["Link"] = ", ".join(links)
        return with_headers(JSONResponse({"items": chunk, "page": page, "per_page": per_page, "total": total,
                                          "pages": pages}), headers)

    @router.get(PREFIX + "/books/{book_id}")
    async def get_book(book_id: str, request: Request):
        who, headers, err = await guard(request)
        if err:
            return err
        book = lab.books.get(int(book_id)) if book_id.isdigit() else None
        if not book:
            return with_headers(_error(404, f"No book with id {book_id}.", f"List books with GET {PREFIX}/books."), headers)
        return with_headers(JSONResponse(book), headers)

    @router.post(PREFIX + "/books")
    async def create_book(request: Request):
        who, headers, err = await guard(request, need_role="editor", bearer_only=True)
        if err:
            return err
        data, err = await _json_body(request)
        if err:
            return with_headers(err, headers)
        errors, clean = _book_errors(data, partial=False, existing=None, books=lab.books)
        if errors:
            status = 409 if any(e.get("conflict") for e in errors) else 400
            msg = "Conflict: that book already exists." if status == 409 else "The book isn't valid."
            return with_headers(JSONResponse({"error": {"code": status, "message": msg, "details": errors}},
                                             status_code=status), headers)
        if len(lab.books) >= MAX_BOOKS:
            return with_headers(_error(507, "The practice API is full.", "POST /practice/lab/reset to start over."), headers)
        book = lab._insert(clean)
        lab.fire("book.created", book)
        return with_headers(JSONResponse(book, status_code=201), {**headers, "Location": f"{PREFIX}/books/{book['id']}"})

    async def _update(book_id: str, request: Request, partial: bool):
        who, headers, err = await guard(request, need_role="editor", bearer_only=True)
        if err:
            return err
        book = lab.books.get(int(book_id)) if book_id.isdigit() else None
        if not book:
            return with_headers(_error(404, f"No book with id {book_id}."), headers)
        data, err = await _json_body(request)
        if err:
            return with_headers(err, headers)
        errors, clean = _book_errors(data, partial=partial, existing=book, books=lab.books)
        if errors:
            status = 409 if any(e.get("conflict") for e in errors) else 400
            return with_headers(JSONResponse({"error": {"code": status, "message": "The update isn't valid.",
                                                        "details": errors}}, status_code=status), headers)
        book.update(clean)
        lab.fire("book.updated", book)
        return with_headers(JSONResponse(book), headers)

    @router.put(PREFIX + "/books/{book_id}")
    async def replace_book(book_id: str, request: Request):
        return await _update(book_id, request, partial=False)

    @router.patch(PREFIX + "/books/{book_id}")
    async def patch_book(book_id: str, request: Request):
        return await _update(book_id, request, partial=True)

    @router.delete(PREFIX + "/books/{book_id}")
    async def delete_book(book_id: str, request: Request):
        who, headers, err = await guard(request, need_role="editor", bearer_only=True)
        if err:
            return err
        book = lab.books.pop(int(book_id), None) if book_id.isdigit() else None
        if not book:
            return with_headers(_error(404, f"No book with id {book_id}."), headers)
        lab.fire("book.deleted", {"id": book["id"], "title": book["title"]})
        return with_headers(Response(status_code=204), headers)

    # ---------------------------------------------------------------- async job
    @router.post(PREFIX + "/reports")
    async def start_report(request: Request):
        who, headers, err = await guard(request, bearer_only=True)
        if err:
            return err
        job_id = secrets.token_hex(4)
        lab.jobs[job_id] = {"id": job_id, "started": time.time(), "user": who["user"]}
        location = f"{PREFIX}/reports/{job_id}"
        return with_headers(JSONResponse({"id": job_id, "status": "pending", "check": location}, status_code=202),
                            {**headers, "Location": location, "Retry-After": "1"})

    @router.get(PREFIX + "/reports/{job_id}")
    async def report_status(job_id: str, request: Request):
        who, headers, err = await guard(request)
        if err:
            return err
        job = lab.jobs.get(job_id)
        if not job:
            return with_headers(_error(404, f"No report job {job_id}."), headers)
        elapsed = time.time() - job["started"]
        if elapsed < REPORT_SECONDS:
            return with_headers(JSONResponse({"id": job_id, "status": "pending",
                                              "progress": round(elapsed / REPORT_SECONDS * 100)}), {**headers, "Retry-After": "1"})
        authors: dict[str, int] = {}
        for b in lab.books.values():
            authors[b["author"]] = authors.get(b["author"], 0) + 1
        top = sorted(authors.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        return with_headers(JSONResponse({"id": job_id, "status": "done", "result": {
            "books": len(lab.books), "authors": len(authors), "top_authors": [{"author": a, "books": n} for a, n in top],
            "newest": max((b["year"] or 0 for b in lab.books.values()), default=None)}}), headers)

    # ---------------------------------------------------------------- retries
    @router.get(PREFIX + "/flaky")
    async def flaky(request: Request):
        who, headers, err = await guard(request)
        if err:
            return err
        key = who["user"]
        lab.flaky[key] = lab.flaky.get(key, 0) + 1
        if lab.flaky[key] % 3:
            return with_headers(_error(503, "Service Unavailable (on purpose: this endpoint fails 2 times out of 3).",
                                       "Retry after the number of seconds in Retry-After.", {"Retry-After": "1"}), headers)
        return with_headers(JSONResponse({"ok": True, "message": "Third time lucky: your retry logic works.",
                                          "attempt": lab.flaky[key]}), headers)

    # ---------------------------------------------------------------- webhooks
    @router.get(PREFIX + "/webhooks")
    async def list_webhooks(request: Request):
        who, headers, err = await guard(request)
        if err:
            return err
        return with_headers(JSONResponse({"items": [{k: v for k, v in h.items() if k != "secret"}
                                                    for h in lab.webhooks.values()]}), headers)

    @router.post(PREFIX + "/webhooks")
    async def add_webhook(request: Request):
        who, headers, err = await guard(request, need_role="editor", bearer_only=True)
        if err:
            return err
        data, err = await _json_body(request)
        if err:
            return with_headers(err, headers)
        if not isinstance(data, dict) or not isinstance(data.get("url"), str):
            return with_headers(_error(400, "Send {\"url\": \"http://127.0.0.1:.../practice/hooks/my-app\", "
                                            "\"events\": [\"book.created\"]}."), headers)
        if not is_loopback_url(data["url"]):
            return with_headers(_error(400, "For your safety the practice API only delivers webhooks to this device "
                                            "(127.0.0.1 or localhost).",
                                       "Use the built-in inbox, e.g. http://127.0.0.1:8765/practice/hooks/my-app, "
                                       "or your own app running on this computer."), headers)
        events = data.get("events") or EVENTS
        if not isinstance(events, list) or not all(e in EVENTS for e in events):
            return with_headers(_error(400, f"events must be a list chosen from {EVENTS}."), headers)
        if len(lab.webhooks) >= 20:
            return with_headers(_error(400, "Too many webhooks; delete some first."), headers)
        hook = {"id": secrets.token_hex(4), "url": data["url"], "events": events, "secret": secrets.token_hex(16)}
        lab.webhooks[hook["id"]] = hook
        return with_headers(JSONResponse(hook, status_code=201),
                            {**headers, "Location": f"{PREFIX}/webhooks/{hook['id']}"})

    @router.delete(PREFIX + "/webhooks/{hook_id}")
    async def delete_webhook(hook_id: str, request: Request):
        who, headers, err = await guard(request, need_role="editor", bearer_only=True)
        if err:
            return err
        if not lab.webhooks.pop(hook_id, None):
            return with_headers(_error(404, f"No webhook {hook_id}."), headers)
        return with_headers(Response(status_code=204), headers)

    # ---------------------------------------------------------------- webhook inbox (a receiver to practise with)
    @router.post("/practice/hooks/{name}")
    async def receive_hook(name: str, request: Request):
        body = await request.body()
        sig = request.headers.get("x-jarvis-signature", "")
        entry = {"name": name[:60], "at": time.strftime("%H:%M:%S"), "event": request.headers.get("x-jarvis-event", ""),
                 "content_type": request.headers.get("content-type", ""), "signature": sig,
                 "signature_valid": lab.signature_valid(body, sig), "body": body[:10_000].decode("utf-8", "replace")}
        lab.inbox.insert(0, entry)
        del lab.inbox[50:]
        return {"received": True}

    @router.get("/practice/hooks")
    async def inbox():
        return {"inbox": lab.inbox, "deliveries": lab.deliveries,
                "webhooks": [{k: v for k, v in h.items()} for h in lab.webhooks.values()]}

    @router.delete("/practice/hooks")
    async def clear_inbox():
        lab.inbox.clear()
        lab.deliveries.clear()
        return {"cleared": True}

    @router.post("/practice/lab/reset")
    async def reset():
        lab.reset()
        return {"reset": True, "books": len(lab.books)}

    # ---------------------------------------------------------------- other API styles
    @router.post("/practice/rpc")
    async def json_rpc(request: Request):
        raw = await request.body()

        def rpc_error(code: int, message: str, rid=None):
            return JSONResponse({"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": rid})
        try:
            call = json.loads(raw[:MAX_BODY] or b"null")
        except ValueError:
            return rpc_error(-32700, "Parse error: the body isn't valid JSON.")
        if not isinstance(call, dict) or call.get("jsonrpc") != "2.0" or not isinstance(call.get("method"), str):
            return rpc_error(-32600, "Invalid Request: send {\"jsonrpc\": \"2.0\", \"method\": ..., \"id\": 1}.",
                             call.get("id") if isinstance(call, dict) else None)
        rid, params = call.get("id"), call.get("params") or {}
        if call["method"] == "books.count":
            return JSONResponse({"jsonrpc": "2.0", "result": len(lab.books), "id": rid})
        if call["method"] == "books.get":
            book_id = params.get("id") if isinstance(params, dict) else None
            if not isinstance(book_id, int):
                return rpc_error(-32602, "Invalid params: books.get needs {\"id\": <number>}.", rid)
            book = lab.books.get(book_id)
            if not book:
                return rpc_error(1404, f"No book with id {book_id}.", rid)
            return JSONResponse({"jsonrpc": "2.0", "result": book, "id": rid})
        return rpc_error(-32601, f"Method not found: {call['method']}. Try books.count or books.get.", rid)

    @router.post("/practice/soap")
    async def soap(request: Request):
        raw = (await request.body())[:MAX_BODY]
        ns = "http://schemas.xmlsoap.org/soap/envelope/"

        def envelope(inner: str, status: int = 200) -> Response:
            xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<soap:Envelope xmlns:soap="{ns}">\n'
                   f"  <soap:Body>\n{inner}\n  </soap:Body>\n</soap:Envelope>\n")
            return Response(xml, status_code=status, media_type="text/xml; charset=utf-8")

        def fault(code: str, text: str) -> Response:
            return envelope(f"    <soap:Fault>\n      <faultcode>soap:{code}</faultcode>\n"
                            f"      <faultstring>{_xml_escape(text)}</faultstring>\n    </soap:Fault>", 500)
        if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            return fault("Client", "DOCTYPE and ENTITY declarations aren't allowed.")
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            return fault("Client", f"The XML isn't well-formed: {exc}")
        if root.tag != f"{{{ns}}}Envelope":
            return fault("Client", "The root element must be soap:Envelope.")
        body = root.find(f"{{{ns}}}Body")
        if body is None or not len(body):
            return fault("Client", "The Envelope needs a soap:Body with one operation.")
        op = body[0]
        name = op.tag.split("}")[-1]
        if name == "CountBooks":
            return envelope(f"    <CountBooksResponse><count>{len(lab.books)}</count></CountBooksResponse>")
        if name == "GetBook":
            id_text = (op.findtext("id") or op.findtext("{*}id") or "").strip()
            book = lab.books.get(int(id_text)) if id_text.isdigit() else None
            if not book:
                return fault("Client", f"No book with id '{id_text}'.")
            fields = "".join(f"<{k}>{_xml_escape(str(v if v is not None else ''))}</{k}>" for k, v in book.items())
            return envelope(f"    <GetBookResponse><book>{fields}</book></GetBookResponse>")
        return fault("Client", f"Unknown operation '{name}'. Try GetBook or CountBooks.")

    return router


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
