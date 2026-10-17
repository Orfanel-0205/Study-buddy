/* Jarvis mobile service worker.
 * Keeps the app's own files (page, script, styles, icons, Study Buddy's pictures) so it opens instantly
 * and works offline (tasks, flashcards, Study Buddy and focus sessions, Build, saved guides) when Jarvis
 * isn't reachable.
 * Your chats, tasks and project data (/api/...) are never stored on the phone.
 * Browsers only enable this when the connection certificate is trusted.
 */
const VERSION = "{{VERSION}}";
const CACHE = "jarvis-mobile-" + VERSION;
const SHELL = [
  "/m/",
  "/m/manifest.webmanifest",
  "/static/mobile.css?v=" + VERSION,
  "/static/mobile.js?v=" + VERSION,
  "/static/markdown.js?v=" + VERSION,
  "/static/images.js?v=" + VERSION,
  "/static/charts.js?v=" + VERSION,
  "/static/charts.css?v=" + VERSION,
  "/static/sessions.js?v=" + VERSION,
  "/static/companion.js?v=" + VERSION,
  "/static/companion.css?v=" + VERSION,
  "/static/i18n.js?v=" + VERSION,
  "/static/build.js?v=" + VERSION,
  "/static/build.css?v=" + VERSION,
  "/static/companion/packs.json",
  "/static/icons/icon-192.png",
  "/static/icons/logo-mark.png",
];

const ART = "/static/companion/";

/** Every picture of Study Buddy (poses, blink frames, the pouty face), from packs.json. */
async function cacheArt(cache) {
  const res = await fetch(ART + "packs.json", { cache: "no-cache" });
  const files = new Set();
  for (const p of (await res.json()).packs || []) {
    for (const item of p.items) for (const k of ["file", "half", "blink", "plain", "plain_blink"]) if (item[k]) files.add(ART + item[k]);
  }
  await cache.addAll([...files]);
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE)
    .then((c) => c.addAll(SHELL).then(() => cacheArt(c).catch(() => { /* her pictures get saved as they're used */ })))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("jarvis-mobile-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  // Network first, so updates appear as soon as the computer is reachable. A computer that is off
  // or behind a firewall may never answer, so fall back to the saved copy after a few seconds.
  event.respondWith(
    withTimeout(fetch(event.request), 4000)
      .then((res) => {
        if (res.ok && (SHELL.includes(url.pathname + url.search) || url.pathname.startsWith(ART))) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(event.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(event.request).then((saved) => saved || fetch(event.request)))
  );
});

function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("timeout")), ms);
    promise.then((v) => { clearTimeout(timer); resolve(v); }, (e) => { clearTimeout(timer); reject(e); });
  });
}
