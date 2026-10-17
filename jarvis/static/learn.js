/* Learn page on the computer: built-in guides, coding practice (Python, JavaScript, TypeScript, PHP),
 * the API Lab (a practice REST API inside Jarvis, for DevNet-style labs offline) and starter flashcard decks.
 * Uses the helpers app.js exposes as window.JarvisUI. */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const ui = () => window.JarvisUI;
  const MD = window.JarvisMarkdown;
  const LANG_LABEL = { python: "Python", javascript: "JavaScript", typescript: "TypeScript", php: "PHP" };
  const TABS = [["guides", "Guides"], ["practice", "Practice"], ["lab", "API Lab"], ["charts", "Chart helper"], ["decks", "Starter decks"]];
  const S = {
    tab: "guides", guides: null, guideId: null, anchor: null, query: "",
    exercises: null, runtimes: null, canRun: true, exerciseId: null, filter: { language: "", topic: "" },
    hintIndex: 0, lastResults: [], saveTimer: 0,
    lab: { method: "GET", path: "/practice/api/v1/books?page=1&per_page=5", auth: "apikey", user: "learner",
      password: "devnet123", token: "", tokens: {}, headers: "", body: "", codeLang: "python", last: null, note: "" },
  };

  const slug = (t) => String(t).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

  async function render() {
    const { el, fill } = ui();
    const page = $("#learn-page");
    const body = el("div", { class: "learn-body" });
    fill(page,
      el("div", { class: "page-head" }, el("h2", { text: "Learn" }),
        el("div", { class: "seg learn-tabs", role: "tablist", "aria-label": "Learn sections" },
          TABS.map(([id, label]) => el("button", { type: "button", role: "tab", "aria-pressed": String(S.tab === id),
            "aria-selected": String(S.tab === id), onclick: () => { S.tab = id; render(); } }, label))),
        el("span", { class: "spacer" }),
        el("span", { class: "muted small", text: "Everything here works offline, on this computer and on Jarvis on your phone." })),
      body);
    if (window.JarvisCompanion) window.JarvisCompanion.setContext({ view: "learn", tab: S.tab });
    try {
      if (S.tab === "guides") await renderGuides(body);
      else if (S.tab === "practice") await renderPractice(body);
      else if (S.tab === "lab") renderLab(body);
      else if (S.tab === "charts") renderCharts(body);
      else await renderDecks(body);
    } catch (err) { ui().showError(err); }
  }

  // ------------------------------------------------------------------ guides
  async function renderGuides(body) {
    const { el, fill, api } = ui();
    if (!S.guides) S.guides = await api("/api/learn/guides");
    if (!S.guideId) S.guideId = S.guides[0] && S.guides[0].id;
    const results = el("div", { class: "guide-results" });
    const search = el("input", { type: "search", placeholder: "Search the guides (e.g. 401 vs 403, merge conflict, N+1)",
      value: S.query, "aria-label": "Search the guides" });
    let timer = 0;
    search.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        S.query = search.value.trim();
        if (!S.query) return fill(results);
        const hits = await api("/api/learn/search?q=" + encodeURIComponent(S.query));
        fill(results, hits.length ? hits.map((h) => el("button", { class: "guide-hit", onclick: () => openGuide(h.guide, h.anchor) },
          el("strong", { text: h.section }), el("span", { class: "muted small", text: h.guide_title }),
          el("span", { class: "small", text: h.snippet + "…" }))) : el("p", { class: "muted small", text: "Nothing found. Try other words." }));
      }, 250);
    });
    const list = el("nav", { class: "guide-list", "aria-label": "Guides" },
      S.guides.map((g) => el("button", { class: "guide-item" + (g.id === S.guideId ? " active" : ""), onclick: () => openGuide(g.id) },
        el("strong", { text: g.title }), el("span", { class: "muted small", text: g.summary }))));
    const article = el("article", { class: "card guide-article" }, el("p", { class: "muted", text: "Loading…" }));
    fill(body, el("div", { class: "learn-grid" }, el("div", { class: "learn-side" }, search, results, list), article));
    if (S.query) search.dispatchEvent(new Event("input"));
    if (S.guideId) showGuide(article);
  }

  async function showGuide(article) {
    const { el, fill, api, askInChat } = ui();
    const g = await api("/api/learn/guides/" + encodeURIComponent(S.guideId));
    const content = el("div", { class: "md guide-body", html: MD.renderMarkdown(g.markdown) });
    sectionIds(content);
    let decks = [];
    try { decks = (await api("/api/learn/decks")).filter((d) => d.guide === g.id); } catch (_) { /* optional */ }
    fill(article,
      el("div", { class: "row guide-actions" },
        el("button", { class: "primary small", onclick: () => askInChat(`Quiz me on the guide "${g.title}". Ask one question at a time and wait for my answer.`, "study", true) }, "Quiz me (chat)"),
        el("button", { class: "small", onclick: () => askInChat(`About the guide "${g.title}": `, g.id === "workplace" ? "coach" : "study") }, "Ask a question"),
        decks.map((d) => el("button", { class: "small", disabled: d.installed && !d.missing,
          onclick: async (e) => { e.currentTarget.disabled = true; await installDeck(d); showGuide(article); } },
        d.installed ? (d.missing ? `Update flashcards (${d.missing} new)` : "Flashcards added ✓") : `Add ${d.cards} flashcards`)),
        el("span", { class: "spacer" }),
        el("span", { class: "muted small", text: "Sections: " }),
        el("select", { class: "small", "aria-label": "Jump to section", onchange: (e) => jump(content, e.target.value) },
          el("option", { value: "", text: "Jump to…" }),
          [...content.querySelectorAll("h3")].map((h) => el("option", { value: h.id, text: h.textContent })))),
      content);
    if (S.anchor) { jump(content, S.anchor); S.anchor = null; } else article.scrollTop = 0;
  }

  /** The Markdown renderer shifts headings down one level (# → h2, ## → h3, ### → h4). Give sections the
   * same ids the server uses for search results: "## Topic" → topic, "### Sub" → topic-sub. */
  function sectionIds(content) {
    let topic = "";
    for (const h of content.querySelectorAll("h3, h4")) {
      if (h.tagName === "H3") { topic = h.textContent; h.id = slug(topic); }
      else h.id = slug(topic ? `${topic} › ${h.textContent}` : h.textContent);
    }
  }

  function jump(content, id) {
    if (!id) return;
    const target = content.querySelector("#" + CSS.escape(id)) ||
      [...content.querySelectorAll("h3, h4")].find((h) => h.id.startsWith(id) || id.startsWith(h.id));
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function openGuide(id, anchor) {
    S.tab = "guides";
    S.guideId = id;
    S.anchor = anchor || null;
    render();
  }

  // ------------------------------------------------------------------ starter decks
  async function installDeck(d) {
    const { api, toast } = ui();
    const r = await api(`/api/learn/decks/${d.key}/install`, { method: "POST" });
    toast(r.added ? `Added ${r.added} card(s) to "${r.name}". Review them in Study.` : `"${r.name}" is up to date.`, "ok");
  }

  async function renderDecks(body) {
    const { el, fill, api, switchView } = ui();
    const decks = await api("/api/learn/decks");
    fill(body,
      el("p", { class: "muted", text: "Ready-made flashcards written from the guides. They sync with Jarvis on your phone, and adding the same deck on both is safe: it stays one deck." }),
      el("div", { class: "deck-grid" }, decks.map((d) => el("div", { class: "card deck" },
        el("h3", { text: d.name }), el("p", { class: "muted small", text: d.description }),
        el("div", { class: "row small muted" }, `${d.cards} cards`,
          d.installed ? el("span", { class: "badge safe", text: d.missing ? `${d.missing} new` : "added" }) : null),
        el("div", { class: "row", style: "margin-top:10px" },
          el("button", { class: d.installed && !d.missing ? "small" : "primary small", disabled: d.installed && !d.missing,
            onclick: async () => { await installDeck(d); render(); } }, d.installed ? (d.missing ? "Add new cards" : "Added ✓") : "Add to Study"),
          d.installed ? el("button", { class: "small", onclick: () => switchView("study") }, "Review") : null,
          el("button", { class: "small ghost", onclick: () => openGuide(d.guide) }, "Read the guide"))))));
  }

  // ------------------------------------------------------------------ practice
  async function loadExercises() {
    const data = await ui().api("/api/learn/exercises");
    S.exercises = data.exercises;
    S.runtimes = data.runtimes;
    S.canRun = data.can_run;
  }

  async function renderPractice(body) {
    const { el, fill } = ui();
    await loadExercises();
    const topics = [...new Set(S.exercises.map((e) => e.topic))].sort();
    const shown = S.exercises.filter((e) => (!S.filter.language || e.language === S.filter.language) && (!S.filter.topic || e.topic === S.filter.topic));
    if (!S.exerciseId || !S.exercises.some((e) => e.id === S.exerciseId)) S.exerciseId = (shown[0] || S.exercises[0]).id;
    const solved = S.exercises.filter((e) => e.solved).length;
    const select = (key, options, label) => el("select", { "aria-label": label, onchange: (e) => { S.filter[key] = e.target.value; render(); } },
      options.map(([v, t]) => el("option", { value: v, text: t, selected: S.filter[key] === v })));
    const detail = el("section", { class: "card practice-detail" }, el("p", { class: "muted", text: "Loading…" }));
    fill(body,
      el("div", { class: "row runtime-row" },
        Object.entries(S.runtimes).map(([lang, r]) => el("span", { class: "badge " + (r.available ? "safe" : "caution"),
          title: r.available ? `Runs with ${r.version}` : r.install }, `${r.label} ${r.available ? "✓" : "not installed"}`)),
        el("span", { class: "spacer" }),
        el("strong", { text: `${solved} of ${S.exercises.length} solved` })),
      el("div", { class: "learn-grid" },
        el("div", { class: "learn-side" },
          el("div", { class: "row" },
            select("language", [["", "All languages"], ...Object.entries(LANG_LABEL)], "Language"),
            select("topic", [["", "All topics"], ...topics.map((t) => [t, t])], "Topic")),
          el("nav", { class: "exercise-list", "aria-label": "Exercises" }, shown.map((e) => el("button", {
            class: "exercise-item" + (e.id === S.exerciseId ? " active" : ""), onclick: () => { S.exerciseId = e.id; S.hintIndex = 0; S.lastResults = []; render(); } },
            el("span", { class: "lang-tag " + e.language, text: LANG_LABEL[e.language] }),
            el("span", { class: "grow", text: e.title }),
            e.solved ? el("span", { class: "solved", title: "Solved", text: "✓" }) : el("span", { class: "muted small", text: e.level }))))),
        detail));
    showExercise(detail);
  }

  async function showExercise(box) {
    const { el, fill, api } = ui();
    const ex = await api("/api/learn/exercises/" + S.exerciseId);
    const runtime = S.runtimes[ex.language];
    const editor = el("textarea", { class: "code-editor", spellcheck: "false", autocapitalize: "off", autocomplete: "off",
      "aria-label": "Your code", rows: "16" });
    editor.value = ex.code;
    const indent = ex.language === "python" || ex.language === "php" ? "    " : "  ";
    editor.addEventListener("keydown", (e) => {
      if (e.key === "Tab" && !e.shiftKey) {
        e.preventDefault();
        editor.setRangeText(indent, editor.selectionStart, editor.selectionEnd, "end");
        scheduleSave(editor);
      } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); check(); }
    });
    editor.addEventListener("input", () => scheduleSave(editor));
    const results = el("div", { class: "practice-results", "aria-live": "polite" });
    const hintBox = el("div", { class: "hint-box", hidden: true });
    const runBtn = el("button", { class: "primary", onclick: () => check(), disabled: !S.canRun || !runtime.available,
      title: "Run the tests on your code (Ctrl+Enter)" }, "Check my code");
    async function check() {
      if (runBtn.disabled) return;
      runBtn.disabled = true;
      runBtn.textContent = "Checking…";
      try {
        const r = await api(`/api/learn/exercises/${ex.id}/run`, { method: "POST", body: { code: editor.value } });
        S.lastResults = r.results;
        showResults(results, r);
        if (r.ok) ui().toast(r.attempts > 1 ? "All tests pass. Well done!" : "All tests pass on the first try!", "ok");
        if (window.JarvisCompanion) window.JarvisCompanion.react(r.ok ? "tests_passed" : "tests_failed");
        const row = S.exercises.find((e) => e.id === ex.id);
        if (row && r.solved && !row.solved) { row.solved = true; }
      } catch (err) { ui().showError(err); }
      runBtn.disabled = false;
      runBtn.textContent = "Check my code";
    }
    function nextHint() {
      hintBox.hidden = false;
      if (S.hintIndex < ex.hints.length) {
        hintBox.append(el("p", {}, el("strong", { text: `Hint ${S.hintIndex + 1}: ` }), el("span", { html: MD.renderMarkdown(ex.hints[S.hintIndex]).replace(/^<p>|<\/p>$/g, "") })));
        S.hintIndex += 1;
        return;
      }
      askModel();
    }
    async function askModel() {
      const wait = el("p", { class: "muted small", text: "Asking Jarvis for a hint about your code…" });
      hintBox.append(wait);
      try {
        const r = await api(`/api/learn/exercises/${ex.id}/hint`, { method: "POST", body: { code: editor.value, results: S.lastResults }, timeout: 180000 });
        wait.replaceWith(el("div", { class: "md" }, el("strong", { text: "Jarvis: " }), el("span", { html: MD.renderMarkdown(r.hint) })));
      } catch (err) { wait.remove(); ui().showError(err); }
    }
    fill(box,
      el("div", { class: "row" }, el("h3", { class: "grow", text: ex.title }),
        el("span", { class: "lang-tag " + ex.language, text: LANG_LABEL[ex.language] }),
        el("span", { class: "badge", text: ex.topic }), el("span", { class: "badge", text: ex.level }),
        ex.solved ? el("span", { class: "badge safe", text: "solved ✓" }) : null),
      el("div", { class: "md exercise-task", html: MD.renderMarkdown(ex.task) }),
      ex.guide ? el("p", { class: "small" }, el("a", { href: "#", onclick: (e) => { e.preventDefault(); openGuide(ex.guide); } }, "Read the related guide")) : null,
      !S.canRun ? el("div", { class: "notice warn", text: "Running code only happens on the device Jarvis runs on. Use Jarvis on your computer, or Jarvis on your phone." }) : null,
      !runtime.available ? el("div", { class: "notice warn", text: `${runtime.label} isn't installed on this device. ${runtime.install}` }) : null,
      editor,
      el("div", { class: "row" }, runBtn,
        el("button", { onclick: nextHint, title: "Show the next hint; after the built-in hints, Jarvis looks at your code" }, "Hint"),
        el("span", { class: "spacer" }),
        el("button", { class: "ghost small", onclick: async () => {
          if (!(await ui().confirmDialog({ title: "Start over?", message: "Your code for this exercise will be replaced by the starter code.", confirmLabel: "Start over" }))) return;
          editor.value = ex.starter; scheduleSave(editor); fill(results); } }, "Start over"),
        el("button", { class: "ghost small", onclick: async () => {
          if (!(await ui().confirmDialog({ title: "Show the solution?", message: "Try a hint first: you learn more by solving it. Show the reference solution anyway?", confirmLabel: "Show it" }))) return;
          const sol = await api(`/api/learn/exercises/${ex.id}/solution`);
          ui().openModal({ title: "Reference solution", body: el("pre", { class: "solution" }, el("code", { text: sol.solution })),
            actions: [{ label: "Close" }] });
        } }, "Solution")),
      el("p", { class: "muted small", text: `${ex.checks} tests. Your code runs on this device with ${runtime.version || runtime.label} and a 15-second limit, like running your own script. It's saved as you type.` }),
      hintBox, results);
    S.hintIndex = 0;
  }

  function scheduleSave(editor) {
    clearTimeout(S.saveTimer);
    const id = S.exerciseId;
    S.saveTimer = setTimeout(() => {
      ui().api(`/api/learn/exercises/${id}/code`, { method: "PUT", body: { code: editor.value } }).catch(() => {});
    }, 800);
  }

  function showResults(box, r) {
    const { el, fill } = ui();
    fill(box,
      el("div", { class: "result-head " + (r.ok ? "ok" : "bad") },
        el("strong", { text: r.problem ? r.problem : r.ok ? `All ${r.total} tests pass ✓` : `${r.passed} of ${r.total} tests pass` }),
        el("span", { class: "muted small", text: r.runtime ? ` · ${r.runtime} · ${r.seconds}s` : "" })),
      el("ul", { class: "test-list" }, r.results.map((t) => el("li", { class: t.ok ? "ok" : "bad" },
        el("span", { class: "mark", text: t.ok ? "✓" : "✗" }), el("span", { text: t.name }),
        t.detail ? el("pre", { class: "detail", text: t.detail }) : null))),
      r.output ? el("details", { open: true }, el("summary", { text: "Your program's output" }), el("pre", { text: r.output })) : null,
      r.errors ? el("details", { open: !r.results.length }, el("summary", { text: "Error output" }), el("pre", { text: r.errors })) : null);
  }

  // ------------------------------------------------------------------ API Lab
  const API = "/practice/api/v1";
  const SCENARIOS = [
    { title: "1. No credentials", expect: "401 Unauthorized", why: "The API doesn't know who you are (authentication).", method: "GET", path: `${API}/books`, auth: "none" },
    { title: "2. API key + pagination", expect: "200 OK with X-Total-Count, Link and X-RateLimit headers", why: "An API key identifies the app. Look at the headers.", method: "GET", path: `${API}/books?page=2&per_page=5`, auth: "apikey" },
    { title: "3. Basic auth → token", expect: "200 OK with a Bearer token (saved for the next steps)", why: "Basic = Base64(username:password). It's encoding, not encryption.", method: "POST", path: `${API}/auth/login`, auth: "basic", user: "learner", password: "devnet123" },
    { title: "4. Bearer token", expect: "200 OK", why: "The token proves who you are on every request (stateless).", method: "GET", path: `${API}/books/4`, auth: "bearer", login: "learner" },
    { title: "5. Read-only user writes", expect: "403 Forbidden", why: "Authenticated as viewer, but not authorized to create books.", method: "POST", path: `${API}/books`, auth: "bearer", login: "viewer",
      headers: "Content-Type: application/json", body: '{"title": "Not allowed", "author": "Viewer"}' },
    { title: "6. Wrong Content-Type", expect: "415 Unsupported Media Type", why: "This API only accepts JSON bodies.", method: "POST", path: `${API}/books`, auth: "bearer", login: "learner",
      headers: "Content-Type: text/plain", body: "title=Hello" },
    { title: "7. Missing field", expect: "400 Bad Request with details", why: "The body is valid JSON, but title is required.", method: "POST", path: `${API}/books`, auth: "bearer", login: "learner",
      headers: "Content-Type: application/json", body: '{"author": "Me"}' },
    { title: "8. Create a book", expect: "201 Created + Location header", why: "POST creates. The Location header points to the new resource.", method: "POST", path: `${API}/books`, auth: "bearer", login: "learner",
      headers: "Content-Type: application/json", body: () => JSON.stringify({ title: "My DevNet notes", author: "Me", year: new Date().getFullYear(), isbn: "me-" + Math.random().toString(36).slice(2, 8) }, null, 2) },
    { title: "9. Duplicate", expect: "409 Conflict", why: "A book with that isbn already exists.", method: "POST", path: `${API}/books`, auth: "bearer", login: "learner",
      headers: "Content-Type: application/json", body: '{"title": "Clean Code", "author": "Robert C. Martin", "isbn": "978-0132350884"}' },
    { title: "10. Partial update", expect: "200 OK", why: "PATCH changes some fields; PUT would need the whole book.", method: "PATCH", path: `${API}/books/1`, auth: "bearer", login: "learner",
      headers: "Content-Type: application/json", body: '{"year": 2001}' },
    { title: "11. Unknown resource", expect: "404 Not Found", why: "Check the path and the id.", method: "GET", path: `${API}/books/9999`, auth: "apikey" },
    { title: "12. Rate limit", expect: "429 Too Many Requests + Retry-After", why: "Token bucket: 10 requests, refilled 1 per second. Uses Burst.", method: "GET", path: `${API}/books`, auth: "basic", user: "viewer", password: "viewer123", burst: 12 },
    { title: "13. Asynchronous job", expect: "202 Accepted, then poll the Location", why: "The server answers at once and works in the background.", method: "POST", path: `${API}/reports`, auth: "bearer", login: "learner" },
    { title: "14. Flaky service", expect: "503 twice, then 200", why: "Retry temporary errors after Retry-After. Send it 3 times.", method: "GET", path: `${API}/flaky`, auth: "apikey" },
    { title: "15. Register a webhook", expect: "201 Created with a secret", why: "Then do step 8 again and watch the Webhook inbox below.", method: "POST", path: `${API}/webhooks`, auth: "bearer", login: "learner",
      headers: "Content-Type: application/json", body: () => JSON.stringify({ url: location.origin + "/practice/hooks/my-app", events: ["book.created", "book.deleted"] }, null, 2) },
    { title: "16. SOAP (XML)", expect: "200 with a SOAP Envelope", why: "SOAP: Envelope, Header, Body, Fault — always XML.", method: "POST", path: "/practice/soap", auth: "none",
      headers: "Content-Type: text/xml", body: '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">\n  <soap:Body>\n    <GetBook><id>3</id></GetBook>\n  </soap:Body>\n</soap:Envelope>' },
    { title: "17. JSON-RPC", expect: "200 with a result", why: "RPC calls a method by name instead of acting on a resource.", method: "POST", path: "/practice/rpc", auth: "none",
      headers: "Content-Type: application/json", body: '{"jsonrpc": "2.0", "method": "books.get", "params": {"id": 2}, "id": 1}' },
  ];

  const STATUS_TEXT = {
    200: "OK — success", 201: "Created — see the Location header", 202: "Accepted — processing in the background (asynchronous)",
    204: "No Content — success, nothing returned", 400: "Bad Request — fix the request (fields, JSON syntax)",
    401: "Unauthorized — not authenticated: check credentials/token", 403: "Forbidden — authenticated but not allowed",
    404: "Not Found — check the path and id", 405: "Method Not Allowed", 409: "Conflict — duplicate or conflicting state",
    413: "Payload Too Large", 415: "Unsupported Media Type — send the right Content-Type", 422: "Unprocessable — values fail validation",
    429: "Too Many Requests — wait Retry-After seconds", 500: "Internal Server Error — server problem (SOAP faults use 500 too)",
    502: "Bad Gateway", 503: "Service Unavailable — temporary; retry later", 504: "Gateway Timeout",
  };

  function renderLab(body) {
    const { el, fill } = ui();
    const L = S.lab;
    const method = el("select", { "aria-label": "Method", onchange: (e) => { L.method = e.target.value; refreshCode(); } },
      ["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => el("option", { value: m, text: m, selected: L.method === m })));
    const path = el("input", { type: "text", class: "mono", value: L.path, "aria-label": "Path", oninput: (e) => { L.path = e.target.value; refreshCode(); } });
    const auth = el("select", { "aria-label": "Authentication", onchange: (e) => { L.auth = e.target.value; render(); } },
      [["none", "No auth"], ["basic", "Basic auth"], ["bearer", "Bearer token"], ["apikey", "API key"]].map(([v, t]) => el("option", { value: v, text: t, selected: L.auth === v })));
    const authFields = L.auth === "basic" ? el("div", { class: "row" },
      el("input", { type: "text", value: L.user, placeholder: "username", "aria-label": "Username", oninput: (e) => { L.user = e.target.value; refreshCode(); } }),
      el("input", { type: "text", value: L.password, placeholder: "password", "aria-label": "Password", oninput: (e) => { L.password = e.target.value; refreshCode(); } }))
      : L.auth === "bearer" ? el("input", { type: "text", class: "mono", value: L.token, placeholder: "token from step 3 (POST /auth/login)", "aria-label": "Token", oninput: (e) => { L.token = e.target.value; refreshCode(); } })
      : L.auth === "apikey" ? el("span", { class: "muted small", text: "Sends X-API-Key: practice-key-123 (read only)" }) : null;
    const headers = el("textarea", { class: "mono", rows: "2", placeholder: "Extra headers, one per line: Name: value", "aria-label": "Headers",
      oninput: (e) => { L.headers = e.target.value; refreshCode(); } });
    headers.value = L.headers;
    const bodyBox = el("textarea", { class: "mono", rows: "6", placeholder: "Request body (JSON or XML)", "aria-label": "Body",
      oninput: (e) => { L.body = e.target.value; refreshCode(); } });
    bodyBox.value = L.body;
    const response = el("div", { class: "lab-response" });
    const code = el("pre", { class: "lab-code" });
    const codeTabs = el("div", { class: "seg small", role: "group", "aria-label": "Code language" },
      [["curl", "curl"], ["python", "Python"], ["javascript", "JavaScript"], ["typescript", "TypeScript"], ["php", "PHP"]].map(([id, label]) =>
        el("button", { type: "button", "aria-pressed": String(L.codeLang === id), onclick: (e) => {
          L.codeLang = id; for (const b of e.currentTarget.parentNode.children) b.setAttribute("aria-pressed", String(b === e.currentTarget)); refreshCode(); } }, label)));
    const inbox = el("div", { class: "lab-inbox" });
    const sendBtn = el("button", { class: "primary", onclick: () => send(), title: "Send (Ctrl+Enter)" }, "Send");
    function refreshCode() { code.textContent = snippet(L); }
    async function send(times) {
      sendBtn.disabled = true;
      try {
        const n = times || 1;
        const statuses = [];
        let last = null;
        for (let i = 0; i < n; i++) {
          last = await sendRequest(L);
          statuses.push(last.status);
        }
        showResponse(response, last, n > 1 ? statuses : null);
        if (last.json && last.json.token && /\/auth\/login$/.test(L.path)) {
          L.token = last.json.token;
          L.tokens[last.json.user] = last.json.token;
          L.note = `Token saved for ${last.json.user}. Steps that need a Bearer token will use it.`;
        }
        if (last.status === 202 && last.headers.location) {
          response.append(el("button", { class: "small", onclick: () => { L.method = "GET"; L.path = last.headers.location; L.body = ""; L.headers = ""; render(); } }, "Poll the Location URL"));
        }
        loadInbox(inbox);
      } catch (err) { ui().showError(err); }
      sendBtn.disabled = false;
    }
    for (const box of [path, headers, bodyBox]) box.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); } });
    fill(body,
      el("div", { class: "learn-grid lab" },
        el("div", { class: "learn-side" },
          el("div", { class: "card small" },
            el("strong", { text: "Practice logins" }),
            el("ul", { class: "plain" },
              el("li", {}, el("code", { text: "learner / devnet123" }), " — can read and write"),
              el("li", {}, el("code", { text: "viewer / viewer123" }), " — read only"),
              el("li", {}, el("code", { text: "X-API-Key: practice-key-123" }), " — read only")),
            el("p", { class: "muted", text: "Base URL for your own scripts: " + location.origin + API }),
            el("button", { class: "ghost small", onclick: async () => { await fetch("/practice/lab/reset", { method: "POST" }); L.tokens = {}; L.token = ""; ui().toast("Practice data reset", "ok"); render(); } }, "Reset the practice data")),
          el("nav", { class: "scenario-list", "aria-label": "Scenarios" }, SCENARIOS.map((sc) => el("button", { class: "scenario", onclick: () => loadScenario(sc) },
            el("strong", { text: sc.title }), el("span", { class: "small muted", text: "Expect: " + sc.expect }))))),
        el("section", { class: "card lab-main" },
          L.note ? el("div", { class: "notice", text: L.note }) : null,
          el("div", { class: "row" }, method, path, sendBtn,
            el("button", { onclick: () => send(12), title: "Send the same request 12 times quickly (for the rate limit)" }, "Burst ×12")),
          el("div", { class: "row" }, auth, authFields),
          headers, bodyBox, response,
          el("div", { class: "row", style: "margin-top:12px" }, el("strong", { text: "The same request in code" }), el("span", { class: "spacer" }), codeTabs),
          code,
          el("div", { class: "row", style: "margin-top:12px" }, el("strong", { text: "Webhook inbox" }), el("span", { class: "spacer" }),
            el("button", { class: "small", onclick: () => loadInbox(inbox) }, "Refresh"),
            el("button", { class: "small ghost", onclick: async () => { await fetch("/practice/hooks", { method: "DELETE" }); loadInbox(inbox); } }, "Clear")),
          inbox)));
    refreshCode();
    if (L.last) showResponse(response, L.last);
    loadInbox(inbox);
  }

  async function loadScenario(sc) {
    const L = S.lab;
    L.method = sc.method; L.path = sc.path; L.auth = sc.auth;
    L.headers = sc.headers || ""; L.body = typeof sc.body === "function" ? sc.body() : (sc.body || "");
    if (sc.user) { L.user = sc.user; L.password = sc.password; }
    L.note = `${sc.title}: expect ${sc.expect}. ${sc.why}`;
    L.last = null;
    if (sc.login) {
      if (!L.tokens[sc.login]) {
        const pw = sc.login === "viewer" ? "viewer123" : "devnet123";
        const r = await fetch(`${API}/auth/login`, { method: "POST", headers: { Authorization: "Basic " + btoa(`${sc.login}:${pw}`) } });
        const data = await r.json().catch(() => ({}));
        if (data.token) L.tokens[sc.login] = data.token;
      }
      L.token = L.tokens[sc.login] || "";
      L.note += ` (Logged in as ${sc.login} to get a token.)`;
    }
    render();
    if (sc.burst) setTimeout(() => { const b = [...document.querySelectorAll(".lab-main button")].find((x) => x.textContent.startsWith("Burst")); if (b) b.click(); }, 50);
  }

  function requestHeaders(L) {
    const h = {};
    for (const line of L.headers.split("\n")) {
      const i = line.indexOf(":");
      if (i > 0) h[line.slice(0, i).trim()] = line.slice(i + 1).trim();
    }
    if (L.auth === "basic") h.Authorization = "Basic " + btoa(unescape(encodeURIComponent(`${L.user}:${L.password}`)));
    if (L.auth === "bearer") h.Authorization = "Bearer " + L.token;
    if (L.auth === "apikey") h["X-API-Key"] = "practice-key-123";
    return h;
  }

  async function sendRequest(L) {
    const started = performance.now();
    const res = await fetch(L.path, { method: L.method, headers: requestHeaders(L),
      body: ["GET", "DELETE"].includes(L.method) || !L.body ? undefined : L.body });
    const text = await res.text();
    const headers = {};
    res.headers.forEach((v, k) => { headers[k] = v; });
    let json = null;
    try { json = text ? JSON.parse(text) : null; } catch (_) { /* not JSON */ }
    L.last = { status: res.status, headers, text, json, ms: Math.round(performance.now() - started) };
    return L.last;
  }

  function showResponse(box, r, statuses) {
    const { el, fill } = ui();
    const cls = r.status < 300 ? "ok" : r.status < 400 ? "info" : r.status < 500 ? "warn" : "bad";
    const interesting = ["content-type", "location", "retry-after", "link", "x-total-count", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "www-authenticate"];
    fill(box,
      el("div", { class: "status-line " + cls }, el("strong", { text: String(r.status) }), el("span", { text: STATUS_TEXT[r.status] || "" }),
        el("span", { class: "spacer" }), el("span", { class: "muted small", text: `${r.ms} ms · ${r.text.length} bytes` })),
      statuses ? el("p", { class: "small", text: "Statuses in order: " + statuses.join(", ") }) : null,
      el("table", { class: "lab-headers" }, el("tbody", {}, Object.entries(r.headers).filter(([k]) => interesting.includes(k)).map(([k, v]) =>
        el("tr", {}, el("th", { text: k }), el("td", { class: "mono", text: v }))))),
      el("pre", { class: "lab-body", text: r.json ? JSON.stringify(r.json, null, 2) : r.text || "(no body)" }));
  }

  async function loadInbox(box) {
    const { el, fill } = ui();
    let data;
    try { data = await (await fetch("/practice/hooks")).json(); } catch (_) { return; }
    if (!data.inbox.length && !data.webhooks.length) {
      return fill(box, el("p", { class: "muted small", text: "No webhooks yet. Do step 15, then create a book (step 8)." }));
    }
    fill(box,
      data.webhooks.length ? el("p", { class: "small muted", text: `${data.webhooks.length} webhook(s) registered: ` + data.webhooks.map((w) => `${w.events.join(", ")} → ${w.url}`).join("; ") }) : null,
      data.inbox.length ? el("ul", { class: "inbox-list" }, data.inbox.map((m) => el("li", {},
        el("div", { class: "row small" }, el("strong", { text: m.event || "(no event header)" }), el("span", { class: "muted", text: `${m.at} → /practice/hooks/${m.name}` }),
          m.signature_valid === true ? el("span", { class: "badge safe", text: "signature valid" })
            : m.signature_valid === false ? el("span", { class: "badge danger", text: "signature INVALID" }) : el("span", { class: "badge", text: "unsigned" })),
        el("pre", { class: "lab-body small", text: m.body })))) : el("p", { class: "muted small", text: "Nothing received yet." }),
      data.deliveries.some((d) => d.error) ? el("p", { class: "small", text: "Failed deliveries: " + data.deliveries.filter((d) => d.error).map((d) => `${d.url} (${d.error})`).join("; ") }) : null);
  }

  // ------------------------------------------------------------------ code snippets for the current request
  function snippet(L) {
    const url = location.origin + L.path;
    const h = requestHeaders(L);
    const hasBody = !["GET", "DELETE"].includes(L.method) && L.body;
    const q = (s) => JSON.stringify(s);
    if (L.codeLang === "curl") {
      return [`curl -i -X ${L.method} ${q(url)}`, ...Object.entries(h).map(([k, v]) => `  -H ${q(`${k}: ${v}`)}`),
        hasBody ? `  --data ${"'" + L.body.replace(/'/g, "'\\''") + "'"}` : null].filter(Boolean).join(" \\\n");
    }
    if (L.codeLang === "python") {
      return ["import requests", "", `url = ${q(url)}`, `headers = ${JSON.stringify(h, null, 4)}`,
        hasBody ? `data = ${q(L.body)}` : null, "",
        `response = requests.request(${q(L.method)}, url, headers=headers${hasBody ? ", data=data" : ""}, timeout=10)`,
        "print(response.status_code, response.reason)",
        'print(response.headers.get("Content-Type"))',
        "print(response.text)"].filter((x) => x !== null).join("\n");
    }
    if (L.codeLang === "javascript" || L.codeLang === "typescript") {
      const ts = L.codeLang === "typescript";
      return [ts ? "const headers: Record<string, string> = " + JSON.stringify(h, null, 2) + ";" : "const headers = " + JSON.stringify(h, null, 2) + ";",
        "", `const response = await fetch(${q(url)}, {`, `  method: ${q(L.method)},`, "  headers,",
        hasBody ? `  body: ${q(L.body)},` : null, "  signal: AbortSignal.timeout(10000),", "});",
        `console.log(response.status, response.statusText);`,
        ts ? "const text: string = await response.text();" : "const text = await response.text();", "console.log(text);"].filter((x) => x !== null).join("\n");
    }
    return ["<?php", `$ch = curl_init(${q(url)});`, "curl_setopt_array($ch, [",
      `    CURLOPT_CUSTOMREQUEST => ${q(L.method)},`,
      "    CURLOPT_HTTPHEADER => [" + Object.entries(h).map(([k, v]) => q(`${k}: ${v}`)).join(", ") + "],",
      hasBody ? `    CURLOPT_POSTFIELDS => ${"'" + L.body.replace(/\\/g, "\\\\").replace(/'/g, "\\'") + "'"},` : null,
      "    CURLOPT_RETURNTRANSFER => true,", "    CURLOPT_TIMEOUT => 10,", "]);",
      "$body = curl_exec($ch);", "$status = curl_getinfo($ch, CURLINFO_RESPONSE_CODE);", "curl_close($ch);",
      'echo $status . "\\n" . $body;'].filter((x) => x !== null).join("\n");
  }

  // ------------------------------------------------------------------ chart helper: which chart fits my data?
  const SAMPLES = {
    "Monthly sales": "month,sales,expenses\n2026-01,120000,90000\n2026-02,135000,92000\n2026-03,128000,99000\n2026-04,151000,101000\n2026-05,166000,104000\n2026-06,159000,110000",
    "Bugs by module": "module,open_bugs\nlogin,4\ncheckout,11\nsearch,7\nprofile,2\nreports,5\nadmin,1",
    "Study hours vs score": "student,study_hours,quiz_score\nA,2,61\nB,4,70\nC,5,74\nD,7,83\nE,8,85\nF,3,64\nG,9,91\nH,6,77\nI,1,55\nJ,10,94",
    "Response times": "response_ms\n120\n135\n98\n240\n180\n150\n133\n410\n125\n160\n175\n142\n118\n205\n190\n130",
  };

  function renderCharts(body) {
    const { el, fill, askInChat } = ui();
    const C = window.JarvisCharts;
    const input = el("textarea", { class: "mono", rows: "9", "aria-label": "Your data (CSV)", placeholder: "Paste CSV or tab-separated data with a header row, e.g.\nmonth,sales\n2026-01,120000\n2026-02,135000" });
    input.value = S.chartData || SAMPLES["Monthly sales"];
    const file = el("input", { type: "file", accept: ".csv,.tsv,.txt,text/csv,text/plain", hidden: true, onchange: () => {
      const f = file.files[0];
      if (!f) return;
      const reader = new FileReader();  // read on this device; nothing is uploaded
      reader.onload = () => { input.value = String(reader.result).slice(0, 400000); analyse(); };
      reader.readAsText(f);
    } });
    const out = el("div", { class: "chart-suggestions" });
    function analyse() {
      S.chartData = input.value;
      const table = C.parseTable(input.value);
      if (!table) return fill(out, el("div", { class: "notice warn", text: "Add a header row and at least one row of data." }));
      const { columns, suggestions } = C.suggest(table);
      fill(out,
        el("div", { class: "card" }, el("h3", { text: `Your data: ${table.rows.length} row(s), ${columns.length} column(s)` }),
          el("table", { class: "profile-table" }, el("thead", {}, el("tr", {}, ["Column", "Looks like", "Different values"].map((t) => el("th", { text: t })))),
            el("tbody", {}, columns.map((c) => el("tr", {}, el("td", { text: c.name }), el("td", { text: c.type }), el("td", { text: String(c.distinct) })))))),
        suggestions.map((sug, i) => {
          const chart = el("div");
          const card = el("div", { class: "card" },
            el("div", { class: "row" }, el("span", { class: "badge" + (i === 0 ? " safe" : ""), text: i === 0 ? "Best fit" : "Also good" }), el("h3", { class: "grow", text: sug.title })),
            el("p", { class: "muted small", text: sug.why }), chart,
            sug.kind !== "info" && sug.kind !== "tiles" ? el("details", {}, el("summary", { text: "Make this chart in your own project" }),
              el("pre", { class: "lab-code", text: chartCode(sug, table) })) : null);
          setTimeout(() => C.draw(chart, table, sug), 0);
          return card;
        }),
        el("button", { onclick: () => askInChat(dataPrompt(table, columns), "explain", true) }, "Ask Jarvis what this data shows"));
    }
    fill(body,
      el("p", { class: "muted", text: "Paste a table (CSV) or open a file. Jarvis checks what kind of data each column holds and suggests the charts that fit, with a short reason and a preview. Your file is read on this device only." }),
      el("div", { class: "learn-grid charts-grid" },
        el("div", { class: "learn-side" },
          el("div", { class: "row wrap" }, Object.keys(SAMPLES).map((k) => el("button", { class: "small", onclick: () => { input.value = SAMPLES[k]; analyse(); } }, k))),
          input,
          el("div", { class: "row" }, el("button", { class: "primary", onclick: analyse }, "Suggest charts"),
            el("button", { onclick: () => file.click() }, "Open a CSV file"), file),
          el("div", { class: "card small" }, el("strong", { text: "Rules of thumb" }),
            el("ul", { class: "plain" },
              el("li", { text: "Trend over time → line chart" }),
              el("li", { text: "Compare categories → bar chart, sorted" }),
              el("li", { text: "Two numbers together → scatter plot" }),
              el("li", { text: "How values spread → histogram" }),
              el("li", { text: "One headline number → a stat tile, not a chart" }),
              el("li", { text: "Avoid pie charts for close values, and never use two y-axes" })))),
        out));
    analyse();
  }

  function dataPrompt(table, columns) {
    const sample = [table.header.join(","), ...table.rows.slice(0, 20).map((r) => r.join(","))].join("\n");
    return `Here is a table with ${table.rows.length} rows. Columns: ${columns.map((c) => `${c.name} (${c.type})`).join(", ")}.\n` +
      `First rows:\n\`\`\`csv\n${sample}\n\`\`\`\nWhat are the 3 most useful insights, which chart shows each best, and what should I check before trusting them?`;
  }

  function chartCode(sug, table) {
    const name = (i) => table.header[i];
    const cols = sug.columns.map(name);
    const kind = { line: "line", bars: "barh", scatter: "scatter", histogram: "hist" }[sug.kind];
    const py = ["import pandas as pd", "import matplotlib.pyplot as plt", "", 'df = pd.read_csv("data.csv")'];
    if (kind === "line") py.push(`df.plot(x=${JSON.stringify(cols[0])}, y=${JSON.stringify(cols.slice(1))}, kind="line")`);
    else if (kind === "barh") py.push(`df.groupby(${JSON.stringify(cols[0])})[${JSON.stringify(cols[1])}].sum().sort_values().plot(kind="barh")`);
    else if (kind === "scatter") py.push(`df.plot(x=${JSON.stringify(cols[0])}, y=${JSON.stringify(cols[1])}, kind="scatter")`);
    else py.push(`df[${JSON.stringify(cols[0])}].plot(kind="hist", bins=10)`);
    py.push(`plt.title(${JSON.stringify(sug.title.split(": ").pop())})`, "plt.tight_layout()", "plt.show()");
    const jsType = { line: "line", barh: "bar", scatter: "scatter", hist: "bar" }[kind];
    const js = ["// Chart.js (npm install chart.js) in a page with <canvas id=\"chart\"></canvas>",
      "import Chart from \"chart.js/auto\";", "", `const rows = await (await fetch("/api/data")).json(); // your data: [{ ${cols.map((c) => `${c}: ...`).join(", ")} }]`,
      `new Chart(document.getElementById("chart"), {`, `  type: "${jsType}",`,
      kind === "scatter" ? `  data: { datasets: [{ label: ${JSON.stringify(cols[1])}, data: rows.map((r) => ({ x: r.${cols[0]}, y: r.${cols[1]} })) }] },`
        : `  data: { labels: rows.map((r) => r.${cols[0]}), datasets: [${(kind === "line" ? cols.slice(1) : [cols[1] || cols[0]]).map((c) => `{ label: ${JSON.stringify(c)}, data: rows.map((r) => r.${c}) }`).join(", ")}] },`,
      kind === "barh" ? `  options: { indexAxis: "y" },` : null, "});"].filter(Boolean);
    return "# Python (pandas + matplotlib)\n" + py.join("\n") + "\n\n" + js.join("\n") +
      "\n\n// PHP / Laravel: send the rows as JSON from a controller (return response()->json($rows)) and draw them with Chart.js as above.";
  }

  function openTab(tab) {
    S.tab = tab;
    render();
  }

  window.JarvisLearn = { render, openGuide, snippet, sectionIds, openTab };
})();
