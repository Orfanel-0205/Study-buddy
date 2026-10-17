---
title: Making apps fast: what to apply, and when
summary: The speed checklist (caching, indexes, N+1 queries, lazy loading, CDNs and more) with when each one is worth it, how to check, and code in Python, PHP, JavaScript and TypeScript.
tags: performance, speed, optimization, caching, database, frontend, backend, web
order: 1
---

# Making apps fast: what to apply, and when

Popular checklists (like "your vibe-coded website is slow because...") list 15+ fixes at once. They are all
real techniques, but **applying all of them everywhere wastes time and adds bugs**. The professional habit is:

1. **Measure first.** Find what is actually slow.
2. **Fix the biggest bottleneck.**
3. **Measure again.** Keep the change only if it helped.

| Where it's slow | How to measure |
|---|---|
| Page load (browser) | Chrome/Edge DevTools → **Lighthouse**, **Network** tab (size + time of each file), **Performance** tab |
| Server/API | Log how long each request takes; Python `time.perf_counter()`, `cProfile`; PHP Xdebug profiler; Node `console.time()`, `--prof` |
| Database | Log the number of queries per request; run `EXPLAIN` (MySQL/PostgreSQL/SQLite) on slow queries |
| React re-renders | React DevTools → **Profiler** ("Highlight updates when components render") |

The list below is grouped by **when** to apply each item.

## Always do these (cheap habits from day one)

These cost almost nothing when you build the feature, and are painful to add later.

### Paginate large lists
- **What:** return/show data in pages (e.g. 20 items) instead of everything.
- **Apply when:** a list can grow without limit (users, orders, posts, logs). Assume it will.
- **Skip when:** the list is small and fixed (countries, settings).
- **Check:** response size in the Network tab; query time with 10,000 rows.

```sql
-- Offset pagination: simple, fine for most apps
SELECT id, title FROM posts ORDER BY id LIMIT 20 OFFSET 40;   -- page 3
-- Keyset (cursor) pagination: fast even on huge tables
SELECT id, title FROM posts WHERE id > :last_seen_id ORDER BY id LIMIT 20;
```

### Index the database
- **What:** an index lets the database find rows without scanning the whole table (like a book index).
- **Apply when:** a column is used in `WHERE`, `JOIN ... ON`, or `ORDER BY` on a table that will have
  thousands of rows. Foreign keys almost always need an index.
- **Skip when:** the table is tiny, or the column is rarely searched. Each index slows down inserts/updates a little.
- **Check:** `EXPLAIN SELECT ...`: look for "full table scan" (`type: ALL` in MySQL, `SCAN` in SQLite).

```sql
CREATE INDEX idx_orders_user_id ON orders (user_id);
CREATE INDEX idx_posts_status_created ON posts (status, created_at);  -- for WHERE status=? ORDER BY created_at
```

### Avoid N+1 database queries (❌ in the checklist = remove it)
- **What:** loading a list (1 query) and then running one more query **per item** (N queries).
  100 posts → 101 queries. It is the most common reason a backend is slow.
- **Apply when:** always, whenever you loop over results and touch related data.
- **Check:** count queries per request (Laravel Debugbar, Django Debug Toolbar, SQL logging).

```python
# ❌ N+1: one query per author
for post in db.execute("SELECT * FROM posts").fetchall():
    author = db.execute("SELECT name FROM users WHERE id = ?", (post["user_id"],)).fetchone()

# ✅ one query with a JOIN
rows = db.execute("""SELECT posts.title, users.name AS author
                     FROM posts JOIN users ON users.id = posts.user_id""").fetchall()
```

```php
// Laravel: ❌ $posts = Post::all();  then $post->author->name inside the loop (N+1)
$posts = Post::with('author')->paginate(20);   // ✅ eager loading: 2 queries total
```

```js
// ❌ await inside a loop, one request per item
for (const id of ids) users.push(await db.user.findUnique({ where: { id } }));
// ✅ one query for all of them
const users = await db.user.findMany({ where: { id: { in: ids } } });
```

### Compress and size images
- **Apply when:** always for uploaded or large images. Images are usually the heaviest part of a page.
- **How:** serve the size you display (not a 4000px photo in a 300px box), use **WebP/AVIF**,
  and compress (quality 70–80 is fine).
- **Check:** Network tab → sort by size; Lighthouse "Properly size images".

```html
<img src="photo-800.webp" srcset="photo-400.webp 400w, photo-800.webp 800w" sizes="(max-width: 600px) 400px, 800px"
     width="800" height="600" loading="lazy" alt="Team photo">
```

### Lazy loading
- **What:** load images, iframes or code only when they are about to be needed.
- **Apply when:** content is below the fold (not visible without scrolling), or a heavy feature is rarely used.
- **Skip when:** the main image at the top of the page (lazy loading it makes the page *feel slower*).

### Minify JS and CSS
- **What:** remove spaces/comments and shorten names so files download faster.
- **Apply when:** in production builds, always. Your bundler (Vite, webpack, esbuild) does it automatically
  with `npm run build`, so just make sure you deploy the build output, not the dev files.
- **Skip when:** during development (it makes debugging harder).

### Defer non-critical scripts
- **Apply when:** a script isn't needed to show the page (analytics, chat widgets, ads).

```html
<script src="/app.js" defer></script>          <!-- runs after the HTML is parsed, in order -->
<script src="/analytics.js" async></script>     <!-- runs whenever it arrives, order not guaranteed -->
```

### Remove unused dependencies (❌ in the checklist = remove it)
- **What:** every package adds download size, install time and security risk.
- **Apply when:** before each release, and before adding a new package ("do I really need it?").
- **Check:** `npx depcheck` (JS), `composer why <pkg>` / `composer-unused` (PHP), `pip-autoremove` or
  `deptry` (Python); bundle size with `npx vite-bundle-visualizer`.

### Compress API payloads
- **What:** gzip/brotli compression of responses. JSON shrinks 70–90%.
- **Apply when:** almost always. It's usually one setting in the web server.
- **How:** Nginx `gzip on;`, Apache `mod_deflate`, Express `app.use(compression())`,
  FastAPI `app.add_middleware(GZipMiddleware, minimum_size=1000)`.
  The client asks with `Accept-Encoding: gzip, br` (browsers do this automatically).
- **Also:** don't send fields the client doesn't use.

### Debounce input handlers
- **What:** wait until the user stops typing (e.g. 300 ms) before searching or saving.
- **Apply when:** search-as-you-type, autosave, window resize/scroll handlers.

```js
function debounce(fn, ms = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
searchBox.addEventListener("input", debounce((e) => search(e.target.value), 300));
```

### Database connection pooling
- **What:** reuse open database connections instead of opening a new one for every request (opening one
  can take 20–100 ms).
- **Apply when:** long-running servers (Node, Python ASGI/WSGI, Java). Most ORMs/drivers pool by default:
  just create the pool **once** at startup, not inside each request.
- **Note for PHP:** classic PHP-FPM starts fresh per request; use persistent PDO connections or a pooler
  (e.g. PgBouncer for PostgreSQL) only if connection time shows up in measurements.

```js
// Node + PostgreSQL: create ONE pool when the app starts and share it
import pg from "pg";
export const pool = new pg.Pool({ max: 10 });
const { rows } = await pool.query("SELECT * FROM users WHERE id = $1", [id]);
```

## Apply when you see a symptom

### Loading skeletons
- **What:** grey placeholder shapes while data loads. They don't make anything faster; they make waiting
  feel shorter and stop the layout from jumping.
- **Apply when:** data takes more than ~300 ms to appear.
- **Skip when:** data is instant, or the real problem is a slow API (fix that first).

### Cache expensive queries
- **What:** store the result of a slow query/calculation (in memory, Redis, or a table) and reuse it.
- **Apply when:** the same expensive query runs often **and** the data changes rarely (dashboards,
  leaderboards, category lists).
- **Skip when:** data must always be live (bank balance), or the query is already fast.
- **The hard part:** **invalidation**: decide when the cache is cleared (after N seconds, or when the data changes).

```python
import time
_cache = {}
def top_products():
    hit = _cache.get("top")
    if hit and time.time() - hit[0] < 60:      # reuse for 60 seconds
        return hit[1]
    result = db.execute("SELECT ... expensive ...").fetchall()
    _cache["top"] = (time.time(), result)
    return result
```

### Cache API responses (HTTP caching)
- **What:** let browsers/CDNs reuse responses using HTTP headers.
- **Apply when:** responses are the same for everyone or change rarely (product catalogue, public profiles, static files).
- **Never** cache personal data publicly: use `Cache-Control: private` or `no-store`.

```php
header('Cache-Control: public, max-age=300');           // reuse for 5 minutes
header('ETag: "' . md5($json) . '"');                  // lets clients ask "has it changed?" → 304 Not Modified
```

```js
res.set("Cache-Control", "public, max-age=300");        // Express
```

### Split code into chunks (code splitting)
- **What:** ship only the JavaScript needed for the current page; load the rest on demand.
- **Apply when:** your JS bundle is large (Lighthouse "Reduce unused JavaScript", or over ~200 KB gzipped),
  especially in single-page apps with many routes.

```js
// React + Vite: each page becomes its own file, loaded when visited
const Settings = React.lazy(() => import("./pages/Settings"));
```

### Unnecessary re-renders (❌ in the checklist = remove it)
- **What:** React components redrawing when nothing they show has changed.
- **Apply when:** the React Profiler shows slow or frequent renders, or typing/scrolling feels laggy.
- **How:** keep state close to where it's used; split big components; `React.memo` for pure components;
  `useMemo`/`useCallback` for expensive values and callbacks passed to memoized children; stable `key`s in lists.
- **Skip when:** there is no measured problem. Adding `memo` everywhere adds complexity for no gain.

## Apply at scale (many users)

### CDN (Content Delivery Network)
- **What:** copies of your static files (images, JS, CSS) on servers around the world.
- **Apply when:** users are far from your server, or you serve lots of static files/media.
  Many hosts include one (Cloudflare, Vercel, Netlify).
- **Skip when:** an internal/school app used in one place.

### Load balancer
- **What:** spreads requests across several copies of your server, and keeps the site up if one fails.
- **Apply when:** one server can't handle the traffic, or you need high availability.
- **Before you can:** your app must be **stateless**: sessions stored in a database/Redis, files in shared
  storage, not on the local disk (this is the REST "stateless" constraint from DevNet).
- **Skip when:** you have not maxed out one server yet. Optimize code and queries first; that's cheaper.

## Quick decision table

| Symptom you measured | First things to try |
|---|---|
| Page slow to appear, big Network total | compress/size images, lazy load, defer scripts, minify (production build), code splitting |
| API endpoint slow | count queries (N+1?), add indexes, paginate, then cache |
| Database CPU high | `EXPLAIN` + indexes, fix N+1, cache expensive queries |
| Typing/scrolling laggy | debounce handlers, fix unnecessary re-renders, virtualize very long lists |
| Fine for you, slow for far-away users | CDN, compression |
| Server overloaded at peak times | caching, connection pooling, then more servers + load balancer |

Rule of thumb: **correctness first, then measure, then optimize the slowest part.** "Premature optimization
is the root of all evil" (Donald Knuth) means: don't optimize what you haven't measured, not "never optimize".
