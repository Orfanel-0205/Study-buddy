/* Jarvis mobile app. It talks only to Jarvis: on your computer over your home Wi-Fi, or on this phone.
 * Plain JavaScript, no external libraries. The phone stores just its pairing token
 * and a few display preferences; chats and tasks stay on the computer. */
(function () {
  "use strict";

  const MD = window.JarvisMarkdown;
  const TOKEN_KEY = "jarvis.deviceToken";
  const PREFS_KEY = "jarvis.prefs";
  const CACHE_KEY = "jarvis.offlineCopy"; // tasks + device info, so the Tasks tab works offline
  const OUTBOX_KEY = "jarvis.outbox"; // task changes made offline, sent when the computer is back
  const IN_APP = /JarvisApp\//.test(navigator.userAgent); // running inside the Android app
  const STUDY_KEY = "jarvis.studyCopy"; // decks + upcoming cards, so reviews work offline
  const PACK_KEY = "jarvis.offlinePack"; // guides, the Build planner and verses, so they work offline (no personal data)
  let POCKET = location.host === "localhost:8766" || location.host === "127.0.0.1:8766"; // Jarvis on this phone (confirmed by /api/status)
  const placeName = () => (POCKET ? "This phone" : state.computer || "Computer");
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  // Inside the Android app, data is kept in the app's own storage, so the pairing and the offline
  // copies survive if the computer's network address changes (browser storage is tied to the address).
  // localStorage can be unavailable (private mode, blocked storage): never let that break the app.
  const NATIVE = window.JarvisNative && typeof window.JarvisNative.load === "function" ? window.JarvisNative : null;
  const store = {
    get(k) {
      if (NATIVE) {
        try { const v = NATIVE.load(k); if (v) return v; } catch (_) { /* fall back */ }
      }
      try { return localStorage.getItem(k); } catch (_) { return null; }
    },
    set(k, v) {
      if (NATIVE) { try { NATIVE.save(k, v); } catch (_) { /* ignore */ } }
      try { localStorage.setItem(k, v); } catch (_) { /* ignore */ }
    },
    del(k) {
      if (NATIVE) { try { NATIVE.remove(k); } catch (_) { /* ignore */ } }
      try { localStorage.removeItem(k); } catch (_) { /* ignore */ }
    },
  };
  // Jarvis on this phone, remembered from an earlier visit, so the app knows it even before it answers
  if (!POCKET && ["localhost", "127.0.0.1"].includes(location.hostname) && store.get("jarvis.pocket") === "1") POCKET = true;
  // One-time move: data saved in browser storage before the app had its own storage.
  if (NATIVE) {
    for (const key of ["jarvis.deviceToken", "jarvis.prefs", "jarvis.offlineCopy", "jarvis.outbox", "jarvis.studyCopy"]) {
      try {
        const old = localStorage.getItem(key);
        if (old && !NATIVE.load(key)) NATIVE.save(key, old);
      } catch (_) { /* nothing to move */ }
    }
  }

  function loadPrefs() {
    let p;
    try { p = Object.assign({ mode: "auto", detail: "concise", useProject: true }, JSON.parse(store.get(PREFS_KEY) || "{}")); }
    catch (_) { p = { mode: "auto", detail: "concise", useProject: true }; }
    if (!p.v16) { p.v16 = true; if (p.mode === "general") p.mode = "auto"; } // 1.6: Auto (picks the best mode) became the default
    return p;
  }

  const state = {
    token: store.get(TOKEN_KEY),
    device: null,
    computer: "",
    status: null,
    tab: "chat",
    conversationId: null,
    prefs: loadPrefs(),
    streaming: null,
    taskFilter: "open",
    tasks: [],
    online: true,
    studyView: "cards", // cards | guides | practice | lab
    guideId: null,
    guideAnchor: null,
    exerciseId: null,
  };
  const savePrefs = () => store.set(PREFS_KEY, JSON.stringify(state.prefs));

  // ------------------------------------------------------------------ helpers
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === undefined || v === null || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k === "html") node.innerHTML = v; // only used with escaped Markdown output or our own SVG
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v === true ? "" : v);
      }
    }
    for (const c of children.flat(Infinity)) {
      if (c === null || c === undefined || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }
  function fill(node, ...children) {
    node.replaceChildren(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
    return node;
  }

  const ICONS = {
    chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>',
    tasks: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3 8-8"/><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9"/></svg>',
    study: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 5a2 2 0 0 1 2-2h5a3 3 0 0 1 3 3v15a2 2 0 0 0-2-2H2z"/><path d="M22 5a2 2 0 0 0-2-2h-5a3 3 0 0 0-3 3v15a2 2 0 0 1 2-2h8z"/></svg>',
    spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>',
    camera: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13.5" r="3.5"/></svg>',
    more: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M8 12h.01M12 12h.01M16 12h.01"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
    stop: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>',
    history: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 5v14M5 12h14"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 12l5 5 9-10"/></svg>',
    sort: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h13M3 12h9M3 18h5M17 8v12M14 17l3 3 3-3"/></svg>',
    build: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/></svg>',
  };
  const icon = (name) => el("span", { html: ICONS[name], "aria-hidden": "true", style: "display:inline-flex" });

  function toast(message, kind, hint) {
    const box = el("div", { class: "toast " + (kind || ""), role: kind === "error" ? "alert" : "status" },
      el("div", { text: message }), hint ? el("div", { class: "hint", text: hint }) : null);
    $("#toasts").append(box);
    setTimeout(() => box.remove(), kind === "error" ? 9000 : 3500);
  }
  const showError = (err) => toast(err.message || String(err), "error", err.hint || "");

  // Grow a textarea to fit its text (fixed-height boxes cut text off on small screens).
  function autosize(ta, max) {
    const fit = () => { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight + 2, max || 220) + "px"; };
    ta.addEventListener("input", fit);
    requestAnimationFrame(fit);
    return ta;
  }

  function randomId() {
    return Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => b.toString(16).padStart(2, "0")).join("");
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {
      const ta = el("textarea", { style: "position:fixed;left:-9999px", readonly: true });
      ta.value = text;
      document.body.append(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    toast("Copied");
  }

  function fmtWhen(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }
  function dueInfo(due, done) {
    if (!due) return null;
    const [y, m, d] = due.split("-").map(Number);
    const date = new Date(y, m - 1, d);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const days = Math.round((date - today) / 86400000);
    const label = date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    if (done) return { text: "Due " + label, cls: "" };
    if (days < 0) return { text: "Overdue · " + label, cls: "overdue" };
    if (days === 0) return { text: "Due today", cls: "today" };
    if (days === 1) return { text: "Due tomorrow", cls: "" };
    return { text: "Due " + label, cls: "" };
  }

  function guessDeviceName() {
    const ua = navigator.userAgent || "";
    if (/iPhone/.test(ua)) return "iPhone";
    if (/iPad/.test(ua)) return "iPad";
    const m = ua.match(/Android [\d.]+; ([^;)]+)\)/);
    if (m && m[1] && m[1].trim() !== "K") return m[1].trim().slice(0, 40);
    if (/Android/.test(ua)) return "Android phone";
    return "Phone";
  }

  // ------------------------------------------------------------------ talking to the computer
  class Offline extends Error {}

  function apiError(status, data) {
    let msg = `Request failed (HTTP ${status})`;
    if (data && typeof data.detail === "string") msg = data.detail;
    else if (data && Array.isArray(data.detail)) msg = data.detail.map((d) => d.msg).join("; ");
    const err = new Error(msg);
    err.status = status;
    err.hint = (data && data.hint) || "";
    err.code = (data && data.code) || "";
    return err;
  }

  // A computer that is off, asleep, or behind a firewall often never answers at all, so
  // requests give up after a few seconds instead of hanging.
  const TIMEOUT_MS = 8000;

  async function api(path, opts) {
    opts = opts || {};
    const headers = {};
    if (state.token) headers.Authorization = "Bearer " + state.token;
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    const ctrl = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; ctrl.abort(); }, opts.timeout || TIMEOUT_MS);
    if (opts.signal) {
      if (opts.signal.aborted) ctrl.abort();
      else opts.signal.addEventListener("abort", () => ctrl.abort(), { once: true });
    }
    let res;
    try {
      res = await fetch(path, { method: opts.method || "GET", headers, signal: ctrl.signal, cache: "no-store",
        body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined });
    } catch (e) {
      if (e.name === "AbortError" && !timedOut) throw e; // stopped by the user
      const err = new Offline("Can't reach Jarvis on your computer.");
      err.hint = "Make sure Jarvis is running with phone access on, and that this phone is on the same Wi-Fi.";
      if (state.token) goOffline();
      throw err;
    } finally {
      clearTimeout(timer); // the computer answered: long answers may now stream as long as they need
    }
    if (opts.raw && res.ok) return res;
    let data = null;
    try { data = await res.json(); } catch (_) { /* empty */ }
    if (res.status === 401 && data && data.code === "unpaired" && state.token) {
      forgetPairing("This phone was removed from Jarvis on your computer. Pair it again to continue.");
    }
    if (!res.ok) throw apiError(res.status, data);
    return data;
  }

  // While the laptop's Jarvis is on screen, the app can still run practice checks on Jarvis on this phone
  // (Termux), so checking code never needs the laptop. The app allows only the practice-exercise calls.
  const pocketWaiting = {};
  window.__jarvisPocketDone = (id, status, text) => {
    const done = pocketWaiting[id];
    if (!done) return;
    delete pocketWaiting[id];
    let data = null;
    try { data = JSON.parse(text); } catch (_) { data = { detail: text }; }
    done(status, data);
  };
  const canCheckOnPhone = () => !POCKET && !!NATIVE && typeof NATIVE.pocketCall === "function" && (() => {
    try { return NATIVE.hasPocket(); } catch (_) { return false; }
  })();
  function pocketCall(method, path, body) {
    return new Promise((resolve, reject) => {
      const id = "p" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
      const timer = setTimeout(() => { delete pocketWaiting[id]; reject(new Error("Jarvis on this phone didn't answer in time.")); }, 150000);
      pocketWaiting[id] = (status, data) => {
        clearTimeout(timer);
        if (status >= 200 && status < 300) resolve(data); else reject(apiError(status, data));
      };
      NATIVE.pocketCall(method, path, body === undefined ? "" : JSON.stringify(body), id);
    });
  }

  let pack = null;
  function offlinePack() {
    if (!pack) { try { pack = JSON.parse(store.get(PACK_KEY) || "null"); } catch (_) { pack = null; } }
    return pack;
  }
  async function refreshOfflinePack() {
    const have = offlinePack();
    const version = state.status && state.status.app_version;
    if (have && have.version === version && Date.now() - (have.savedAt || 0) < 86400000) return;
    try {
      const fresh = await api("/api/offline/pack", { timeout: 20000 });
      fresh.savedAt = Date.now();
      store.set(PACK_KEY, JSON.stringify(fresh));
      pack = fresh;
    } catch (_) { /* next time */ }
  }

  function forgetPairing(message) {
    store.del(TOKEN_KEY);
    store.del(CACHE_KEY); // the offline copies go with the pairing
    store.del(STUDY_KEY);
    store.del(OUTBOX_KEY);
    state.token = null;
    state.device = null;
    state.tasks = [];
    if (state.streaming) state.streaming.controller.abort();
    renderPairing(message);
  }

  // ------------------------------------------------------------------ offline mode
  // When the computer can't be reached, the Tasks tab keeps working from a copy kept on
  // this phone. Changes wait in an outbox and are sent, in order, once the computer is back.
  function readJSON(key, fallback) {
    try { return JSON.parse(store.get(key) || "null") || fallback; } catch (_) { return fallback; }
  }
  function saveCache() {
    store.set(CACHE_KEY, JSON.stringify({ device: state.device, computer: state.computer, tasks: state.tasks, savedAt: Date.now() }));
  }
  const outbox = () => readJSON(OUTBOX_KEY, { ops: [], ids: {}, next: -1 });
  const saveOutbox = (box) => store.set(OUTBOX_KEY, JSON.stringify(box));

  let reconnectTimer = 0;
  let failedProbes = 0;
  let searched = false;
  function goOffline() {
    if (!state.online) return;
    state.online = false;
    failedProbes = 0;
    searched = false;
    renderBanner();
    scheduleReconnect();
  }
  function findComputer() {
    // The Android app can look for Jarvis on the Wi-Fi in case the computer got a new address.
    if (NATIVE && typeof NATIVE.findComputer === "function") {
      try { NATIVE.findComputer(); } catch (_) { /* not available */ }
    }
  }
  function scheduleReconnect(delay) {
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(async () => {
      try {
        await api("/api/phone/whoami", { timeout: 4000 });
        await goOnline();
      } catch (err) {
        if (!(err instanceof Offline)) return;
        failedProbes += 1;
        if (failedProbes === 2 && !searched) { searched = true; findComputer(); }
        scheduleReconnect();
      }
    }, delay === undefined ? 8000 : delay);
  }
  async function goOnline() {
    if (!$(".m-app")) { state.online = true; return start(); }
    state.online = true;
    failedProbes = 0;
    let sent = 0;
    try {
      sent = await syncOutbox();
    } catch (err) {
      if (err instanceof Offline) return;
    }
    if (sent) toast(`Back online · synced ${sent} change${sent === 1 ? "" : "s"} to your computer`);
    await refreshStatus();
    if (state.tab === "tasks") loadTasks();
    else if (state.tab === "chat") renderChat();
    else if (state.tab === "study") renderStudy();
    else renderMore();
  }

  async function syncOutbox() {
    const box = outbox();
    let sent = 0;
    while (box.ops.length) {
      try {
        await sendTaskChange(box.ops[0], box.ids);
      } catch (err) {
        if (err instanceof Offline) { saveOutbox(box); throw err; }
        // The computer refused it (for example the task was deleted there): skip this change.
      }
      box.ops.shift();
      sent += 1;
      saveOutbox(box);
    }
    store.del(OUTBOX_KEY);
    return sent;
  }

  function renderBanner() {
    const banner = $("#m-banner");
    if (!banner) return;
    if (!state.online) {
      const pending = outbox().ops.length;
      banner.hidden = false;
      const works = "Working offline: tasks" + (pending ? ` (${pending} change${pending === 1 ? "" : "s"} waiting to sync)` : "") +
        ", flashcard reviews, Study Buddy and focus sessions, check-ins, Build (plan, decide, numbers, hackathon)" +
        (offlinePack() ? ", the guides" : "") + ".";
      fill(banner, el("div", { class: "notice warn" }, el("strong", { text: POCKET ? "Jarvis on this phone isn't answering yet." : "Offline: can't reach your computer." }),
        el("div", { class: "small", text: works + (POCKET ? " It may still be starting; chat and code checking come back by themselves."
          : " Chat and AI need Jarvis; this app reconnects by itself.") }),
        IN_APP && NATIVE && !POCKET ? el("button", { type: "button", class: "ghost", style: "padding-left:0", onclick: findComputer }, "Search the Wi-Fi for my computer") : null));
      fill($("#m-sub"), el("span", { class: "dot bad" }), `${POCKET ? "This phone" : state.computer || "Computer"} · offline`);
      return;
    }
    const m = state.status && state.status.model;
    if (m && m.state !== "ready") {
      banner.hidden = false;
      fill(banner, el("div", { class: "notice warn" }, el("strong", { text: m.message }),
        el("div", { class: "small", text: m.hint + " (Do this on your computer.) Tasks still work." })));
    } else {
      banner.hidden = true;
    }
  }

  // ------------------------------------------------------------------ sheets (bottom panels)
  function openSheet({ title, body, actions, onClose }) {
    const foot = el("div", { class: "sheet-foot" });
    const sheet = el("div", { class: "sheet", role: "dialog", "aria-modal": "true", "aria-label": title },
      el("div", { class: "sheet-grab", "aria-hidden": "true" }),
      el("div", { class: "sheet-head" }, el("h3", { text: title }),
        el("button", { class: "ghost icon", "aria-label": "Close", onclick: () => close() }, "✕")),
      el("div", { class: "sheet-body" }, body));
    const backdrop = el("div", { class: "sheet-backdrop", onclick: (e) => { if (e.target === backdrop) close(); } }, sheet);
    let closed = false;
    function close() {
      if (closed) return;
      closed = true;
      backdrop.remove();
      document.removeEventListener("keydown", onKey);
      if (onClose) onClose();
    }
    function onKey(e) { if (e.key === "Escape") close(); }
    if (actions && actions.length) {
      sheet.append(foot);
      for (const a of actions) {
        const btn = el("button", { class: a.kind || "", type: "button" }, a.label);
        btn.addEventListener("click", async () => {
          if (!a.onClick) return close();
          const old = btn.textContent;
          btn.disabled = true;
          if (a.busy) btn.textContent = a.busy;
          try {
            if ((await a.onClick(close)) !== true) close();
          } catch (err) {
            showError(err);
          } finally {
            btn.disabled = false;
            btn.textContent = old;
          }
        });
        foot.append(btn);
      }
    }
    document.addEventListener("keydown", onKey);
    $("#sheet-root").append(backdrop);
    return { close };
  }

  function confirmSheet(title, message, confirmLabel) {
    return new Promise((resolve) => {
      let ok = false;
      openSheet({ title, body: el("p", { text: message }), onClose: () => resolve(ok), actions: [
        { label: "Cancel" },
        { label: confirmLabel, kind: "danger", onClick: () => { ok = true; } },
      ] });
    });
  }

  // ------------------------------------------------------------------ pairing
  function renderPairing(message) {
    const code = el("input", { type: "text", class: "code-input", inputmode: "numeric", pattern: "[0-9]*",
      maxlength: "6", autocomplete: "one-time-code", placeholder: "000000", "aria-label": "Pairing code" });
    const name = el("input", { type: "text", value: guessDeviceName(), maxlength: "60", "aria-label": "Name for this phone" });
    const err = el("div", { class: "notice bad", hidden: true, role: "alert" });
    const btn = el("button", { class: "primary block", type: "submit" }, "Pair this phone");
    async function pair(e) {
      e.preventDefault();
      const value = code.value.replace(/\D/g, "");
      if (value.length !== 6) { err.hidden = false; err.textContent = "Enter the 6-digit code shown on your computer."; return; }
      btn.disabled = true;
      btn.textContent = "Pairing…";
      err.hidden = true;
      try {
        const r = await api("/api/phone/pair", { method: "POST", body: { code: value, name: name.value.trim() || "Phone" } });
        store.set(TOKEN_KEY, r.token);
        state.token = r.token;
        toast(`Paired with ${r.computer}`);
        start();
      } catch (ex) {
        err.hidden = false;
        err.textContent = ex.message + (ex.hint ? " " + ex.hint : "");
      } finally {
        btn.disabled = false;
        btn.textContent = "Pair this phone";
      }
    }
    fill($("#app"), el("form", { class: "pair stack", onsubmit: pair },
      el("div", { class: "m-mark", "aria-hidden": "true" }, "J"),
      el("h2", { text: "Connect to Jarvis on your computer" }),
      message ? el("div", { class: "notice warn", text: message }) : null,
      el("ol", {},
        el("li", {}, "On your computer, open Jarvis → ", el("strong", { text: "Settings" }), " → ", el("strong", { text: "Phone access" }), "."),
        el("li", {}, "Click ", el("strong", { text: "Pair a phone" }), " and type the 6-digit code here.")),
      el("label", { class: "field" }, el("span", { text: "Pairing code" }), code),
      el("label", { class: "field" }, el("span", { text: "Name for this phone" }), name),
      err, btn,
      el("p", { class: "muted small", text: "Your phone connects only to your own computer over your Wi-Fi. Chats, tasks and code stay on the computer; nothing goes to the internet." })));
    code.addEventListener("input", () => { if (code.value.replace(/\D/g, "").length === 6) name.focus(); });
    code.focus();
  }

  function renderUnreachable(err) {
    fill($("#app"), el("div", { class: "pair stack" },
      el("div", { class: "m-mark", "aria-hidden": "true" }, "J"),
      el("h2", { text: "Can't reach your computer" }),
      el("p", { text: err.hint || err.message }),
      el("ul", { class: "small" },
        el("li", { text: "Is Jarvis running on your computer?" }),
        el("li", { text: "Is “Phone access” turned on in its Settings?" }),
        el("li", { text: "Is this phone on the same Wi-Fi as the computer?" }),
        el("li", { text: "Did the computer's network address change? Then open the new address shown in Jarvis's Settings and pair again." })),
      el("button", { class: "primary block", onclick: start }, "Try again"),
      IN_APP ? el("a", { class: "block", href: "jarvisapp:address", style: "display:block;text-align:center;margin-top:8px" }, "Change computer address") : null));
  }

  // ------------------------------------------------------------------ app shell
  function renderShell() {
    const T = (k, fallback) => (window.JarvisI18n ? window.JarvisI18n.t(k) : fallback);
    const tabs = [["chat", T("nav.chat", "Chat")], ["tasks", T("nav.tasks", "Tasks")], ["study", T("nav.study", "Study")],
      ["build", T("nav.build", "Build")], ["more", T("nav.more", "More")]];
    fill($("#app"), el("div", { class: "m-app" },
      el("header", { class: "m-top" },
        el("div", { class: "m-title" }, el("div", { class: "m-mark", "aria-hidden": "true" }, "J"),
          el("div", { style: "min-width:0" }, el("strong", { text: "Jarvis" }), el("small", { id: "m-sub" }, el("span", { class: "dot" }), "Connecting…"))),
        el("div", { class: "m-top-actions", id: "m-actions" })),
      el("div", { class: "m-banner", id: "m-banner", hidden: true }),
      el("main", { class: "m-main", id: "m-main" }),
      el("nav", { class: "m-tabs", "aria-label": "Sections" }, tabs.map(([id, label]) =>
        el("button", { "data-tab": id, "aria-current": state.tab === id ? "page" : "false", onclick: () => showTab(id) }, icon(id), label)))));
  }

  function showTab(tab) {
    state.tab = tab;
    for (const b of $$(".m-tabs button")) b.setAttribute("aria-current", b.dataset.tab === tab ? "page" : "false");
    document.body.classList.remove("composing");
    if (tab === "chat") renderChat();
    else if (tab === "tasks") renderTasks();
    else if (tab === "study") renderStudy();
    else if (tab === "build") renderBuild();
    else renderMore();
    companionContext();
  }

  function renderBuild() {
    setActions();
    const box = el("div", { class: "m-build" });
    fill($("#m-main"), el("div", { class: "m-scroll" }, box));
    if (!window.JarvisBuild) return fill(box, el("p", { class: "muted", text: "The Build page didn't load. Reload the app." }));
    window.JarvisBuild.render(box, { api, ask: (text, mode) => startChat(text, mode), toast: (t) => toast(t, "ok"), offline: offlinePack });
  }

  function companionContext() {
    if (!window.JarvisCompanion) return;
    const learning = state.tab === "study" && ["practice", "lab"].includes(state.studyView);
    window.JarvisCompanion.setContext({ view: learning ? "learn" : state.tab, tab: learning ? "practice" : state.studyView, mode: state.prefs.mode });
  }

  let companionMounted = false;
  function mountCompanion() {
    if (companionMounted || !window.JarvisCompanion) return;
    companionMounted = true;
    window.JarvisCompanion.mount({ api, store, place: "phone", native: NATIVE, offlineWords: () => (offlinePack() || {}).words, navigate(target, message) {
      if (target === "review") { state.studyView = "cards"; showTab("study"); }
      else if (target === "practice") { state.studyView = "practice"; showTab("study"); }
      else if (target === "progress") { showTab("more"); setTimeout(() => { const c = $("#m-progress"); if (c) c.scrollIntoView({ behavior: "smooth" }); }, 100); }
      else if (target === "toast") toast(message, "ok");
      else if (target === "coach") startChat(`My check-in today: ${message}\n\nHelp me plan a realistic study and coding session for how I feel right now.`, "coach");
      else showTab("chat");
    } });
    if (window.JarvisI18n) {
      const tellApp = (lang) => { if (NATIVE && typeof NATIVE.setLanguage === "function") { try { NATIVE.setLanguage(lang); } catch (_) { /* old app */ } } };
      tellApp(window.JarvisI18n.lang());
      window.JarvisI18n.onChange((lang) => { tellApp(lang); const tab = state.tab; renderShell(); showTab(tab); refreshStatus(); });
    }
  }

  function setActions(...buttons) { fill($("#m-actions"), buttons); }

  async function refreshStatus() {
    if (!state.token || !$("#m-sub")) return;
    if (!state.online) return renderBanner();
    try {
      state.status = await api("/api/status");
    } catch (err) {
      return renderBanner(); // offline: the banner explains
    }
    POCKET = POCKET || !!state.status.pocket;
    if (state.status.pocket && store.get("jarvis.pocket") !== "1") store.set("jarvis.pocket", "1");
    const m = state.status.model;
    const cls = m.state === "ready" ? "ok" : m.state === "not_running" || m.state === "blocked" ? "bad" : "warn";
    fill($("#m-sub"), el("span", { class: "dot " + cls }),
      `${placeName()} · ${m.state === "ready" ? m.model : "model not ready"}`);
    renderBanner();
    if (state.tab === "chat") renderComposerOptions();
  }

  // ------------------------------------------------------------------ chat
  const EXAMPLES = [
    ["explain", "Learn", "Explain what an API is, with a simple example."],
    ["tasks", "Plan", "Help me plan my week of study in small steps."],
    ["test", "Debug", "What does \"undefined is not a function\" mean in JavaScript?"],
    ["requirements", "Idea", "Turn this into requirements: an app to track my reading list."],
  ];

  function renderChat() {
    setActions(
      el("button", { class: "ghost icon", "aria-label": "Chat history", title: "History", onclick: openHistory }, icon("history")),
      el("button", { class: "ghost icon", "aria-label": "New chat", title: "New chat", onclick: newChat }, icon("plus")));
    const prompt = el("textarea", { id: "m-prompt", rows: "1", placeholder: "Message Jarvis", "aria-label": "Message", enterkeyhint: "enter" });
    prompt.addEventListener("input", () => { prompt.style.height = "auto"; prompt.style.height = Math.min(prompt.scrollHeight, 140) + "px"; });
    prompt.addEventListener("focus", () => document.body.classList.add("composing"));
    prompt.addEventListener("blur", () => setTimeout(() => document.body.classList.remove("composing"), 150));
    const sendBtn = el("button", { class: "primary", id: "m-send", type: "submit", "aria-label": "Send" }, icon("send"));
    const picker = el("input", { type: "file", accept: "image/*", multiple: true, hidden: true });
    picker.addEventListener("change", () => { addPictures([...picker.files]); picker.value = ""; });
    const photoBtn = el("button", { class: "ghost icon", type: "button", "aria-label": "Attach a photo", title: "Photo of notes, a page or a screenshot",
      onclick: () => picker.click() }, icon("camera"));
    const stopBtn = el("button", { class: "danger", id: "m-stop", type: "button", "aria-label": "Stop", hidden: true, onclick: stopStreaming }, icon("stop"));
    fill($("#m-main"), el("div", { class: "m-chat" },
      el("div", { class: "m-messages", id: "m-messages", "aria-live": "polite" }),
      el("form", { class: "m-composer", onsubmit: (e) => {
        e.preventDefault();
        const text = prompt.value.trim();
        if (!text || state.streaming) return;
        prompt.value = "";
        prompt.style.height = "auto";
        prompt.blur();
        sendMessage(text);
      } }, el("div", { class: "m-options", id: "m-options" }), el("div", { class: "thumbs", id: "m-pictures" }),
      el("div", { class: "m-input" }, photoBtn, picker, prompt, sendBtn, stopBtn))));
    renderPictures();
    renderComposerOptions();
    setBusy(!!state.streaming);
    if (!state.online) {
      sendBtn.disabled = true;
      fill($("#m-messages"), el("div", { class: "welcome" },
        el("div", { class: "m-mark", "aria-hidden": "true" }, "J"),
        el("h2", { text: "Chat needs your computer" }),
        el("p", { class: "muted small", text: "Answers come from the model running on your computer, which this phone can't reach right now. Your tasks still work offline." }),
        el("button", { type: "button", class: "block", onclick: () => showTab("tasks") }, "Go to tasks")));
      return;
    }
    if (state.conversationId) openConversation(state.conversationId, true);
    else renderWelcome();
  }

  function renderComposerOptions() {
    const box = $("#m-options");
    if (!box) return;
    const modes = (state.status && state.status.modes) || [{ id: "general", label: "General" }];
    const select = el("select", { "aria-label": "Mode" }, modes.map((m) => el("option", { value: m.id, selected: m.id === state.prefs.mode }, m.label)));
    select.addEventListener("change", () => { state.prefs.mode = select.value; savePrefs(); });
    const detailed = state.prefs.detail === "detailed";
    const project = state.status && state.status.project;
    fill(box, select,
      el("button", { type: "button", "aria-pressed": String(detailed), onclick: () => {
        state.prefs.detail = detailed ? "concise" : "detailed"; savePrefs(); renderComposerOptions();
      } }, detailed ? "Detailed" : "Concise"),
      project && project.open ? el("button", { type: "button", "aria-pressed": String(state.prefs.useProject), title: "Include relevant files from the project open on your computer", onclick: () => {
        state.prefs.useProject = !state.prefs.useProject; savePrefs(); renderComposerOptions();
      } }, "📁 " + project.name) : null);
  }

  function setBusy(busy) {
    const send = $("#m-send");
    const stop = $("#m-stop");
    if (send) send.hidden = busy;
    if (stop) stop.hidden = !busy;
  }

  function renderWelcome() {
    const box = $("#m-messages");
    if (!box) return;
    fill(box, el("div", { class: "welcome" },
      el("div", { class: "m-mark", "aria-hidden": "true" }, "J"),
      el("h2", { text: "Hi! What can I help with?" }),
      el("p", { class: "muted small", text: POCKET ? "Answers come from the model running on this phone \u2014 no laptop or internet needed."
        : "Answers come from the model running on your computer." }),
      el("div", { class: "examples" }, EXAMPLES.map(([mode, label, text]) => el("button", { type: "button", onclick: () => {
        state.prefs.mode = mode; savePrefs(); renderComposerOptions();
        const p = $("#m-prompt"); p.value = text; p.focus();
      } }, el("span", {}, el("b", { text: label }), text))))));
  }

  function scrollDown(force) {
    const box = $("#m-messages");
    if (box && (force || box.scrollHeight - box.scrollTop - box.clientHeight < 140)) box.scrollTop = box.scrollHeight;
  }

  function addUserMessage(text, pictures, storedNames) {
    const box = $("#m-messages");
    if ($(".welcome", box)) fill(box);
    const thumbs = el("div", { class: "thumbs" });
    for (const src of pictures || []) thumbs.append(window.JarvisImages.thumb(src));
    for (const name of storedNames || []) {
      const img = window.JarvisImages.thumb("");
      thumbs.append(img);
      window.JarvisImages.objectUrl(name, { Authorization: "Bearer " + state.token })
        .then((url) => { img.src = url; }).catch(() => img.remove());
    }
    box.append(el("div", { class: "msg user" },
      el("div", { class: "user-col" }, thumbs.childElementCount ? thumbs : null, el("div", { class: "bubble", text }))));
    scrollDown(true);
  }

  async function addPictures(files) {
    state.pictures = state.pictures || [];
    for (const file of files) {
      if (state.pictures.length >= 4) { toast("Up to 4 pictures per message.", "error"); break; }
      try { state.pictures.push(await window.JarvisImages.toDataUrl(file)); } catch (err) { showError(err); }
    }
    renderPictures();
  }

  function renderPictures() {
    const box = $("#m-pictures");
    if (!box) return;
    const list = state.pictures || [];
    fill(box, list.map((src, i) => el("span", { class: "thumb-wrap" }, window.JarvisImages.thumb(src),
      el("button", { class: "thumb-x", type: "button", "aria-label": "Remove picture", onclick: () => { list.splice(i, 1); renderPictures(); } }, "\u2715"))));
  }

  function addAssistantMessage() {
    const meta = el("div", { class: "meta" }, el("strong", { text: "Jarvis" }));
    const sources = el("div", { class: "sources", hidden: true });
    const thinking = el("details", { class: "thinking", hidden: true }, el("summary", { text: "Reasoning" }), el("pre"));
    const md = el("div", { class: "md" }, el("div", { class: "typing", "aria-label": "Jarvis is thinking" }, el("span"), el("span"), el("span")));
    const extra = el("div");
    const statusBox = el("div", { class: "muted small", hidden: true });
    const actions = el("div", { class: "msg-actions", hidden: true });
    $("#m-messages").append(el("div", { class: "msg assistant" }, meta, statusBox, sources, thinking, md, extra, actions));
    let content = "";
    let frame = 0;
    let thought = "";
    const paint = () => { frame = 0; md.innerHTML = MD.renderMarkdown(content); scrollDown(); };
    const decorate = () => {
      for (const block of $$(".codeblock", md)) {
        const bar = $(".codebar", block);
        if (bar.querySelector("button")) continue;
        bar.append(el("button", { class: "ghost", type: "button", onclick: () => copyText($("code", block).textContent) }, "Copy"));
      }
    };
    return {
      setContent(text) { content = text; if (!frame) frame = requestAnimationFrame(paint); },
      addStatus(text) { statusBox.hidden = false; statusBox.append(el("div", { text: "\u2022 " + text })); scrollDown(); },
      addThinking(text) { thought += text; thinking.hidden = false; $("pre", thinking).textContent = thought; },
      setSources(list) {
        if (!list || !list.length) return;
        sources.hidden = false;
        fill(sources, "Used:", list.map((s) => s.kind === "guide"
          ? el("button", { class: "chip", type: "button", title: "From Jarvis's built-in guides: tap to read it", onclick: () => {
            const [gid, anchor] = s.path.slice(6).split("#");
            state.studyView = "guides";
            state.guideId = gid;
            state.guideAnchor = anchor || null;
            showTab("study");
          } }, "📘 " + (s.title || s.path))
          : el("span", { class: "chip", text: s.path })));
      },
      finish({ model, stopped }) {
        if (frame) { cancelAnimationFrame(frame); frame = 0; }
        if (content) paint();
        else md.replaceChildren(el("p", { class: "muted", text: stopped ? "(Stopped before any answer was written.)" : "" }));
        if (stopped) meta.append(el("span", { class: "badge stopped", text: "stopped" }));
        if (model) meta.append(el("span", { text: model }));
        decorate();
        if (content) {
          actions.hidden = false;
          fill(actions,
            el("button", { class: "ghost", type: "button", onclick: () => copyText(content) }, "Copy"),
            el("button", { class: "ghost", type: "button", onclick: () => sendMessage("Please explain your previous answer in more detail, with examples and definitions of any technical terms.", "detailed") }, "More detail"));
        }
        scrollDown();
      },
      fail(message, hint) {
        if (frame) { cancelAnimationFrame(frame); frame = 0; }
        if (content) paint(); else md.replaceChildren();
        fill(extra, el("div", { class: "notice bad" }, el("strong", { text: message }), hint ? el("div", { class: "small", text: hint }) : null));
        decorate();
        scrollDown();
      },
    };
  }

  async function sendMessage(text, detail) {
    if (state.streaming) return toast("Jarvis is still answering. Tap stop first.", "error");
    if (!$("#m-messages")) showTab("chat");
    const pictures = detail === "detailed" ? [] : (state.pictures || []).splice(0);
    renderPictures();
    addUserMessage(text, pictures);
    const view = addAssistantMessage();
    const streamId = randomId();
    const controller = new AbortController();
    state.streaming = { streamId, controller };
    setBusy(true);
    const project = state.status && state.status.project;
    let content = "";
    let ended = false;
    function handle(ev) {
      if (ev.type === "meta") state.conversationId = ev.conversation_id;
      else if (ev.type === "sources") view.setSources(ev.sources);
      else if (ev.type === "status") view.addStatus(ev.text);
      else if (ev.type === "thinking") view.addThinking(ev.text);
      else if (ev.type === "content") { content += ev.text; view.setContent(content); }
      else if (ev.type === "done") { ended = true; view.finish({ model: ev.model }); }
      else if (ev.type === "stopped") { ended = true; view.finish({ stopped: true }); }
      else if (ev.type === "error") { ended = true; view.fail(ev.message, ev.hint); }
    }
    try {
      const res = await api("/api/chat", { method: "POST", raw: true, signal: controller.signal, body: {
        message: text, conversation_id: state.conversationId, mode: state.prefs.mode,
        detail: detail || state.prefs.detail, use_project: !!(project && project.open && state.prefs.useProject),
        stream_id: streamId, images: pictures, use_guides: GUIDE_MODES.includes(state.prefs.mode),
        lang: window.JarvisI18n ? window.JarvisI18n.lang() : "en",
        wellbeing: window.JarvisCompanion ? window.JarvisCompanion.wellbeing() : "",
      } });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, idx);
          buf = buf.slice(idx + 1);
          if (line.trim()) handle(JSON.parse(line));
        }
      }
      if (!ended) view.finish({ stopped: true });
    } catch (err) {
      if (err.name === "AbortError") { if (!ended) view.finish({ stopped: true }); }
      else view.fail(err.message, err.hint);
    } finally {
      state.streaming = null;
      setBusy(false);
    }
  }

  async function stopStreaming() {
    const s = state.streaming;
    if (!s) return;
    try { await api("/api/chat/cancel", { method: "POST", body: { stream_id: s.streamId } }); } catch (_) { /* ignore */ }
    setTimeout(() => { if (state.streaming === s) s.controller.abort(); }, 2500);
  }

  function newChat() {
    if (state.streaming) return toast("Wait for the answer to finish, or tap stop.", "error");
    state.conversationId = null;
    renderWelcome();
  }

  async function openConversation(id, quiet) {
    try {
      const data = await api(`/api/conversations/${id}`);
      state.conversationId = id;
      const box = $("#m-messages");
      if (!box) return;
      fill(box);
      for (const m of data.messages) {
        if (m.role === "user") addUserMessage(m.content, [], m.images);
        else {
          const v = addAssistantMessage();
          v.setSources(m.sources);
          v.setContent(m.content);
          v.finish({ model: m.model, stopped: m.stopped });
        }
      }
      scrollDown(true);
    } catch (err) {
      if (err.status === 404) { state.conversationId = null; renderWelcome(); }
      if (!quiet) showError(err);
    }
  }

  async function openHistory() {
    let list;
    try { list = await api("/api/conversations"); } catch (err) { return showError(err); }
    const body = el("div");
    const sheet = openSheet({ title: "Chats", body });
    function render() {
      fill(body, list.length ? list.map((c) => el("div", { class: "conv-item" + (c.id === state.conversationId ? " active" : "") },
        el("button", { class: "open", type: "button", onclick: () => {
          if (state.streaming) return toast("Wait for the answer to finish, or tap stop.", "error");
          sheet.close(); openConversation(c.id);
        } }, el("span", { class: "title", text: c.title }), el("span", { class: "when", text: fmtWhen(c.updated_at) })),
        el("button", { class: "ghost icon", type: "button", "aria-label": "Delete " + c.title, onclick: async () => {
          if (!(await confirmSheet("Delete this chat?", `“${c.title}” will be removed from your history.`, "Delete"))) return;
          try {
            await api(`/api/conversations/${c.id}`, { method: "DELETE" });
            list = list.filter((x) => x.id !== c.id);
            if (state.conversationId === c.id) newChat();
            render();
          } catch (err) { showError(err); }
        } }, "✕"))) : el("p", { class: "muted", text: "No chats yet." }));
    }
    render();
  }

  // ------------------------------------------------------------------ tasks
  const STATUSES = { todo: "To do", in_progress: "In progress", blocked: "Blocked", done: "Done" };
  const PRIORITIES = ["urgent", "high", "medium", "low"];

  async function renderTasks() {
    setActions(
      el("button", { class: "ghost", title: "Draft a stand-up note from your tasks", onclick: standupSheet }, "Stand-up"),
      el("button", { class: "ghost icon", "aria-label": "Suggest an order", title: "Suggest order (AI)", onclick: (e) => planTasks(e.currentTarget) }, icon("sort")));
    const list = el("ul", { class: "task-list", id: "m-task-list" });
    fill($("#m-main"),
      el("div", { class: "m-scroll" },
        el("div", { class: "row" },
          el("div", { class: "seg", role: "group", "aria-label": "Show" }, [["open", "Open"], ["done", "Done"]].map(([id, label]) =>
            el("button", { type: "button", "aria-pressed": String(state.taskFilter === id), onclick: () => { state.taskFilter = id; renderTasks(); } }, label)))),
        list),
      el("button", { class: "fab", "aria-label": "New task", onclick: () => openTaskSheet(null) }, "+"));
    await loadTasks();
  }

  async function loadTasks() {
    if (state.online) {
      try {
        state.tasks = await api("/api/tasks?include_done=true");
        for (const op of outbox().ops) applyLocally(op); // anything not synced yet stays visible
        saveCache();
      } catch (err) {
        if (!(err instanceof Offline)) return showError(err);
        state.tasks = readJSON(CACHE_KEY, {}).tasks || [];
      }
    } else {
      state.tasks = readJSON(CACHE_KEY, {}).tasks || [];
    }
    renderTaskList();
  }

  // Every task change goes through here: sent straight to the computer when it's reachable,
  // otherwise applied to the offline copy and queued.
  async function saveTaskChange(op) {
    if (op.kind !== "create") { applyLocally(op); renderTaskList(); } // instant feedback
    if (state.online) {
      try {
        await sendTaskChange(op, {});
        await loadTasks();
        return;
      } catch (err) {
        if (!(err instanceof Offline)) { await loadTasks(); throw err; }
      }
    }
    const box = outbox();
    if (op.kind === "create") {
      op.tempId = box.next;
      box.next -= 1;
    }
    applyLocally(op); // marks it "waiting to sync"
    box.ops.push(op);
    saveOutbox(box);
    saveCache();
    renderTaskList();
    renderBanner();
    toast("Saved on this phone. It will sync when your computer is reachable.");
  }

  async function sendTaskChange(op, ids) {
    if (op.kind === "review") { // a flashcard reviewed while offline keeps the day it was reviewed
      await api(`/api/study/cards/${op.id}/review`, { method: "POST", body: { grade: op.grade, reviewed_on: op.reviewed_on } });
      return;
    }
    const real = (id) => (id < 0 ? ids[id] : id); // tasks created offline have temporary negative ids
    if (op.kind === "create") {
      const body = Object.assign({}, op.body);
      if (body.parent_id && body.parent_id < 0) body.parent_id = real(body.parent_id) || null;
      const created = await api("/api/tasks", { method: "POST", body });
      if (op.tempId) ids[op.tempId] = created.id;
      return;
    }
    const id = real(op.id);
    if (!id) return; // created and then deleted while offline
    if (op.kind === "update") await api(`/api/tasks/${id}`, { method: "PATCH", body: op.changes });
    else await api(`/api/tasks/${id}`, { method: "DELETE" });
  }

  function applyLocally(op) {
    if (op.kind === "review") return; // flashcard reviews don't change the task list
    if (op.kind === "create") {
      if (state.tasks.some((t) => t.id === op.tempId)) return;
      state.tasks.push(Object.assign({ description: "", due_date: null, priority: "medium", status: "todo",
        project: "", notes: "", parent_id: null, position: 9999 }, op.body,
        { id: op.tempId, created_at: new Date().toISOString(), pending: true }));
    } else if (op.kind === "update") {
      const t = state.tasks.find((x) => x.id === op.id);
      if (t) Object.assign(t, op.changes, { pending: !state.online || t.pending });
    } else {
      state.tasks = state.tasks.filter((t) => t.id !== op.id && t.parent_id !== op.id);
    }
  }

  function needsComputer() {
    if (state.online) return false;
    toast("That uses the AI on your computer, which isn't reachable right now.", "error");
    return true;
  }

  function renderTaskList() {
    const ul = $("#m-task-list");
    if (!ul) return;
    const byId = new Map(state.tasks.map((t) => [t.id, t]));
    const children = {};
    for (const t of state.tasks) if (t.parent_id && byId.has(t.parent_id)) (children[t.parent_id] = children[t.parent_id] || []).push(t);
    for (const k in children) children[k].sort((a, b) => a.position - b.position);
    const wantDone = state.taskFilter === "done";
    const top = state.tasks.filter((t) => (!t.parent_id || !byId.has(t.parent_id)) && (t.status === "done") === wantDone);
    if (!top.length) {
      fill(ul, el("li", { class: "empty", text: wantDone ? "No completed tasks yet." : "Nothing to do. Tap + to add a task." }));
      return;
    }
    fill(ul, top.map((t) => taskCard(t, children[t.id] || [])));
  }

  function checkButton(t) {
    const done = t.status === "done";
    return el("button", { class: "check", role: "checkbox", "aria-checked": String(done), "aria-label": (done ? "Mark not done: " : "Mark done: ") + t.title,
      onclick: () => updateTask(t.id, { status: done ? "todo" : "done" }) }, done ? icon("check") : null);
  }

  function taskCard(t, subs) {
    const done = t.status === "done";
    const due = dueInfo(t.due_date, done);
    const finished = subs.filter((s) => s.status === "done").length;
    return el("li", { class: "task" + (done ? " done" : "") },
      el("div", { class: "task-row" }, checkButton(t),
        el("button", { class: "task-open", type: "button", onclick: () => openTaskSheet(t) },
          el("div", { class: "task-title", text: t.title }),
          el("div", { class: "task-meta" },
            t.priority !== "medium" ? el("span", { class: "badge " + t.priority, text: t.priority }) : null,
            t.status === "in_progress" || t.status === "blocked" ? el("span", { class: "badge " + t.status, text: STATUSES[t.status] }) : null,
            due ? el("span", { class: "due " + due.cls, text: due.text }) : null,
            subs.length ? el("span", { text: `${finished}/${subs.length} steps` }) : null,
            t.project ? el("span", { text: "📁 " + t.project }) : null,
            t.pending ? el("span", { class: "badge", text: "waiting to sync" }) : null))),
      subs.length ? el("ul", { class: "subs" }, subs.map((s) => el("li", { class: "sub" + (s.status === "done" ? " done" : "") },
        checkButton(s), el("button", { class: "task-open", type: "button", onclick: () => openTaskSheet(s) }, el("span", { class: "task-title", text: s.title }))))) : null);
  }

  async function updateTask(id, changes) {
    try { await saveTaskChange({ kind: "update", id, changes }); } catch (err) { showError(err); }
  }

  async function openTaskSheet(task) {
    const t = task || { title: "", description: "", due_date: "", priority: "medium", status: "todo", project: "", notes: "", area: "" };
    const f = {
      title: el("input", { type: "text", value: t.title, maxlength: "300", placeholder: "What needs doing?" }),
      description: el("textarea", { rows: "3", placeholder: "Details (optional)" }),
      due_date: el("input", { type: "date", value: t.due_date || "" }),
      priority: el("select", {}, PRIORITIES.map((p) => el("option", { value: p, selected: p === t.priority }, p[0].toUpperCase() + p.slice(1)))),
      status: el("select", {}, Object.entries(STATUSES).map(([k, v]) => el("option", { value: k, selected: k === t.status }, v))),
      project: el("input", { type: "text", value: t.project || "", placeholder: "Optional label" }),
      area: el("select", {}, [["", "Not set"], ["study", "Studying"], ["dev", "Developing"]].map(([v, l]) => el("option", { value: v, selected: v === (t.area || "") }, l))),
      notes: el("textarea", { rows: "3", placeholder: "Notes (optional)" }),
    };
    f.description.value = t.description || "";
    f.notes.value = t.notes || "";
    autosize(f.description);
    autosize(f.notes);
    const body = el("div", { class: "stack" },
      el("label", { class: "field" }, el("span", { text: "Title" }), f.title),
      el("label", { class: "field" }, el("span", { text: "Description" }), f.description),
      el("div", { class: "grid2" },
        el("label", { class: "field" }, el("span", { text: "Due" }), f.due_date),
        el("label", { class: "field" }, el("span", { text: "Priority" }), f.priority),
        el("label", { class: "field" }, el("span", { text: "Status" }), f.status),
        el("label", { class: "field" }, el("span", { text: "Project" }), f.project),
        el("label", { class: "field" }, el("span", { text: "Area" }), f.area)),
      el("label", { class: "field" }, el("span", { text: "Notes" }), f.notes),
      task && !task.parent_id && task.id > 0 && state.online ? el("button", { type: "button", class: "block", onclick: (e) => breakDown(task, e.currentTarget, sheet) }, "✨ Break into steps with AI") : null,
      task ? el("button", { type: "button", class: "block ghost", style: "color:var(--danger)", onclick: async () => {
        if (!(await confirmSheet("Delete task?", `“${task.title}” and its steps will be deleted.`, "Delete"))) return;
        try { await saveTaskChange({ kind: "delete", id: task.id }); sheet.close(); } catch (err) { showError(err); }
      } }, "Delete task") : null);
    const sheet = openSheet({ title: task ? "Edit task" : "New task", body, actions: [
      { label: "Cancel" },
      { label: task ? "Save" : "Add", kind: "primary", onClick: async () => {
        const data = { title: f.title.value.trim(), description: f.description.value, due_date: f.due_date.value || null,
          priority: f.priority.value, status: f.status.value, project: f.project.value.trim(), notes: f.notes.value,
          area: f.area.value || (f.project.value.trim() ? "dev" : "") };
        if (!data.title) { toast("Give the task a title.", "error"); return true; }
        await saveTaskChange(task ? { kind: "update", id: task.id, changes: data } : { kind: "create", body: data });
      } },
    ] });
    if (!task) f.title.focus();
  }

  async function breakDown(task, btn, parentSheet) {
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Thinking… (this can take a moment)";
    let result;
    try {
      result = await api(`/api/tasks/${task.id}/breakdown`, { method: "POST", timeout: 600000 });
    } catch (err) {
      showError(err);
      return;
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
    parentSheet.close();
    const rows = result.steps.map((s) => ({
      check: el("input", { type: "checkbox", checked: true, "aria-label": "Include step" }),
      title: el("input", { type: "text", value: s.title }),
      desc: autosize(el("textarea", { rows: "2" }, s.description)),
    }));
    openSheet({ title: "Suggested steps", body: el("div", { class: "stack" },
      el("p", { class: "muted small", text: "In a practical order. Edit or untick any before adding." }),
      result.notes ? el("div", { class: "notice info", text: result.notes }) : null,
      el("ol", { class: "steps" }, rows.map((r) => el("li", {}, r.check, el("div", { class: "grow" }, r.title, r.desc))))),
    actions: [
      { label: "Cancel" },
      { label: "Add steps", kind: "primary", onClick: async () => {
        const steps = rows.filter((r) => r.check.checked && r.title.value.trim()).map((r) => ({ title: r.title.value.trim(), description: r.desc.value }));
        if (!steps.length) { toast("Pick at least one step.", "error"); return true; }
        await api(`/api/tasks/${task.id}/subtasks`, { method: "POST", body: { steps } });
        toast(`Added ${steps.length} steps`);
        loadTasks();
      } },
    ] });
  }

  async function planTasks(btn) {
    if (needsComputer()) return;
    btn.disabled = true;
    toast("Asking Jarvis for a suggested order…");
    try {
      const plan = await api("/api/tasks/plan", { method: "POST", timeout: 600000 });
      openSheet({ title: "Suggested order", body: el("div", { class: "plan" },
        plan.advice ? el("p", { text: plan.advice }) : null,
        plan.order.length ? el("ol", {}, plan.order.map((o) => el("li", {}, el("strong", { text: o.title }), o.reason ? el("div", { class: "muted small", text: o.reason }) : null)))
          : el("p", { class: "muted", text: "No open tasks." }),
        el("p", { class: "muted small", text: "Just a suggestion; your tasks aren't changed." })) });
    } catch (err) {
      showError(err);
    } finally {
      btn.disabled = false;
    }
  }

  // ------------------------------------------------------------------ study (flashcards)
  let reviewSession = null;
  const todayISO = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };

  async function loadStudy() {
    if (state.online) {
      try {
        const [decks, upcoming] = await Promise.all([api("/api/study/decks"), api("/api/study/due?within_days=14")]);
        const reviewed = new Set(outbox().ops.filter((o) => o.kind === "review").map((o) => o.id));
        const copy = { decks, cards: upcoming.filter((c) => !reviewed.has(c.id)) };
        store.set(STUDY_KEY, JSON.stringify(copy));
        return copy;
      } catch (err) {
        if (!(err instanceof Offline)) showError(err);
      }
    }
    return readJSON(STUDY_KEY, { decks: [], cards: [] });
  }

  function dueNow(copy, deckId) {
    const today = todayISO();
    return copy.cards.filter((c) => c.due <= today && (deckId == null || c.deck_id === deckId));
  }

  async function renderStudy() {
    if (reviewSession) return renderReview();
    if (state.studyView === "guides") return renderGuidesM();
    if (state.studyView === "practice") return renderPracticeM();
    if (state.studyView === "lab" && POCKET) return renderLabM();
    setActions(
      el("button", { class: "ghost icon", "aria-label": "Make flashcards with AI", title: "Make flashcards with AI", onclick: () => makeCardsSheet(null) }, icon("spark")),
      el("button", { class: "ghost icon", "aria-label": "New deck", title: "New deck", onclick: () => newDeckSheet() }, icon("plus")));
    const box = el("div", { class: "m-scroll" }, el("p", { class: "muted", text: "Loading\u2026" }));
    fill($("#m-main"), box);
    const copy = await loadStudy();
    const due = dueNow(copy, null).length;
    fill(box, studySeg(),
      el("div", { class: "card" },
        el("h3", { text: due ? `${due} card${due === 1 ? "" : "s"} to review` : copy.decks.length ? "All caught up for today" : "Start studying" }),
        el("p", { class: "muted small", text: "Each card comes back just before you'd forget it. A few minutes a day is enough. Reviews work offline too." }),
        due ? el("button", { class: "primary block", onclick: () => startReview(null) }, "Review now") : null),
      copy.decks.length ? el("div", { style: "margin-top:12px" }, copy.decks.map((d) => {
        const n = dueNow(copy, d.id).length;
        return el("button", { class: "deck-item", type: "button", onclick: () => deckSheet(d, copy) },
          el("div", { class: "grow" }, el("div", { class: "task-title", text: d.name }),
            el("div", { class: "task-meta" }, `${d.cards} card${d.cards === 1 ? "" : "s"}`,
              n ? el("span", { class: "badge high", text: `${n} due` }) : el("span", { class: "badge low", text: "done for today" }))),
          el("span", { class: "muted", text: "\u203A" }));
      })) : el("div", { class: "empty", text: "No decks yet. Tap \u2728 to make flashcards from your notes or a photo of a page, or + to make a deck yourself." }),
      el("button", { class: "block", style: "margin-top:12px", onclick: starterSheet }, "+ Starter decks: DevNet, HTTP codes, Git\u2026"),
      el("p", { class: "muted small", style: "margin-top:14px", text: "Tip: in Chat, choose \u201cStudy companion\u201d for explanations, hints and quizzes, and send a photo of your notes with \uD83D\uDCF7." }));
  }

  // ------------------------------------------------------------------ learn: guides, practice, API Lab, stand-up
  // chat modes that use Jarvis's built-in guides (in Auto only when a guide really answers the question)
  const GUIDE_MODES = ["auto", "study", "explain", "coach", "rules", "business", "stack", "hackathon"];
  const LANG_LABEL = { python: "Python", javascript: "JavaScript", typescript: "TypeScript", php: "PHP" };
  const slug = (t) => String(t).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

  function studySeg() {
    const views = [["cards", "Cards"], ["guides", "Guides"], ["practice", "Practice"]];
    if (POCKET) views.push(["lab", "API Lab"]);
    return el("div", { class: "seg study-seg", role: "tablist", "aria-label": "Study sections" }, views.map(([id, label]) =>
      el("button", { type: "button", role: "tab", "aria-pressed": String(state.studyView === id),
        onclick: () => { state.studyView = id; renderStudy(); } }, label)));
  }

  function learnBox() {
    const box = el("div", { class: "m-scroll" }, studySeg(), el("p", { class: "muted", text: "Loading\u2026" }));
    fill($("#m-main"), box);
    return box;
  }

  function offlineCard(box, what) {
    fill(box, studySeg(), el("div", { class: "notice warn", style: "margin-top:12px", text: `${what} need${what.endsWith("s") ? "" : "s"} Jarvis to be reachable. Flashcard reviews` +
      (offlinePack() ? " and the guides" : "") + " still work offline." }));
  }

  async function startChat(text, mode) {
    state.prefs.mode = mode;
    savePrefs();
    showTab("chat");
    sendMessage(text);
  }

  async function renderGuidesM() {
    setActions();
    const box = learnBox();
    if (state.guideId) return showGuideM(box);
    let guides;
    const saved = offlinePack();
    try { guides = await api("/api/learn/guides"); } catch (_) {
      if (!saved) return offlineCard(box, "The guides");
      guides = saved.guides; // no connection: the copy saved on this phone
    }
    const search = el("input", { type: "search", placeholder: "Search: 401 vs 403, merge conflict, N+1\u2026", "aria-label": "Search the guides" });
    const hits = el("div", { class: "stack" });
    let timer = 0;
    search.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const q = search.value.trim();
        if (!q) return fill(hits);
        let found;
        try { found = await api("/api/learn/search?q=" + encodeURIComponent(q)); } catch (_) {
          found = saved ? searchSaved(saved.guides, q) : []; // offline: a simple search of the saved guides
        }
        fill(hits, found.length ? found.map((h) => el("button", { class: "deck-item", onclick: () => openGuideM(h.guide, h.anchor) },
          el("div", { class: "grow" }, el("div", { class: "task-title", text: h.section }), el("div", { class: "muted small", text: h.guide_title })))) :
          el("p", { class: "muted small", text: "Nothing found." }));
      }, 300);
    });
    fill(box, studySeg(), el("div", { style: "margin:12px 0" }, search), hits,
      guides.map((g) => el("button", { class: "deck-item", onclick: () => openGuideM(g.id) },
        el("div", { class: "grow" }, el("div", { class: "task-title", text: g.title }), el("div", { class: "muted small", text: g.summary })),
        el("span", { class: "muted", text: "\u203A" }))));
  }

  /** Offline search: sections of the saved guides that contain every word you typed. */
  function searchSaved(guides, q) {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    const out = [];
    for (const g of guides) {
      let topic = "";
      for (const part of g.markdown.split(/\n(?=#{2,3} )/)) {
        const m = part.match(/^(#{2,3}) (.+)/);
        if (!m) continue;
        if (m[1] === "##") topic = m[2];
        const anchor = slug(m[1] === "##" ? m[2] : `${topic} \u203a ${m[2]}`);
        if (words.every((w) => part.toLowerCase().includes(w))) out.push({ guide: g.id, guide_title: g.title, section: m[2], anchor });
        if (out.length >= 8) return out;
      }
    }
    return out;
  }

  function openGuideM(id, anchor) {
    state.guideId = id;
    state.guideAnchor = anchor || null;
    renderGuidesM();
  }

  async function showGuideM(box) {
    setActions(el("button", { class: "ghost", onclick: () => { state.guideId = null; renderGuidesM(); } }, "\u2039 Guides"));
    let g;
    try { g = await api("/api/learn/guides/" + encodeURIComponent(state.guideId)); } catch (_) {
      const saved = offlinePack();
      g = saved && saved.guides.find((x) => x.id === state.guideId);
      if (!g) return offlineCard(box, "The guides");
    }
    const content = el("div", { class: "md guide-body", html: MD.renderMarkdown(g.markdown) });
    let topic = ""; // the renderer shifts headings down a level: "## Topic" is an h3, "### Sub" an h4
    for (const h of content.querySelectorAll("h3, h4")) {
      if (h.tagName === "H3") { topic = h.textContent; h.id = slug(topic); }
      else h.id = slug(topic ? `${topic} \u203a ${h.textContent}` : h.textContent);
    }
    fill(box, studySeg(),
      el("div", { class: "grid2", style: "margin:12px 0" },
        el("button", { class: "primary", onclick: () => startChat(`Quiz me on the guide "${g.title}". Ask one question at a time and wait for my answer.`, "study") }, "Quiz me"),
        el("button", { onclick: starterSheet }, "Flashcards")),
      content);
    const anchor = state.guideAnchor;
    state.guideAnchor = null;
    if (anchor) {
      const target = content.querySelector("#" + CSS.escape(anchor)) || [...content.querySelectorAll("h3, h4")].find((h) => h.id.startsWith(anchor));
      if (target) setTimeout(() => target.scrollIntoView({ block: "start" }), 50);
    }
  }

  async function starterSheet() {
    const list = el("div", { class: "stack" }, el("p", { class: "muted small", text: "Loading\u2026" }));
    openSheet({ title: "Starter decks", body: el("div", { class: "stack" },
      el("p", { class: "muted small", text: "Ready-made flashcards from Jarvis's guides. Adding a deck on the laptop and on this phone is safe: they stay one deck when they sync." }),
      list) });
    const draw = async () => {
      let decks;
      try { decks = await api("/api/learn/decks"); } catch (_) { return fill(list, el("p", { class: "muted", text: "Needs Jarvis to be reachable." })); }
      fill(list, decks.map((d) => el("div", { class: "card-line" },
        el("div", { class: "grow" }, el("div", { class: "task-title", text: d.name }),
          el("div", { class: "muted small", text: `${d.cards} cards \u00b7 ${d.description}` })),
        el("button", { class: d.installed && !d.missing ? "ghost" : "primary", disabled: d.installed && !d.missing, onclick: async (e) => {
          e.currentTarget.disabled = true;
          try {
            const r = await api(`/api/learn/decks/${d.key}/install`, { method: "POST" });
            toast(r.added ? `Added ${r.added} card(s)` : "Already up to date", "ok");
            state.studyCopy = null;
            draw();
            if (state.tab === "study" && state.studyView === "cards") renderStudy();
          } catch (err) { showError(err); }
        } }, d.installed ? (d.missing ? "Update" : "Added") : "Add"))));
    };
    draw();
  }

  async function renderPracticeM() {
    setActions();
    const box = learnBox();
    if (state.exerciseId) return showExerciseM(box);
    let data;
    try { data = await api("/api/learn/exercises"); } catch (_) { return offlineCard(box, "Practice exercises"); }
    const solved = data.exercises.filter((e) => e.solved).length;
    const groups = Object.keys(LANG_LABEL).map((lang) => [lang, data.exercises.filter((e) => e.language === lang)]);
    fill(box, studySeg(),
      el("div", { class: "card", style: "margin-top:12px" },
        el("h3", { text: `${solved} of ${data.exercises.length} solved` }),
        el("p", { class: "muted small", text: data.can_run
          ? "Write the code, then Check runs the tests on " + (POCKET ? "this phone." : "this device.")
          : canCheckOnPhone()
            ? "You're connected to the laptop's Jarvis, but Check runs your code on this phone (Jarvis in Termux), so the laptop isn't needed for checking. (Code from a phone never runs on the laptop.)"
            : "You're connected to the laptop's Jarvis: read the exercises here, and check your code on the laptop (code never runs on the laptop from a phone). Jarvis on this phone can run it." }),
        el("div", { class: "row wrap" }, Object.values(data.runtimes).map((r) => el("span", { class: "badge " + (r.available ? "low" : "high"), text: `${r.label} ${r.available ? "\u2713" : "\u2717"}` })))),
      groups.map(([lang, items]) => items.length ? el("div", { style: "margin-top:12px" },
        el("h4", { class: "muted", text: LANG_LABEL[lang] }),
        items.map((e) => el("button", { class: "deck-item", onclick: () => { state.exerciseId = e.id; renderPracticeM(); } },
          el("div", { class: "grow" }, el("div", { class: "task-title", text: e.title }), el("div", { class: "muted small", text: `${e.topic} \u00b7 ${e.level}` })),
          e.solved ? el("span", { class: "badge low", text: "\u2713" }) : el("span", { class: "muted", text: "\u203A" })))) : null));
  }

  async function showExerciseM(box) {
    setActions(el("button", { class: "ghost", onclick: () => { state.exerciseId = null; renderPracticeM(); } }, "\u2039 Exercises"));
    let ex, listing;
    try {
      [ex, listing] = await Promise.all([api("/api/learn/exercises/" + state.exerciseId), api("/api/learn/exercises")]);
    } catch (_) { return offlineCard(box, "Practice exercises"); }
    const runtime = listing.runtimes[ex.language];
    const onPhone = !listing.can_run && canCheckOnPhone(); // run the check on this phone's Jarvis instead
    const canRun = (listing.can_run && runtime.available) || onPhone;
    const editor = el("textarea", { class: "code-editor", spellcheck: "false", autocapitalize: "off", autocomplete: "off", rows: "14", "aria-label": "Your code" });
    editor.value = ex.code;
    let saveTimer = 0;
    editor.addEventListener("input", () => {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(() => api(`/api/learn/exercises/${ex.id}/code`, { method: "PUT", body: { code: editor.value } }).catch(() => {}), 800);
    });
    const results = el("div", { class: "stack" });
    const hints = el("div", { class: "notice info", hidden: true });
    let hintIndex = 0;
    let lastResults = [];
    const check = el("button", { class: "primary", disabled: !canRun, onclick: async () => {
      check.disabled = true;
      check.textContent = "Checking\u2026";
      try {
        const r = onPhone
          ? await pocketCall("POST", `/api/learn/exercises/${ex.id}/run`, { code: editor.value })
          : await api(`/api/learn/exercises/${ex.id}/run`, { method: "POST", body: { code: editor.value }, timeout: 60000 });
        lastResults = r.results;
        fill(results,
          el("div", { class: "notice " + (r.ok ? "ok" : "bad"), text: r.problem || (r.ok ? `All ${r.total} tests pass \u2713` : `${r.passed} of ${r.total} tests pass`) }),
          r.results.map((t) => el("div", { class: "test-line " + (t.ok ? "ok" : "bad") },
            el("strong", { text: (t.ok ? "\u2713 " : "\u2717 ") + t.name }), t.detail ? el("pre", { text: t.detail }) : null)),
          r.output ? el("pre", { class: "out", text: "Output:\n" + r.output }) : null,
          r.errors ? el("pre", { class: "out", text: r.errors }) : null);
        if (r.ok) toast("All tests pass. Well done!", "ok");
        if (window.JarvisCompanion) window.JarvisCompanion.react(r.ok ? "tests_passed" : "tests_failed");
      } catch (err) { showError(err); }
      check.disabled = false;
      check.textContent = "Check";
    } }, "Check");
    fill(box, studySeg(),
      el("div", { class: "card", style: "margin-top:12px" },
        el("div", { class: "row wrap" }, el("span", { class: "badge", text: LANG_LABEL[ex.language] }), el("span", { class: "badge", text: ex.topic }),
          ex.solved ? el("span", { class: "badge low", text: "solved \u2713" }) : null),
        el("h3", { text: ex.title }),
        el("div", { class: "md", html: MD.renderMarkdown(ex.task) })),
      onPhone ? el("div", { class: "notice info", text: "Check runs on this phone (Jarvis in Termux). The first check can take up to a minute while it starts." })
        : !listing.can_run ? el("div", { class: "notice warn", text: "Checking your code needs Jarvis on the laptop's screen, or Jarvis on this phone." })
        : !runtime.available ? el("div", { class: "notice warn", text: `${runtime.label} isn't installed here. ${runtime.install}` }) : null,
      editor,
      el("div", { class: "grid3" }, check,
        el("button", { onclick: async () => {
          hints.hidden = false;
          if (hintIndex < ex.hints.length) { hints.append(el("p", { text: `Hint ${hintIndex + 1}: ${ex.hints[hintIndex]}` })); hintIndex += 1; return; }
          const wait = el("p", { class: "muted small", text: "Asking Jarvis\u2026" });
          hints.append(wait);
          try {
            const r = await api(`/api/learn/exercises/${ex.id}/hint`, { method: "POST", body: { code: editor.value, results: lastResults }, timeout: 180000 });
            wait.replaceWith(el("div", { class: "md", html: MD.renderMarkdown("**Jarvis:** " + r.hint) }));
          } catch (err) { wait.remove(); showError(err); }
        } }, "Hint"),
        el("button", { onclick: async () => {
          if (!(await confirmSheet("Show the solution?", "Try a hint first \u2014 you learn more by solving it.", "Show it"))) return;
          try {
            const sol = await api(`/api/learn/exercises/${ex.id}/solution`);
            openSheet({ title: "Reference solution", body: el("pre", { class: "out", text: sol.solution }) });
          } catch (err) { showError(err); }
        } }, "Solution")),
      hints, results);
  }

  // The API Lab on the phone: only with Jarvis running on this phone (the laptop never offers it to the network).
  const LAB = "/practice/api/v1";
  const LAB_STEPS = [
    ["No credentials", "401", "GET", `${LAB}/books`, "none"],
    ["API key + pagination headers", "200", "GET", `${LAB}/books?page=2&per_page=5`, "key"],
    ["Log in (Basic) \u2192 token", "200", "POST", `${LAB}/auth/login`, "basic:learner:devnet123"],
    ["Read with the Bearer token", "200", "GET", `${LAB}/books/4`, "bearer:learner"],
    ["Read-only user creates a book", "403", "POST", `${LAB}/books`, "bearer:viewer", '{"title": "No", "author": "Viewer"}'],
    ["Wrong Content-Type", "415", "POST", `${LAB}/books`, "bearer:learner", "title=Hello", "text/plain"],
    ["Missing field", "400", "POST", `${LAB}/books`, "bearer:learner", '{"author": "Me"}'],
    ["Create a book", "201", "POST", `${LAB}/books`, "bearer:learner", () => JSON.stringify({ title: "Phone notes", author: "Me", isbn: "p-" + Date.now() })],
    ["Duplicate isbn", "409", "POST", `${LAB}/books`, "bearer:learner", '{"title": "Clean Code", "author": "R. C. Martin", "isbn": "978-0132350884"}'],
    ["Unknown book", "404", "GET", `${LAB}/books/9999`, "key"],
    ["Rate limit (12 quick requests)", "429", "GET", `${LAB}/books`, "basic:viewer:viewer123", null, null, 12],
    ["Asynchronous job", "202", "POST", `${LAB}/reports`, "bearer:learner"],
    ["Flaky service (try 3 times)", "503\u2192200", "GET", `${LAB}/flaky`, "key"],
  ];
  const labTokens = {};

  async function labAuth(spec) {
    const [kind, user, pw] = String(spec).split(":");
    if (kind === "key") return { "X-API-Key": "practice-key-123" };
    if (kind === "basic") return { Authorization: "Basic " + btoa(`${user}:${pw}`) };
    if (kind === "bearer") {
      if (!labTokens[user]) {
        const r = await fetch(`${LAB}/auth/login`, { method: "POST", headers: { Authorization: "Basic " + btoa(`${user}:${user === "viewer" ? "viewer123" : "devnet123"}`) } });
        labTokens[user] = (await r.json().catch(() => ({}))).token || "";
      }
      return { Authorization: "Bearer " + labTokens[user] };
    }
    return {};
  }

  async function renderLabM() {
    setActions(el("button", { class: "ghost", onclick: async () => { await fetch("/practice/lab/reset", { method: "POST" }); for (const k of Object.keys(labTokens)) delete labTokens[k]; toast("Practice data reset", "ok"); } }, "Reset"));
    const box = learnBox();
    const out = el("div", { class: "stack", "aria-live": "polite" });
    fill(box, studySeg(),
      el("div", { class: "card", style: "margin-top:12px" },
        el("h3", { text: "API Lab" }),
        el("p", { class: "muted small", text: "A practice REST API inside Jarvis on this phone: learner / devnet123 (read + write), viewer / viewer123 (read only), X-API-Key practice-key-123. Tap a step, look at the status and headers. The full lab with code examples is on the laptop." })),
      LAB_STEPS.map(([title, expect, method, path, auth, body, ctype, times]) => el("button", { class: "deck-item", onclick: async () => {
        try {
          const headers = await labAuth(auth);
          const payload = typeof body === "function" ? body() : body;
          if (payload) headers["Content-Type"] = ctype || "application/json";
          const statuses = [];
          let res, text = "";
          for (let i = 0; i < (times || 1); i++) {
            res = await fetch(path, { method, headers, body: payload || undefined });
            text = await res.text();
            statuses.push(res.status);
          }
          const shown = ["location", "retry-after", "x-total-count", "x-ratelimit-remaining", "link", "content-type"].filter((h) => res.headers.get(h))
            .map((h) => `${h}: ${res.headers.get(h)}`).join("\n");
          let pretty = text;
          try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch (_) { /* not JSON */ }
          fill(out, el("div", { class: "notice " + (res.status < 300 ? "ok" : res.status < 500 ? "warn" : "bad") },
            el("strong", { text: `${method} ${path}` }), el("div", { text: `\u2192 ${statuses.join(", ")}  (expected ${expect})` })),
            shown ? el("pre", { class: "out", text: shown }) : null, el("pre", { class: "out", text: pretty.slice(0, 3000) }));
          out.scrollIntoView({ behavior: "smooth", block: "start" });
        } catch (err) { showError(err); }
      } }, el("div", { class: "grow" }, el("div", { class: "task-title", text: title }), el("div", { class: "muted small", text: `${method} \u00b7 expect ${expect}` })))),
      out);
  }

  async function standupSheet() {
    let note;
    try { note = await api("/api/learn/standup"); } catch (err) { return showError(err); }
    const box = el("textarea", { rows: "12", class: "code-editor", "aria-label": "Stand-up note" });
    box.value = note.text;
    openSheet({ title: "Stand-up note", body: el("div", { class: "stack" },
      el("p", { class: "muted small", text: "Drafted from your tasks. Edit it, then copy it into your team chat." }), box),
      actions: [{ label: "Close" }, { label: "Copy", kind: "primary", onClick: async () => {
        try { await navigator.clipboard.writeText(box.value); } catch (_) { box.select(); document.execCommand("copy"); }
        toast("Copied", "ok");
        return true;
      } }] });
  }

  function newDeckSheet(after) {
    if (needsComputer()) return;
    const name = el("input", { type: "text", maxlength: "120", placeholder: "e.g. Biology \u2013 cells" });
    openSheet({ title: "New deck", body: el("label", { class: "field" }, el("span", { text: "Name" }), name), actions: [
      { label: "Cancel" },
      { label: "Create", kind: "primary", onClick: async () => {
        if (!name.value.trim()) { toast("Give the deck a name.", "error"); return true; }
        const deck = await api("/api/study/decks", { method: "POST", body: { name: name.value.trim(), description: "" } });
        if (after) after(deck); else renderStudy();
      } },
    ] });
    name.focus();
  }

  async function deckSheet(deck, copy) {
    const due = dueNow(copy, deck.id).length;
    const list = el("div", { class: "stack" }, el("p", { class: "muted small", text: state.online ? "Loading cards\u2026" : "The card list needs your computer. Reviews still work offline." }));
    const sheet = openSheet({ title: deck.name, body: el("div", { class: "stack" },
      due ? el("button", { class: "primary block", onclick: () => { sheet.close(); startReview(deck); } }, `Review ${due} due card${due === 1 ? "" : "s"}`) : el("p", { class: "muted small", text: "Nothing due in this deck today." }),
      el("div", { class: "grid2" },
        el("button", { onclick: () => { if (needsComputer()) return; sheet.close(); addCardSheet(deck); } }, "+ Add a card"),
        el("button", { onclick: () => { if (needsComputer()) return; sheet.close(); makeCardsSheet(deck); } }, "\u2728 Make with AI")),
      list,
      el("button", { class: "block ghost", style: "color:var(--danger)", onclick: async () => {
        if (needsComputer()) return;
        if (!(await confirmSheet("Delete deck?", `\u201C${deck.name}\u201D and its ${deck.cards} card(s) will be deleted.`, "Delete"))) return;
        try { await api(`/api/study/decks/${deck.id}`, { method: "DELETE" }); sheet.close(); renderStudy(); } catch (err) { showError(err); }
      } }, "Delete deck")) });
    if (!state.online) return;
    try {
      const cards = await api(`/api/study/decks/${deck.id}/cards`);
      fill(list, cards.length ? cards.map((c) => el("div", { class: "card-line" },
        el("div", { class: "grow" }, el("div", { class: "task-title", text: c.front }), el("div", { class: "muted small", text: c.back })),
        el("button", { class: "ghost icon", "aria-label": "Delete card", onclick: async (e) => {
          try { await api(`/api/study/cards/${c.id}`, { method: "DELETE" }); e.currentTarget.closest(".card-line").remove(); } catch (err) { showError(err); }
        } }, "\u2715"))) : el("p", { class: "muted small", text: "No cards yet." }));
    } catch (err) { fill(list, el("p", { class: "muted small", text: err.message })); }
  }

  function addCardSheet(deck) {
    const front = el("textarea", { rows: "2", placeholder: "Question or term" });
    const back = el("textarea", { rows: "3", placeholder: "Answer" });
    openSheet({ title: "Add a card to " + deck.name, body: el("div", { class: "stack" },
      el("label", { class: "field" }, el("span", { text: "Front" }), front), el("label", { class: "field" }, el("span", { text: "Back" }), back)),
    actions: [{ label: "Cancel" }, { label: "Add", kind: "primary", onClick: async () => {
      if (!front.value.trim() || !back.value.trim()) { toast("Fill in both sides.", "error"); return true; }
      await api(`/api/study/decks/${deck.id}/cards`, { method: "POST", body: { cards: [{ front: front.value, back: back.value }] } });
      toast("Card added");
      renderStudy();
    } }] });
    front.focus();
  }

  function makeCardsSheet(deck) {
    if (needsComputer()) return;
    const pictures = [];
    const notes = autosize(el("textarea", { rows: "4", placeholder: "Paste notes or vocabulary (optional if you add a photo)" }));
    const thumbs = el("div", { class: "thumbs" });
    const picker = el("input", { type: "file", accept: "image/*", multiple: true, hidden: true });
    const count = el("select", {}, [5, 10, 15, 20].map((n) => el("option", { value: n, selected: n === 10 }, `${n} cards`)));
    const showThumbs = () => fill(thumbs, pictures.map((src, i) => el("span", { class: "thumb-wrap" }, window.JarvisImages.thumb(src),
      el("button", { class: "thumb-x", type: "button", "aria-label": "Remove", onclick: () => { pictures.splice(i, 1); showThumbs(); } }, "\u2715"))));
    picker.addEventListener("change", async () => {
      for (const f of [...picker.files]) {
        if (pictures.length >= 4) break;
        try { pictures.push(await window.JarvisImages.toDataUrl(f)); } catch (err) { showError(err); }
      }
      picker.value = "";
      showThumbs();
    });
    openSheet({ title: deck ? `Make cards for ${deck.name}` : "Make flashcards with AI", body: el("div", { class: "stack" },
      el("button", { type: "button", class: "block", onclick: () => picker.click() }, icon("camera"), "Take or choose photos of your notes"), picker, thumbs,
      el("label", { class: "field" }, el("span", { text: "Notes" }), notes),
      el("label", { class: "field" }, el("span", { text: "How many" }), count),
      el("p", { class: "muted small", text: "Jarvis reads the photo first, then writes the cards. You can check them before saving." })),
    actions: [{ label: "Cancel" }, { label: "Make cards", kind: "primary", busy: "Working\u2026", onClick: async () => {
      if (!notes.value.trim() && !pictures.length) { toast("Add a photo or some notes first.", "error"); return true; }
      const result = await api("/api/study/generate", { method: "POST", timeout: 600000,
        body: { text: notes.value, images: pictures, count: parseInt(count.value, 10) } });
      reviewGenerated(result, deck);
    } }] });
  }

  function reviewGenerated(result, deck) {
    const rows = result.cards.map((c) => ({ check: el("input", { type: "checkbox", checked: true, "aria-label": "Keep card" }),
      front: el("input", { type: "text", value: c.front }), back: autosize(el("textarea", { rows: "2" }, c.back)) }));
    const name = el("input", { type: "text", value: result.title || "New deck", maxlength: "120" });
    openSheet({ title: "Check the cards", body: el("div", { class: "stack" },
      result.transcript ? el("details", {}, el("summary", { class: "small", text: "Text read from the photo" }), el("pre", { class: "small transcript", text: result.transcript })) : null,
      deck ? null : el("label", { class: "field" }, el("span", { text: "New deck name" }), name),
      el("p", { class: "muted small", text: "Small models can make mistakes: edit or untick any card." }),
      el("ol", { class: "steps" }, rows.map((r) => el("li", {}, r.check, el("div", { class: "grow" }, r.front, r.back))))),
    actions: [{ label: "Cancel" }, { label: "Save", kind: "primary", onClick: async () => {
      const cards = rows.filter((r) => r.check.checked && r.front.value.trim() && r.back.value.trim())
        .map((r) => ({ front: r.front.value.trim(), back: r.back.value.trim() }));
      if (!cards.length) { toast("Keep at least one card.", "error"); return true; }
      const target = deck || await api("/api/study/decks", { method: "POST", body: { name: name.value.trim() || "New deck", description: "" } });
      await api(`/api/study/decks/${target.id}/cards`, { method: "POST", body: { cards } });
      toast(`Saved ${cards.length} card${cards.length === 1 ? "" : "s"}`);
      renderStudy();
    } }] });
  }

  async function startReview(deck) {
    const copy = await loadStudy();
    const cards = dueNow(copy, deck ? deck.id : null);
    if (!cards.length) return toast("Nothing to review right now.");
    reviewSession = { deck, queue: cards, index: 0, shown: false, done: 0, again: {} };
    renderReview();
  }

  function renderReview() {
    const r = reviewSession;
    setActions(el("button", { class: "ghost", onclick: () => { reviewSession = null; renderStudy(); } }, "End"));
    if (r.index >= r.queue.length) {
      fill($("#m-main"), el("div", { class: "m-scroll" }, el("div", { class: "flashcard" },
        el("div", { class: "flash-front", text: "\uD83C\uDF89 Done!" }),
        el("p", { class: "muted", text: `You reviewed ${r.done} card${r.done === 1 ? "" : "s"}.` + (state.online ? "" : " They'll sync when your computer is reachable.") }),
        el("button", { class: "primary block", onclick: () => { reviewSession = null; renderStudy(); } }, "Back to decks"))));
      return;
    }
    const card = r.queue[r.index];
    const next = card.next || {};
    const days = (n) => (n === undefined ? "" : n <= 1 ? "1 day" : `${n} days`);
    fill($("#m-main"), el("div", { class: "m-scroll" },
      el("div", { class: "row small muted" }, el("span", { text: r.deck ? r.deck.name : "All decks" }), el("span", { class: "grow" }),
        el("span", { text: `${r.index + 1} / ${r.queue.length}` })),
      el("div", { class: "progress" }, el("div", { style: `width:${Math.round((100 * r.index) / r.queue.length)}%` })),
      el("button", { class: "flashcard", type: "button", "aria-label": r.shown ? "Answer shown" : "Show answer",
        onclick: () => { if (!r.shown) { r.shown = true; renderReview(); } } },
        el("div", { class: "flash-front", text: card.front }),
        r.shown ? el("div", { class: "flash-back", text: card.back }) : el("div", { class: "muted small", text: "Tap to show the answer" })),
      r.shown ? el("div", { class: "grades" },
        gradeButton("again", "Again", "forgot"), gradeButton("hard", "Hard", days(next.hard)),
        gradeButton("good", "Good", days(next.good)), gradeButton("easy", "Easy", days(next.easy))) : null));
  }

  function gradeButton(grade, label, hint) {
    return el("button", { class: "grade " + grade, type: "button", onclick: () => gradeCard(grade) }, el("strong", { text: label }), el("small", { text: hint }));
  }

  async function gradeCard(grade) {
    const r = reviewSession;
    const card = r.queue[r.index];
    const op = { kind: "review", id: card.id, grade, reviewed_on: todayISO() };
    let sent = false;
    if (state.online) {
      try { await sendTaskChange(op, {}); sent = true; } catch (err) { if (!(err instanceof Offline)) return showError(err); }
    }
    if (!sent) { const box = outbox(); box.ops.push(op); saveOutbox(box); renderBanner(); }
    const copy = readJSON(STUDY_KEY, { decks: [], cards: [] }); // take it out of today's offline list
    copy.cards = copy.cards.filter((c) => c.id !== card.id);
    store.set(STUDY_KEY, JSON.stringify(copy));
    r.done += 1;
    if (grade === "again" && (r.again[card.id] || 0) < 3) {
      r.again[card.id] = (r.again[card.id] || 0) + 1;
      r.queue.push(Object.assign({}, card, { next: null }));
    }
    r.index += 1;
    r.shown = false;
    renderReview();
  }

  // ------------------------------------------------------------------ progress (studying vs developing)
  let progressView = { tab: "study", days: 30 };
  async function loadProgress(card) {
    const C = window.JarvisCharts;
    let p;
    try { p = await api(`/api/progress?days=${progressView.days}`); } catch (_) {
      return fill(card, el("h3", { text: "Your progress" }), el("p", { class: "muted small", text: "Couldn't load your progress." }));
    }
    const seg = el("div", { class: "seg study-seg" }, [["study", "Studying"], ["dev", "Developing"]].map(([id, label]) =>
      el("button", { type: "button", "aria-pressed": String(progressView.tab === id), onclick: () => { progressView.tab = id; loadProgress(card); } }, label)));
    const range = el("select", { "aria-label": "Time range", onchange: (e) => { progressView.days = Number(e.target.value); loadProgress(card); } },
      [[7, "Last 7 days"], [30, "Last 30 days"], [90, "Last 90 days"]].map(([v, t]) => el("option", { value: v, selected: progressView.days === v }, t)));
    const tiles = el("div"), chart = el("div", { style: "margin-top:12px" }), bars = el("div", { style: "margin-top:12px" });
    fill(card, el("h3", { text: "Your progress" }), seg, el("div", { style: "margin:10px 0" }, range), tiles, chart, bars);
    if (progressView.tab === "study") {
      const st = p.study;
      C.tiles(tiles, [
        { label: "Study streak", value: `${st.streak} day${st.streak === 1 ? "" : "s"}` },
        { label: "Cards reviewed", value: String(st.reviews_week), note: "last 7 days" },
        { label: "Retention", value: st.retention === null ? "\u2013" : `${st.retention}%` },
        { label: "Exercises solved", value: `${st.exercises.solved} / ${st.exercises.total}` },
      ]);
      C.columns(chart, { title: "Study activity per day", data: st.daily.map((d) => ({ label: d.date, values: d })), height: 160,
        series: [{ key: "reviews", label: "Flashcard reviews", slot: 0 }, { key: "practice", label: "Practice checks", slot: 1 }, { key: "questions", label: "Study questions", slot: 2 }],
        empty: "No study activity in this period yet." });
      C.hbars(bars, { title: "Practice solved by language", rows: st.exercises.by_language.map((l) => ({ label: LANG_LABEL[l.language] || l.language, value: l.solved, max: l.total })),
        format: (r) => `${r.value} of ${r.max}`, valueLabel: "Solved" });
    } else {
      const dv = p.dev;
      const runs = dv.test_runs.passed + dv.test_runs.failed;
      C.tiles(tiles, [
        { label: "Coding streak", value: `${dv.streak} day${dv.streak === 1 ? "" : "s"}` },
        { label: "Tasks finished", value: String(dv.tasks_week), note: "last 7 days" },
        { label: "Tests passed", value: runs ? `${dv.test_runs.passed} / ${runs}` : "\u2013" },
        { label: "Open dev tasks", value: String(dv.open_tasks) },
      ]);
      C.columns(chart, { title: "Development activity per day", data: dv.daily.map((d) => ({ label: d.date, values: d })), height: 160,
        series: [{ key: "tasks", label: "Tasks finished", slot: 0 }, { key: "changes", label: "Code changes", slot: 1 }, { key: "runs", label: "Test and build runs", slot: 2 }],
        empty: "No development activity in this period yet." });
      bars.replaceChildren();
    }
  }

  // ------------------------------------------------------------------ laptop or this phone
  function whereCard() {
    const mode = NATIVE && typeof NATIVE.mode === "function" ? NATIVE.mode() : "auto";
    const option = (value, label) => el("a", { href: "jarvisapp:use-" + value, class: "mode-option" + (mode === value ? " active" : "") }, label);
    const sync = el("p", { class: "small muted", text: POCKET ? "Checking sync\u2026" : "" });
    if (POCKET) loadSyncStatus(sync);
    return el("div", { class: "card" }, el("h3", { text: "Where Jarvis runs" }),
      el("p", { class: "small", text: POCKET
        ? "Now: on this phone. Answers come from the small model on the phone; your tasks and flashcards sync with the laptop when it's reachable."
        : "Now: on your laptop (bigger models). If the laptop isn't reachable, the app switches to Jarvis on this phone." }),
      el("div", { class: "mode-row" }, option("auto", "Automatic"), option("laptop", "Laptop"), option("phone", "This phone")),
      sync);
  }

  async function loadSyncStatus(box) {
    let st;
    try { st = await api("/api/sync/status"); } catch (_) { box.textContent = ""; return; }
    if (!st.enabled) { box.textContent = "Not set up to sync with the laptop."; return; }
    const when = st.last_ok ? fmtWhen(st.last_ok) : "not yet";
    fill(box, `Last synced with the laptop: ${when}.`, st.last_error ? el("div", { text: "Last try: " + st.last_error.slice(0, 120) }) : null,
      el("button", { class: "ghost", style: "padding-left:0", onclick: async (e) => {
        e.currentTarget.disabled = true;
        try {
          const r = await api("/api/sync/now", { method: "POST", timeout: 60000 });
          const got = r.received;
          toast(`Synced: ${got.tasks} task(s), ${got.cards} card(s) updated`);
        } catch (err) { showError(err); }
        loadSyncStatus(box);
      } }, "Sync now"));
  }

  // ------------------------------------------------------------------ more
  function renderMore() {
    setActions();
    const st = state.status;
    const m = st && st.model;
    const isIOS = /iPhone|iPad/.test(navigator.userAgent);
    const progressCard = el("div", { class: "card", id: "m-progress" }, el("h3", { text: "Your progress" }), el("p", { class: "muted small", text: "Loading\u2026" }));
    if (state.online) loadProgress(progressCard); else fill(progressCard, el("h3", { text: "Your progress" }), el("p", { class: "muted small", text: "Needs Jarvis to be reachable." }));
    fill($("#m-main"), el("div", { class: "m-scroll" },
      IN_APP ? whereCard() : null,
      progressCard,
      window.JarvisCompanion ? el("div", { class: "card" }, el("h3", { text: window.JarvisI18n ? window.JarvisI18n.t("set.title") : "Study Buddy" }),
        el("p", { class: "muted small", text: "Study Buddy, the check-in before you start, focus sessions, floating over other apps, and the Bible verse or quote when you open the app. Saved on this phone." }),
        window.JarvisCompanion.settingsCard()) : null,
      el("div", { class: "card" }, el("h3", { text: "Connection" }),
        el("dl", { class: "kv" },
          el("dt", { text: POCKET ? "Running on" : "Computer" }), el("dd", { text: placeName() + (state.online ? "" : " (offline)") }),
          el("dt", { text: "Address" }), el("dd", { text: location.host }),
          el("dt", { text: "Model" }), el("dd", { text: !state.online ? "not reachable" : m ? m.message : "unknown" }),
          el("dt", { text: "Project" }), el("dd", { text: st && st.project.open ? st.project.name : "none open" }),
          el("dt", { text: "Version" }), el("dd", { text: st ? st.app_version : "" })),
        state.online && m && m.state !== "ready" ? el("p", { class: "small muted", style: "margin-top:8px", text: m.hint }) : null,
        IN_APP ? el("a", { href: "jarvisapp:address", style: "display:block;margin-top:10px" }, "Change computer address") : null,
        IN_APP && NATIVE ? el("button", { class: "ghost", style: "padding-left:0", onclick: findComputer }, "Search the Wi-Fi for my computer") : null),
      el("div", { class: "card" }, el("h3", { text: "This phone" }),
        el("dl", { class: "kv" },
          el("dt", { text: "Name" }), el("dd", { text: state.device ? state.device.name : "" }),
          el("dt", { text: "Paired" }), el("dd", { text: state.device ? fmtWhen(state.device.created_at) : "" })),
        el("button", { class: "block", style: "margin-top:12px", onclick: async () => {
          if (!(await confirmSheet("Unpair this phone?", "You'll need a new code from your computer to connect again.", "Unpair"))) return;
          try { await api("/api/phone/unpair", { method: "POST" }); } catch (_) { /* forget locally anyway */ }
          forgetPairing("This phone is no longer paired.");
        } }, "Unpair this phone")),
      IN_APP ? null : el("div", { class: "card" }, el("h3", { text: "Add to your home screen" }),
        el("p", { class: "small", text: isIOS
          ? "In Safari, tap the Share button, then “Add to Home Screen”. Jarvis then opens full screen like an app."
          : "In Chrome, open the ⋮ menu and tap “Add to Home screen” (or “Install app”). Jarvis then opens like an app." })),
      el("div", { class: "card" }, el("h3", { text: "Privacy & security" }),
        el("ul", { class: "small", style: "padding-left:20px;margin:0" },
          el("li", { text: "Your phone talks only to Jarvis on your computer, over your Wi-Fi. Nothing is sent to the internet." }),
          el("li", { text: IN_APP
            ? "The connection is encrypted, and this app only trusts the certificate made by Jarvis on your computer."
            : "The connection is encrypted with a certificate your computer made itself, which is why the browser warned you the first time." }),
          el("li", { text: "Chats stay on the computer. A copy of your tasks is kept on this phone so they work offline; unpairing deletes it." }),
          el("li", { text: "For safety, file changes and commands can only be approved on the computer." })),
        IN_APP ? null : el("p", { class: "small muted", style: "margin-top:10px", text: "Optional: to stop the certificate warning, install Jarvis's certificate on this phone (Android: Settings → Security → Install a certificate → CA certificate. iPhone: open it, then Settings → General → VPN & Device Management, and enable it under About → Certificate Trust Settings)." }),
        IN_APP ? null : el("a", { href: "/m/jarvis-ca.crt", download: "jarvis-ca.crt" }, "Download Jarvis's certificate"))));
  }

  // ------------------------------------------------------------------ start
  async function start() {
    if (!state.token) return renderPairing();
    try {
      const who = await api("/api/phone/whoami", { timeout: 4000 });
      state.device = who.device;
      state.computer = who.computer;
      state.online = true;
    } catch (err) {
      if (!state.token) return; // unpaired: the pairing screen is already showing
      // offline with something useful saved (tasks, cards, guides, the planner): open in offline mode
      const copy = readJSON(CACHE_KEY, null) ||
        (err instanceof Offline && (POCKET || offlinePack()) ? { device: null, computer: POCKET ? "This phone" : "" } : null);
      if (!(err instanceof Offline) || !copy) return renderUnreachable(err);
      // Offline, but we have a copy of the tasks: open the app in offline mode.
      state.device = copy.device;
      state.computer = copy.computer;
      state.online = false;
      if (state.tab === "chat") state.tab = "tasks";
      renderShell();
      renderBanner();
      showTab(state.tab);
      mountCompanion(); // she, focus sessions and check-ins work without Jarvis
      scheduleReconnect();
      return;
    }
    renderShell();
    if (outbox().ops.length) {
      try { await syncOutbox(); } catch (_) { /* went offline again; banner shows it */ }
    }
    await refreshStatus();
    showTab(state.tab);
    mountCompanion();
    refreshOfflinePack();
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (!state.online) return scheduleReconnect(0);
    refreshStatus();
    if (state.tab === "tasks" && $("#m-task-list")) loadTasks();
  });
  window.addEventListener("online", () => { if (!state.online) scheduleReconnect(0); });
  setInterval(refreshStatus, 30000);

  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/m/sw.js", { scope: "/m/" }).catch(() => { /* untrusted certificate: run without it */ });
  }

  start();
})();
