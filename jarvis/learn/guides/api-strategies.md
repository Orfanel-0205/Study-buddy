---
title: API strategies in practice (Python, PHP, JavaScript, TypeScript)
summary: How professionals call and build APIs - a reusable client with timeouts, retries with backoff, pagination loops, rate-limit handling, keeping keys secret, verifying webhooks, async 202 jobs - and how to design your own REST API, with code in all four languages.
tags: api, rest, client, retry, backoff, timeout, pagination, rate limit, webhook, hmac, idempotency, api design, fastapi, express, laravel, php, python, javascript, typescript, fetch, requests, curl
order: 7
---

# API strategies in practice (Python, PHP, JavaScript, TypeScript)

The DevNet module explains **what** APIs are. This guide is about **how to use and build them well** at work.

## Calling APIs: the rules that prevent most incidents

1. **Always set a timeout.** Without one, a stuck server freezes your script/page forever.
2. **Check the status code before using the body.** A 404 or 500 often still has a (JSON or HTML) body.
3. **Wrap every API in one small client** (base URL, auth header, timeout, error handling in one place)
   instead of copying `requests.get(...)` everywhere.
4. **Retry only what is safe to retry**, and only for temporary errors (see below).
5. **Keep secrets out of code:** API keys and tokens come from environment variables (`.env`, never committed).
6. **Never put a private API key in frontend JavaScript.** Anyone can read it in the browser. Call your own
   backend, and let the backend call the API with the key.
7. **Log** the method, URL (without secrets), status and time of each call; it's how you debug production.

## A reusable API client

### Python (requests)
```python
import os
import requests

class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(f"{status}: {message}")
        self.status = status

class BooksClient:
    def __init__(self, base_url, token=None, timeout=10):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()               # reuses connections (faster)
        self.session.headers["Accept"] = "application/json"
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.timeout = timeout

    def request(self, method, path, **kwargs):
        r = self.session.request(method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
        if not r.ok:                                    # 4xx / 5xx
            try:
                message = r.json().get("error", {}).get("message", r.text)
            except ValueError:
                message = r.text[:200]
            raise ApiError(r.status_code, message)
        return r.json() if r.content else None

    def list_books(self, page=1):
        return self.request("GET", "/books", params={"page": page})

    def create_book(self, title, author, year):
        return self.request("POST", "/books", json={"title": title, "author": author, "year": year})

client = BooksClient("http://127.0.0.1:8765/practice/api/v1", token=os.environ.get("BOOKS_TOKEN"))
```

### JavaScript (fetch: browsers and Node 18+)
```js
export async function api(path, { method = "GET", body, token, timeoutMs = 10000 } = {}) {
  const res = await fetch(`http://127.0.0.1:8765/practice/api/v1${path}`, {
    method,
    headers: {
      Accept: "application/json",
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(timeoutMs),          // fetch has NO timeout by default
  });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new Error(`${res.status}: ${data?.error?.message ?? res.statusText}`);
  return data;
}
```
`fetch` only rejects on **network** errors. A 404 or 500 is a *successful* fetch, so check `res.ok` yourself.

### TypeScript (types for the response)
```ts
export interface Book { id: number; title: string; author: string; year: number | null; isbn?: string }
export interface Page<T> { items: T[]; page: number; per_page: number; total: number; pages: number }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(`${status}: ${message}`); }
}

export async function api<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const res = await fetch(`http://127.0.0.1:8765/practice/api/v1${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({})))?.error?.message ?? res.statusText);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const firstPage = await api<Page<Book>>("/books?page=1", {}, process.env.BOOKS_TOKEN);
```
Types are a **promise you make to the compiler**. They don't validate data at runtime; check important fields
(or use a validator such as `zod`) when the data comes from outside.

### PHP (cURL, built in)
```php
<?php
function api(string $method, string $path, ?array $body = null, ?string $token = null): ?array {
    $ch = curl_init('http://127.0.0.1:8765/practice/api/v1' . $path);
    $headers = ['Accept: application/json'];
    if ($token) $headers[] = 'Authorization: Bearer ' . $token;
    if ($body !== null) {
        $headers[] = 'Content-Type: application/json';
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($body));
    }
    curl_setopt_array($ch, [
        CURLOPT_CUSTOMREQUEST => $method,
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 10,
    ]);
    $raw = curl_exec($ch);
    if ($raw === false) throw new RuntimeException('Network error: ' . curl_error($ch));
    $status = curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
    curl_close($ch);
    $data = $raw === '' ? null : json_decode($raw, true);
    if ($status >= 400) throw new RuntimeException("$status: " . ($data['error']['message'] ?? $raw));
    return $data;
}
$books = api('GET', '/books?page=1', null, getenv('BOOKS_TOKEN'));
```
In Laravel use the HTTP client: `Http::withToken($t)->timeout(10)->retry(3, 200)->get($url)->throw()->json();`

## Retries with exponential backoff

**Retry when** the problem is probably temporary: network errors, timeouts, **429**, **502, 503, 504**.
**Don't retry** 400, 401, 403, 404, 409, 415, 422: the same request will fail again; fix it instead.

**Only retry safe operations.** GET, PUT and DELETE are **idempotent** (doing them twice has the same effect
as once). **POST is not**: a retried "create order" may create two orders. For POST, use an
**idempotency key** header (`Idempotency-Key: <uuid>`) if the API supports it, so the server can ignore duplicates.

**Backoff:** wait longer after each failure (e.g. 0.5 s, 1 s, 2 s, 4 s) plus a little random **jitter** so
thousands of clients don't retry at the same moment. **If the server sends `Retry-After`, wait that long.**

```python
import random, time, requests

RETRY_STATUS = {429, 502, 503, 504}

def get_with_retries(url, retries=4, base=0.5, **kwargs):
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, timeout=10, **kwargs)
            if r.status_code not in RETRY_STATUS or attempt == retries:
                return r
            wait = float(r.headers.get("Retry-After", base * 2 ** attempt))
        except (requests.ConnectionError, requests.Timeout):
            if attempt == retries:
                raise
            wait = base * 2 ** attempt
        time.sleep(wait + random.uniform(0, 0.1))
```

```js
async function withRetries(fn, { retries = 4, baseMs = 500 } = {}) {
  for (let attempt = 0; ; attempt++) {
    const res = await fn().catch((err) => ({ networkError: err }));
    const temporary = res.networkError || [429, 502, 503, 504].includes(res.status);
    if (!temporary || attempt === retries) {
      if (res.networkError) throw res.networkError;
      return res;
    }
    const retryAfter = res.headers?.get?.("Retry-After");
    const waitMs = retryAfter ? Number(retryAfter) * 1000 : baseMs * 2 ** attempt;
    await new Promise((r) => setTimeout(r, waitMs + Math.random() * 100));
  }
}
const res = await withRetries(() => fetch(url, { signal: AbortSignal.timeout(10000) }));
```
Libraries do this for you: Python `urllib3.Retry` with `HTTPAdapter`, `tenacity`; PHP Guzzle retry middleware,
Laravel `->retry()`; JS `p-retry`, `axios-retry`.

## Pagination: getting everything

```python
def all_books(client):
    page, books = 1, []
    while True:
        data = client.list_books(page=page)
        books.extend(data["items"])
        if page >= data["pages"]:          # or: no "next" link / empty items / no next cursor
            return books
        page += 1
```
- **Page/offset** (`?page=3&per_page=50`): simple; items can shift if data changes while you page.
- **Cursor** (`?cursor=abc`): the response gives the next cursor; stable and fast for big data.
- **Link header** (GitHub style): `Link: <...page=3>; rel="next", <...page=10>; rel="last"`. Follow `rel="next"` until it's gone.
- Use the **largest page size allowed** to make fewer requests (and stay under rate limits).

## Rate limits: be a good client

- Read `X-RateLimit-Remaining`; when it gets low, **slow down** before you hit 429.
- On **429**, wait `Retry-After` seconds (or until `X-RateLimit-Reset`), then continue.
- For bulk jobs (e.g. "add 100 books"), add a small delay between calls or process in batches, and make the
  job **resumable** (remember what's done) in case it stops halfway.
- **Cache** responses you read often so you don't spend your limit on the same data.

## Async jobs: 202 Accepted + polling

```python
r = requests.post(f"{BASE}/reports", headers=headers, timeout=10)      # → 202 Accepted
status_url = r.headers["Location"]
while True:
    job = requests.get(f"http://127.0.0.1:8765{status_url}", headers=headers, timeout=10).json()
    if job["status"] == "done":
        print(job["result"]); break
    time.sleep(1)                                                     # poll politely; or use a webhook
```

## Webhooks: receiving them safely

1. **Verify the signature.** Providers sign the body with a shared secret (HMAC-SHA256) so you know the request
   really came from them. Compare with a **constant-time** comparison.
2. **Respond 2xx fast** (within a few seconds), then do slow work in the background; otherwise the provider
   times out and retries.
3. **Expect duplicates and out-of-order events.** Store processed event IDs and skip repeats (idempotency).
4. Webhook URLs must be **reachable by the provider** (public HTTPS). For local testing use a tunnel (ngrok,
   Cloudflare Tunnel) or the provider's test tools. Jarvis's API Lab delivers to your own laptop, so you can practise offline.

```python
# FastAPI receiver
import hashlib, hmac, os
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI()
SECRET = os.environ["WEBHOOK_SECRET"].encode()

@app.post("/hooks/books")
async def books_hook(request: Request, x_jarvis_signature: str = Header(...)):
    body = await request.body()
    expected = "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_jarvis_signature):
        raise HTTPException(401, "bad signature")
    event = await request.json()
    # save event["id"] to skip duplicates, queue the real work, then:
    return {"received": True}
```

```php
<?php // plain PHP receiver
$body = file_get_contents('php://input');
$expected = 'sha256=' . hash_hmac('sha256', $body, getenv('WEBHOOK_SECRET'));
if (!hash_equals($expected, $_SERVER['HTTP_X_JARVIS_SIGNATURE'] ?? '')) {
    http_response_code(401); exit;
}
$event = json_decode($body, true);
http_response_code(200);
echo json_encode(['received' => true]);
```

```js
// Express receiver: the signature is computed over the RAW body, so don't parse JSON first
import crypto from "node:crypto";
app.post("/hooks/books", express.raw({ type: "application/json" }), (req, res) => {
  const expected = "sha256=" + crypto.createHmac("sha256", process.env.WEBHOOK_SECRET).update(req.body).digest("hex");
  const given = req.get("X-Jarvis-Signature") ?? "";
  const ok = given.length === expected.length && crypto.timingSafeEqual(Buffer.from(given), Buffer.from(expected));
  if (!ok) return res.sendStatus(401);
  const event = JSON.parse(req.body);
  res.json({ received: true });
});
```

## Designing your own REST API

| Topic | Good practice |
|---|---|
| URLs | **nouns, plural**: `/books`, `/books/42`, `/users/7/orders`. The method is the verb (not `/getBooks`) |
| Versioning | `/api/v1/...` so you can change things later without breaking clients |
| Status codes | 200 read/update, **201 + `Location`** create, 204 delete, 400/422 validation, 401/403 auth, 404, 409 conflict, 429 limit |
| Errors | one consistent JSON shape: `{"error": {"code": 400, "message": "title is required", "field": "title"}}` |
| Validation | validate **every** input on the server (types, required, lengths, ranges); never trust the client |
| Lists | paginate (`page`, `per_page` with a maximum), allow filtering (`?author=`) and sorting (`?sort=-year`) |
| Auth | HTTPS only; tokens in the `Authorization` header; least privilege (roles/scopes) |
| Security | parameterized SQL (no string concatenation), rate limiting, CORS only for your frontend's origin, no stack traces in responses |
| Docs | OpenAPI/Swagger (FastAPI generates it at `/docs`), with examples |

### Minimal endpoints in each language

```python
# Python: FastAPI (pip install fastapi uvicorn), run: uvicorn main:app --reload
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI()
books = {}

class BookIn(BaseModel):
    title: str = Field(min_length=1)
    author: str = Field(min_length=1)
    year: int | None = None

@app.post("/api/v1/books", status_code=201)
def create_book(book: BookIn):                  # invalid JSON/fields → automatic 422 response
    book_id = len(books) + 1
    books[book_id] = {"id": book_id, **book.model_dump()}
    return books[book_id]

@app.get("/api/v1/books/{book_id}")
def get_book(book_id: int):
    if book_id not in books:
        raise HTTPException(404, "Book not found")
    return books[book_id]
```

```php
<?php // PHP: Laravel routes/api.php (served under /api)
use Illuminate\Http\Request;
use App\Models\Book;

Route::post('/v1/books', function (Request $request) {
    $data = $request->validate([                // invalid → 422 with error details automatically
        'title' => 'required|string|max:200',
        'author' => 'required|string|max:200',
        'year' => 'nullable|integer|min:0|max:2100',
    ]);
    return response()->json(Book::create($data), 201);
});
Route::get('/v1/books/{book}', fn (Book $book) => $book);   // unknown id → 404 automatically
```

```js
// JavaScript: Express (npm install express), run: node server.js
import express from "express";
const app = express();
app.use(express.json());
const books = new Map();

app.post("/api/v1/books", (req, res) => {
  const { title, author, year = null } = req.body ?? {};
  if (!title || !author) return res.status(400).json({ error: { code: 400, message: "title and author are required" } });
  const book = { id: books.size + 1, title, author, year };
  books.set(book.id, book);
  res.status(201).location(`/api/v1/books/${book.id}`).json(book);
});

app.get("/api/v1/books/:id", (req, res) => {
  const book = books.get(Number(req.params.id));
  if (!book) return res.status(404).json({ error: { code: 404, message: "Book not found" } });
  res.json(book);
});

app.listen(3000);
```
In TypeScript, the same Express code with types (`Request<{ id: string }>`, an interface `Book`) and
`npm i -D typescript @types/express`.

## Testing APIs

- **Manually:** curl, Postman/Insomnia/Bruno, VS Code REST Client, or Jarvis's API Lab.
- **Automated:** call your endpoints in tests (FastAPI `TestClient`, Laravel `$this->postJson(...)->assertStatus(201)`,
  `supertest` for Express).
- **Mock external APIs** in unit tests (Python `responses`/`respx`, PHP `Http::fake()`, JS `msw`) so tests are
  fast and don't need the internet or real keys.

## Practice path in Jarvis

1. **API Lab:** walk through the scenarios (401 → 200 → 403 → 415 → 400 → 409 → 429 → 202 → webhook).
2. Use **Show code** to see the same request in Python, curl, JavaScript, TypeScript and PHP, then run it yourself.
3. **Practice:** do the API exercises (status classes, Basic auth header, pagination, token bucket, retries, Link headers).
4. Build a tiny Books API in your strongest language, then a client for it in another.
