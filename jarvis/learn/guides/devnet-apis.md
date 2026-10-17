---
title: DevNet Module 4: Understanding and using APIs
summary: Exam-focused notes for DevNet Associate Module 4 - sync vs async APIs, RPC/SOAP/REST, REST constraints, requests and responses, status codes, authentication vs authorization, OAuth, rate limits, webhooks and troubleshooting - with Python examples and Jarvis API Lab exercises.
tags: devnet, cisco, api, rest, soap, rpc, http, status codes, authentication, oauth, rate limit, webhook, troubleshooting, python requests, postman
order: 5
---

# DevNet Module 4: Understanding and using APIs

Module goal: **create REST API requests over HTTPS to securely integrate services.**
Every section ends with something to try in **Jarvis → Learn → API Lab** (a practice API that runs on your
laptop, so it works offline).

## 4.1 What an API is, and why use one

An **API (Application Programming Interface)** lets one program talk to another. It defines **what data and
functions an application exposes** and how to ask for them, so the application can share exactly what it wants, securely.

Three main uses:
- **Automation:** a script does a manual task for you (e.g. configure 200 switches, add 100 books).
- **Data integration:** one app consumes or reacts to another app's data.
- **Functionality:** add another product's feature to yours (maps, payments, messaging).

Why APIs are everywhere now: they're designed into products and tested, and simple languages like Python let
non-programmers (network engineers!) use them.

## 4.2 API design styles: synchronous vs asynchronous

| | Synchronous | Asynchronous |
|---|---|---|
| Server responds | immediately **with the data** | immediately with an **acknowledgement only** (no data yet) |
| Use when | data is readily available | the work takes time, or data isn't ready |
| Client | **waits (is blocked)** until the response arrives | **continues working**; gets the result later (polling a status URL, a callback/webhook) |
| Analogy | buying tickets at a counter, first come first served | ordering at a restaurant with a buzzer |

The same product can mix both: each API is designed independently. In HTTP, an async API typically answers
**202 Accepted** with a link to check the status later.

API Lab: `POST /practice/api/v1/reports` returns 202; poll the `Location` URL until `status` is `done`.

## 4.3 API architectural styles: RPC, SOAP, REST

### RPC (Remote Procedure Call)
- Request-response: the client **calls a procedure (function) on a remote server** as if it were local;
  the server runs it and returns the result.
- It's a style that can run over different transports: **XML-RPC, JSON-RPC, NFS**; SOAP also follows the RPC model.

```json
{"jsonrpc": "2.0", "method": "books.count", "params": {}, "id": 1}
```

### SOAP (Simple Object Access Protocol)
- An **XML-based messaging protocol** for apps on different platforms/languages.
- **Independent** (any OS/language), **extensible** (add security, reliability), **neutral** (runs over HTTP, SMTP, TCP, UDP, JMS).
- A SOAP message is an XML document with:
  - **Envelope:** the root element (required)
  - **Header:** application-specific info such as authorization (optional)
  - **Body:** the actual data for the recipient (required)
  - **Fault:** errors and status information (optional, inside Body)

```xml
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Header/>
  <soap:Body>
    <GetBook><id>3</id></GetBook>
  </soap:Body>
</soap:Envelope>
```

### REST (REpresentational State Transfer)
An architectural style defined by **Roy Fielding**, with **six constraints**:

1. **Client-server:** client and server are independent; each can change and scale separately.
2. **Stateless:** each request carries **everything** the server needs (e.g. the auth token). The server keeps
   **no session state** between requests. (This is what makes load balancing easy.)
3. **Cacheable:** responses must say whether they can be cached (`Cache-Control`); cacheable data can be reused.
4. **Uniform interface:**
   - identification of resources (each has a URI),
   - manipulation of resources through representations (e.g. JSON you send back),
   - self-descriptive messages (method, headers and `Content-Type` say how to process them),
   - **HATEOAS**: hypermedia as the engine of application state (responses contain links to related actions).
5. **Layered system:** each layer (proxy, load balancer, cache, server) only knows the layer next to it.
6. **Code-on-demand (optional):** the server may send executable code (e.g. JavaScript). Optional because running
   third-party code is a security risk.

## 4.4 REST API requests and responses

A REST API is a programming interface over **HTTP**, so it uses HTTP **requests/responses, verbs (methods),
status codes, and headers/body**.

### The request: URI + method + headers + body

```text
https://api.example.com:443/v1/books?author=Fielding&page=2
└─┬─┘   └──────┬──────┘└┬┘└───┬───┘ └────────────┬────────┘
scheme      host      port  path              query
        └────── authority ──────┘
```
- **Scheme:** `http` or `https` (always https for real APIs).
- **Authority:** host (+ optional port).
- **Path:** which resource.
- **Query:** extra details: filtering, scope, pagination.

| Method | Action (CRUD) | Typical success code | Body? |
|---|---|---|---|
| **POST** | **Create** a new resource | 201 Created | yes |
| **GET** | **Read** resource(s) | 200 OK | no |
| **PUT** | **Update by replacing** the whole resource | 200 / 204 | yes |
| **PATCH** | **Partial update** of some fields | 200 / 204 | yes |
| **DELETE** | **Delete** | 204 No Content / 200 | no |

**Headers** are `Name: value` pairs:
- **Request headers:** extra info not about the body, e.g. `Authorization: Basic dmFncmFudDp2YWdyYW50`, `Accept: application/json`.
- **Entity headers:** describe the body, e.g. `Content-Type: application/json`.

**Body:** the data for POST, PUT, PATCH (optional for others). If you send one, say its type in `Content-Type`.

### The response: status + headers + body

**Status code categories:**
| Range | Meaning |
|---|---|
| 1xx | Informational (no body) |
| 2xx | Success: received, understood, accepted |
| 3xx | Redirection: the client must take another action |
| 4xx | **Client error**: the request has a problem (fix the request) |
| 5xx | **Server error**: a valid request the server couldn't fulfil |

**Codes to know for the exam:**
| Code | Name | Meaning / typical cause |
|---|---|---|
| 200 | OK | success, usually with a body |
| 201 | Created | resource created (often with a `Location` header) |
| 202 | Accepted | accepted for processing, not finished (**async**) |
| 204 | No Content | success, nothing to return (e.g. DELETE) |
| 304 | Not Modified | your cached copy is still valid |
| 400 | Bad Request | malformed syntax: misspelled field, invalid JSON, missing required field |
| 401 | Unauthorized | **not authenticated**: missing/wrong credentials or token |
| 403 | Forbidden | **authenticated but not allowed** (not enough privileges); some APIs also use it for rate limits |
| 404 | Not Found | the resource/path doesn't exist (check the URI) |
| 405 | Method Not Allowed | e.g. DELETE on a read-only resource |
| 407 | Proxy Authentication Required | authenticate with the **proxy** first |
| 409 | Conflict | conflicts with the current state (duplicate, edit conflict); retry after it's resolved |
| 415 | Unsupported Media Type | body format not supported, e.g. XML sent to a JSON-only API, wrong `Content-Type` |
| 429 | Too Many Requests | **rate limit** exceeded |
| 500 | Internal Server Error | unexpected error on the server |
| 501 | Not Implemented | the server doesn't support that functionality |
| 502 | Bad Gateway | a gateway/proxy got an **invalid response** from the upstream server |
| 503 | Service Unavailable | overloaded or under maintenance; try later |
| 504 | Gateway Timeout | a gateway/proxy got **no timely response** from upstream |

**Response headers:** `Set-Cookie`, `Cache-Control: max-age=3600, public`; **entity header** `Content-Type: application/json`.

**Pagination:** large results are split into pages, usually chosen with query parameters
(`?page=2&per_page=20`, `?offset=40&limit=20`, or a `cursor`). Many APIs return a `Link` header with the next page.

**Compression:** for data that can't be paginated, ask for compressed responses with the request header
`Accept-Encoding` (values: `gzip`, `compress`, `deflate`, `br`, `identity`, `*`). The response says which
one it used in `Content-Encoding`.

**Sequence diagrams** show the order of requests between parties, e.g. (1) create a session with
credentials → token, (2) GET the device list with the token, (3) POST to create a device.

```text
Client                      API server
  |--- POST /session (credentials) -->|
  |<-- 200 {token} -------------------|
  |--- GET /devices (token) --------->|
  |<-- 200 [devices] -----------------|
  |--- POST /devices (token, JSON) -->|
  |<-- 201 Created -------------------|
```

### In Python (the `requests` library, as in the DevNet labs)
```python
import requests

BASE = "http://127.0.0.1:8765/practice/api/v1"
login = requests.post(f"{BASE}/auth/login", auth=("learner", "devnet123"))   # Basic auth
token = login.json()["token"]
headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

r = requests.get(f"{BASE}/books", params={"page": 1, "per_page": 5}, headers=headers, timeout=10)
print(r.status_code, r.headers.get("Content-Type"))
print(r.json())

new = requests.post(f"{BASE}/books", json={"title": "Network Programmability", "author": "Me", "year": 2026},
                    headers=headers, timeout=10)      # json= sets Content-Type: application/json
print(new.status_code, new.headers.get("Location"))
```

## 4.5 Authenticating to a REST API

APIs require authentication so random users can't read, create, update or delete data. (Read-only APIs with
nothing sensitive sometimes don't.)

- **Authentication** = proving **who you are** (showing your ID at the airport).
- **Authorization** = proving you're **allowed to do this action** (showing your concert ticket).

**Authentication mechanisms:**
- **Basic:** `username:password` joined with a colon, **Base64-encoded** (not encrypted!) in
  `Authorization: Basic <base64>`. Only safe over HTTPS.
- **Bearer:** a **token** generated by an authentication server (an Identity Service), sent as `Authorization: Bearer <token>`.
- **API key:** a unique string the server generates for a user/app; **public** keys can be shared (identify
  the app), **private** keys must stay secret (like passwords). Sent in a header (e.g. `X-API-Key`), a query
  parameter, or a cookie.

**Authorization: OAuth**
- **OAuth** combines authentication with authorization and replaced insecure approaches (like giving every app your password).
- **OAuth 1.0 and 2.0**; OAuth 2.0 is **not backwards compatible** with 1.0.
- OAuth 2.0 lets a **third-party application get limited access** to an HTTP service. The user gives credentials
  **only to the authorization server** (Identity Provider IdP / Identity Service IdS), which issues an **access
  token** the app uses. The process of getting the token is called a **flow** (e.g. authorization code flow for
  apps with users, client credentials flow for server-to-server).

API Lab: try `GET /books` with no auth (401), with Basic auth, with `X-API-Key: practice-key-123`, and with a Bearer token;
then `POST /books` as the read-only user `viewer` / `viewer123` (403).

## 4.6 API rate limits

A **rate limit** controls how many requests a user/app can make per unit of time. It:
- prevents server **overload**,
- gives **better service and response times** for everyone,
- protects against **Denial-of-Service (DoS)** attacks.

**Algorithms:**
| Algorithm | How it works |
|---|---|
| **Leaky bucket** | requests go into a **queue** (in arrival order); the server processes them at a **fixed rate**; if the queue is full, new requests are rejected |
| **Token bucket** | each client has a bucket of **tokens** refilled over time; each request uses one; **no token → rejected**. Allows short bursts. The client should track its remaining tokens |
| **Fixed window counter** | a counter per fixed time window (e.g. per minute); when the limit for the window is reached, the rest of that window is rejected |
| **Sliding window counter** | counts requests in the window **ending now** (e.g. the last 60 s) to decide; smoother than fixed windows |

**Knowing your limit:** many APIs send headers like
`X-RateLimit-Limit` (max requests per window), `X-RateLimit-Remaining` (left in this window),
`X-RateLimit-Reset` (when the window resets).

**Exceeding it:** the server rejects the request with **429 Too Many Requests** (sometimes **403 Forbidden**),
often with `Retry-After` (seconds to wait).

```python
import time, requests

def get_with_rate_limit(url, headers):
    while True:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 429:
            return r
        wait = int(r.headers.get("Retry-After", "1"))
        print(f"Rate limited; waiting {wait}s")
        time.sleep(wait)
```

API Lab: send 15 quick requests (the **Burst** button) and watch `X-RateLimit-Remaining` drop until you get 429.

## 4.7 Webhooks

A **webhook** is an **HTTP callback**: an HTTP **POST** that a provider sends **to a URL you registered** when
an event happens. Also called a **reverse API**: instead of you calling the API, it calls you.
- No **polling** needed (asking "anything new?" every few seconds), so it's more efficient.
- Many applications can subscribe to the same webhook provider.
- Examples: **Cisco DNA Center** sends network events to third-party apps; **Webex** notifies you of new messages in a room.

To **consume** a webhook your application must:
1. be **running at all times** to receive the POST,
2. **register its URI** with the provider,
3. **handle** the incoming notifications (and reply quickly with 2xx).
Use free online tools (request inspectors) or a local receiver to check you're receiving them.

API Lab: register `http://127.0.0.1:8765/practice/hooks/my-app`, create a book, then see the delivery in the **Webhook inbox**.

## 4.8 Troubleshooting API calls

Always have the **API reference** and your **authentication details** handy.

### No response / no status code
**Client side:**
- **User error:** mistyped URI. **Missing scheme** (`127.0.0.1/api` instead of `http://...`) → Python raises
  `requests.exceptions.MissingSchema` / `InvalidURL`.
- **Wrong domain name** → `ConnectionError` ... `Name or service not known` / `getaddrinfo failed` (DNS couldn't resolve it).
- **Connectivity:** proxy, firewall or VPN in the way?
- **SSL error (HTTPS only):** the certificate is invalid/self-signed → `SSLError: CERTIFICATE_VERIFY_FAILED`.
  In a **lab only**, you may skip verification with `requests.get(url, verify=False)`; in production fix
  the certificate (or trust the right CA with `verify="ca.pem"`).

**Server side:**
- The API server is down (power, cabling, domain name change, network down) → a **long silence, then a timeout**
  traceback (`ConnectTimeout` / `ReadTimeout`). Always set `timeout=` so your script doesn't hang forever.
- Is the response lost between server and client? Use a **packet capture tool** (Wireshark) and check the **server logs**.
- Server-side problems can't be fixed from the client: **contact the API server's administrator**.

### Interpreting status codes
The first digit is the class; the last two just number the codes (RFC 7231). Steps:
1. **Check the return code** (print `r.status_code` during development).
2. **Check the response body**; it often explains the problem (e.g. `"No id field provided"`).
3. **Use a status code reference** if that isn't enough.

| Code | What to check |
|---|---|
| 400 | spelling of fields/resources, JSON syntax, missing required fields |
| 401 | credentials: username/password, API key, token (expired?), the `Authorization` header format |
| 403 | the user is valid but lacks privileges: use an account with the right role (e.g. `person2/super` instead of `person1/great` in the DevNet lab) |
| 404 | the path/ID in the URI |
| 407 | authenticate with the proxy first |
| 409 | a conflict with the current state (duplicate/edit conflict): resolve it, then retry |
| 415 | the body's format/`Content-Type`: send `Content-Type: application/json` (or omit it and use `json=` in requests) |
| 500 | server bug: report it with the request you sent |
| 501 | the server doesn't support that function |
| 502 | gateway/proxy got an invalid response from upstream |
| 503 | overloaded or maintenance: retry later (respect `Retry-After`) |
| 504 | gateway/proxy timed out waiting for upstream |

## Exam traps

- **401 vs 403:** 401 = who are you? (authentication). 403 = I know who you are, but no (authorization).
- **PUT vs PATCH:** PUT replaces the whole resource; PATCH changes some fields.
- **502 vs 504:** 502 = bad answer from upstream; 504 = no answer in time.
- **Basic auth is encoding, not encryption.** Base64 is reversible; only HTTPS protects it.
- **Webhook = the provider POSTs to you**; polling = you GET repeatedly.
- **Token bucket allows bursts; leaky bucket processes at a constant rate.**
- **Stateless** means the server keeps no client session; every request carries its credentials.
- SOAP = **XML only**; REST can use JSON, XML, etc.

## Labs from this module, offline in Jarvis

- *Explore REST APIs with API Simulator and Postman* → API Lab: request builder + code view (Python, curl, JS, PHP).
- *Use Python to add 100 books* → Practice idea: write a loop with `requests` that adds 100 books to the API Lab;
  you'll hit the rate limit and must handle 429 with `Retry-After`.
- *Integrating a REST API with Python (MapQuest)* needs the internet and an API key; do it with the real
  service when you're online. The parsing and error-handling skills are the same as in the API Lab.
