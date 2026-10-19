/* Jarvis interface. Plain JavaScript with no external libraries, so it works offline. */
(function () {
  "use strict";

  const TOKEN = document.querySelector('meta[name="jarvis-token"]').content;
  const MD = window.JarvisMarkdown;
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  const state = {
    status: null,
    settings: null,
    paths: null,
    view: "chat",
    conversationId: null,
    mode: "auto", // Jarvis picks the best mode for each question (router.py)
    detail: "concise",
    attached: [],
    images: [], // pictures waiting to be sent with the next message (data URLs)
    streaming: null,
    project: null,
    projectTab: "files",
    openDirs: new Set([""]),
    currentFile: null,
    editing: false,
    editDraft: null,
    run: null,
    runTimer: null,
    activityScope: "session",
    speaking: null,
  };

  // ------------------------------------------------------------------ helpers
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === undefined || v === null || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k === "html") node.innerHTML = v; // only ever used with escaped Markdown output
        else if (k === "dataset") Object.assign(node.dataset, v);
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
    // Like node.replaceChildren(), but flattens arrays and skips null/false (native would print them).
    node.replaceChildren(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
    return node;
  }

  function apiError(status, data) {
    let msg = `Request failed (HTTP ${status})`;
    if (data && typeof data.detail === "string") msg = data.detail;
    else if (data && Array.isArray(data.detail)) {
      msg = data.detail.map((d) => `${(d.loc || []).filter((x) => x !== "body").join(".")}: ${d.msg}`).join("; ");
    }
    const err = new Error(msg);
    err.status = status;
    err.hint = (data && data.hint) || "";
    return err;
  }

  async function api(path, opts = {}) {
    const headers = { "X-Jarvis-Token": TOKEN };
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    let res;
    try {
      res = await fetch(path, {
        method: opts.method || "GET",
        headers,
        body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
        signal: opts.signal,
      });
    } catch (e) {
      if (e.name === "AbortError") throw e;
      const err = new Error("Can't reach the Jarvis server. Is it still running?");
      err.hint = "Start it again with run_jarvis.bat (or python -m jarvis), then reload this page.";
      throw err;
    }
    if (opts.raw) return res;
    let data = null;
    try { data = await res.json(); } catch (_) { /* empty body */ }
    if (!res.ok) throw apiError(res.status, data);
    return data;
  }

  function toast(message, kind, hint) {
    const box = el("div", { class: "toast " + (kind || ""), role: kind === "error" ? "alert" : "status" },
      el("div", { text: message }), hint ? el("div", { class: "hint", text: hint }) : null);
    $("#toasts").append(box);
    setTimeout(() => box.remove(), kind === "error" ? 11000 : 5000);
  }
  const showError = (err) => toast(err.message || String(err), "error", err.hint || "");
  const CUT_NOTE = /\*\(Stopped at the answer length limit[^\n]*\)\*\s*$/; // the server's note on a cut-off answer

  function randomId() {
    if (window.crypto && crypto.getRandomValues) {
      return Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => b.toString(16).padStart(2, "0")).join("");
    }
    return String(Math.random()).slice(2);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied to clipboard", "ok");
    } catch (_) {
      const ta = el("textarea", { style: "position:fixed;left:-9999px" });
      ta.value = text;
      document.body.append(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
      toast("Copied to clipboard", "ok");
    }
  }

  function fmtTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }
  function fmtBytes(n) {
    if (!n) return "";
    if (n > 1e9) return (n / 1e9).toFixed(1) + " GB";
    if (n > 1e6) return (n / 1e6).toFixed(0) + " MB";
    return Math.max(1, Math.round(n / 1024)) + " KB";
  }
  function localToday() {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
  }
  function dueInfo(due, done) {
    if (!due) return null;
    const [y, m, d] = due.split("-").map(Number);
    const date = new Date(y, m - 1, d);
    const days = Math.round((date - localToday()) / 86400000);
    const label = date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    if (done) return { text: "Due " + label, cls: "" };
    if (days < 0) return { text: `Overdue (${label})`, cls: "overdue" };
    if (days === 0) return { text: "Due today", cls: "today" };
    if (days === 1) return { text: "Due tomorrow", cls: "" };
    return { text: "Due " + label, cls: "" };
  }

  // ------------------------------------------------------------------ modal
  function openModal({ title, body, actions, wide, onClose }) {
    const prevFocus = document.activeElement;
    const foot = el("div", { class: "modal-foot" });
    const modal = el("div", { class: "modal" + (wide ? " wide" : ""), role: "dialog", "aria-modal": "true", "aria-label": title },
      el("div", { class: "modal-head" }, el("h3", { text: title }),
        el("button", { class: "ghost", "aria-label": "Close", onclick: () => close() }, "\u2715")),
      el("div", { class: "modal-body" }, body), foot);
    const backdrop = el("div", { class: "modal-backdrop", onmousedown: (e) => { if (e.target === backdrop) close(); } }, modal);
    let closed = false;
    function onKey(e) { if (e.key === "Escape") close(); }
    function close() {
      if (closed) return;
      closed = true;
      backdrop.remove();
      document.removeEventListener("keydown", onKey);
      if (onClose) onClose();
      if (prevFocus && prevFocus.focus) prevFocus.focus();
    }
    function render(list) {
      fill(foot);
      for (const a of list || []) {
        if (a.node) { foot.append(a.node); continue; }
        const btn = el("button", { class: a.kind || "", type: "button", disabled: a.disabled }, a.label);
        btn.addEventListener("click", async () => {
          if (!a.onClick) return close();
          const old = btn.textContent;
          btn.disabled = true;
          if (a.busy) btn.textContent = a.busy;
          try {
            const keep = await a.onClick(close, btn);
            if (keep !== true) close();
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
    render(actions);
    document.addEventListener("keydown", onKey);
    $("#modal-root").append(backdrop);
    const first = modal.querySelector(".modal-body input, .modal-body textarea, .modal-body select") || foot.querySelector("button:last-child");
    if (first) first.focus();
    return { close, modal, setActions: render };
  }

  function confirmDialog({ title, message, confirmLabel, danger, check }) {
    return new Promise((resolve) => {
      let ok = false;
      const box = check ? el("input", { type: "checkbox" }) : null;
      const body = el("div", { class: "stack" }, typeof message === "string" ? el("p", { text: message }) : message,
        check ? el("label", { class: "check" }, box, check) : null);
      openModal({
        title, body, onClose: () => resolve(ok),
        actions: [
          { label: "Cancel" },
          { label: confirmLabel || "Confirm", kind: danger ? "danger" : "primary", onClick: () => {
            if (box && !box.checked) { toast("Tick the box to confirm.", "error"); return true; }
            ok = true;
          } },
        ],
      });
    });
  }

  // ------------------------------------------------------------------ navigation
  function switchView(name) {
    state.view = name;
    for (const b of $$(".sidenav button")) b.setAttribute("aria-current", b.dataset.view === name ? "page" : "false");
    for (const s of $$("main > .view")) s.hidden = s.id !== "view-" + name;
    if (name === "tasks") loadTasks();
    if (name === "study" && window.JarvisStudy) window.JarvisStudy.render();
    if (name === "learn" && window.JarvisLearn) window.JarvisLearn.render();
    if (name === "progress" && window.JarvisProgress) window.JarvisProgress.render();
    if (name === "build" && window.JarvisBuild) {
      window.JarvisBuild.render($("#build-root"), { api, ask: (text, mode) => askInChat(text, mode), toast: (t) => toast(t, "ok") });
    }
    if (window.JarvisCompanion) window.JarvisCompanion.setContext({ view: name, mode: state.mode });
    if (name === "project") renderProject();
    if (name === "activity") loadActivity();
    if (name === "settings") renderSettings();
    if (name === "chat") $("#prompt").focus();
  }

  // ------------------------------------------------------------------ status
  const STATE_TEXT = {
    ready: ["ok", (s) => "Model: " + s.model],
    not_running: ["bad", (s) => (s.provider === "ollama" ? "Ollama not running" : "Model server not running")],
    no_models: ["warn", () => "No model installed"],
    model_missing: ["warn", (s) => "Model missing: " + s.model],
    blocked: ["bad", () => "Endpoint blocked"],
  };

  async function refreshStatus() {
    try {
      state.status = await api("/api/status");
    } catch (err) {
      $("#model-pill").className = "pill bad";
      $("#model-pill-text").textContent = "Jarvis server unreachable";
      return;
    }
    const st = state.status;
    const m = st.model;
    const [cls, fn] = STATE_TEXT[m.state] || ["warn", () => m.state];
    $("#model-pill").className = "pill " + cls;
    $("#model-pill-text").textContent = fn(m);
    $("#model-pill").title = (m.message || "") + (m.hint ? "\n" + m.hint : "") + "\nEndpoint: " + m.endpoint;
    $("#project-pill").className = "pill " + (st.project.open ? "ok" : "");
    $("#project-pill-text").textContent = st.project.open ? "Project: " + st.project.name : "No project";
    $("#project-pill").title = st.project.open ? st.project.root : "No project folder selected. Click to choose one.";
    $("#phone-pill").hidden = !st.phone.enabled;
    $("#phone-pill").className = "pill " + (st.phone.running ? "ok" : "bad");
    $("#phone-pill-text").textContent = st.phone.running ? "Phone access on" : "Phone access failed";
    $("#use-project-wrap").hidden = !st.project.open;
    $("#run-tests-wrap").hidden = !(st.project.open && st.project.can_run_tests);
    if (!$("#mode").options.length) {
      for (const md of st.modes) $("#mode").append(el("option", { value: md.id, title: md.hint }, md.label));
      $("#mode").value = state.mode;
      fill($("#help-modes"), ...st.modes.map((md) => el("li", {}, el("strong", { text: md.label + ": " }), md.hint)));
    }
    renderSetupBanner();
  }

  function renderSetupBanner() {
    const banner = $("#setup-banner");
    const m = state.status && state.status.model;
    if (!m || m.state === "ready") { banner.hidden = true; return; }
    banner.hidden = false;
    fill(banner, el("div", { class: "notice " + (m.state === "not_running" || m.state === "blocked" ? "bad" : "warn") },
      el("h4", { text: m.message }),
      el("p", { text: m.hint }),
      el("p", { class: "small muted", text: "Tasks, project browsing, commands and file changes still work without the model." }),
      el("div", { class: "row" },
        el("button", { onclick: () => switchView("help") }, "Open setup guide"),
        el("button", { onclick: () => switchView("settings") }, "Settings"),
        el("button", { class: "primary", onclick: async () => { await refreshStatus(); toast(state.status.model.message || "Checked", state.status.model.state === "ready" ? "ok" : "error"); } }, "Check again"))));
  }

  // ------------------------------------------------------------------ chat: conversations
  async function loadConversations() {
    let list = [];
    try { list = await api("/api/conversations"); } catch (err) { return showError(err); }
    const ul = $("#conversations");
    fill(ul, ...list.map((c) => el("li", { class: c.id === state.conversationId ? "active" : "" },
      el("button", { class: "open", title: `${c.title}\n${fmtTime(c.updated_at)}`, onclick: () => openConversation(c.id) }, c.title),
      el("button", { class: "ghost small del", title: "Delete this conversation", "aria-label": "Delete conversation", onclick: async () => {
        if (!(await confirmDialog({ title: "Delete conversation?", message: `"${c.title}" will be removed from your history.`, confirmLabel: "Delete", danger: true }))) return;
        try {
          await api(`/api/conversations/${c.id}`, { method: "DELETE" });
          if (state.conversationId === c.id) newChat();
          loadConversations();
        } catch (err) { showError(err); }
      } }, "\u2715"))));
    if (!list.length) ul.append(el("li", { class: "muted small", style: "padding:8px" }, "No conversations yet."));
  }

  async function openConversation(id) {
    if (state.streaming) return toast("Wait for the current answer to finish, or press Stop.", "error");
    try {
      const data = await api(`/api/conversations/${id}`);
      state.conversationId = id;
      const inner = $("#messages-inner");
      fill(inner);
      data.messages.forEach((m, i) => {
        if (m.role === "user") appendUserMessage(m.content, [], m.images);
        else {
          const v = createAssistantMessage();
          v.setSources(m.sources);
          v.setContent(m.content);
          v.finish({ model: m.model, stopped: m.stopped, cut: i === data.messages.length - 1 && CUT_NOTE.test(m.content) });
        }
      });
      loadConversations();
      scrollToBottom(true);
    } catch (err) { showError(err); }
  }

  function newChat() {
    if (state.streaming) return toast("Wait for the current answer to finish, or press Stop.", "error");
    state.conversationId = null;
    renderWelcome();
    loadConversations();
    $("#prompt").focus();
  }

  const EXAMPLES = [
    ["requirements", "Requirements", "I want a small app to track my reading list. Turn this idea into requirements and acceptance criteria."],
    ["design", "Architecture", "Design a REST API and database schema for a to-do app with users and shared lists."],
    ["implement", "Implementation", "Write a Python function that validates email addresses, with unit tests."],
    ["test", "Debugging", "What does \"TypeError: 'NoneType' object is not subscriptable\" mean and how do I find the cause?"],
    ["explain", "Learn", "Explain what an API is, with a simple real-world example."],
    ["tasks", "Planning", "Help me plan learning Git basics this week, in small steps."],
    ["study", "Study", "Quiz me on the parts of a cell, one question at a time."],
    ["study", "Study", "Explain photosynthesis simply, then check that I understood."],
  ];

  function renderWelcome() {
    const inner = $("#messages-inner");
    fill(inner, el("div", { class: "welcome" },
      el("h2", { text: "Hi, I'm Jarvis." }),
      el("p", { class: "muted", text: "Your local assistant for tasks and software development. Everything runs on this computer." }),
      el("div", { class: "examples" }, EXAMPLES.map(([mode, label, text]) => el("button", {
        onclick: () => { setMode(mode); $("#prompt").value = text; autoGrow(); $("#prompt").focus(); },
      }, el("b", { text: label }), el("span", { text }))))));
  }

  // ------------------------------------------------------------------ chat: messages
  function scrollToBottom(force) {
    const box = $("#messages");
    if (force || box.scrollHeight - box.scrollTop - box.clientHeight < 160) box.scrollTop = box.scrollHeight;
  }

  function appendUserMessage(text, pictures, storedNames) {
    $(".welcome") && fill($("#messages-inner"));
    const thumbs = el("div", { class: "thumbs" });
    for (const src of pictures || []) thumbs.append(window.JarvisImages.thumb(src));
    for (const name of storedNames || []) {
      const img = window.JarvisImages.thumb("");
      thumbs.append(img);
      window.JarvisImages.objectUrl(name, { "X-Jarvis-Token": TOKEN }).then((url) => { img.src = url; }).catch(() => img.remove());
    }
    $("#messages-inner").append(el("div", { class: "msg user" },
      el("div", { class: "avatar", "aria-hidden": "true" }, "You"),
      el("div", { class: "body" }, thumbs.childElementCount ? thumbs : null, el("div", { class: "bubble", text }))));
    scrollToBottom(true);
  }

  async function addImages(files) {
    for (const file of files) {
      if (state.images.length >= 4) { toast("Up to 4 pictures per message.", "error"); break; }
      try { state.images.push(await window.JarvisImages.toDataUrl(file)); } catch (err) { showError(err); }
    }
    renderImageChips();
  }

  function renderImageChips() {
    fill($("#image-chips"), state.images.map((src, i) => el("span", { class: "thumb-wrap" }, window.JarvisImages.thumb(src),
      el("button", { class: "thumb-x", type: "button", "aria-label": "Remove picture", onclick: () => { state.images.splice(i, 1); renderImageChips(); } }, "\u2715"))));
  }

  function createAssistantMessage() {
    const meta = el("div", { class: "meta" }, el("strong", { text: "Jarvis" }));
    const sources = el("div", { class: "sources", hidden: true });
    const thinking = el("details", { class: "thinking", hidden: true }, el("summary", { text: "Model's reasoning" }), el("pre"));
    const md = el("div", { class: "md" }, el("div", { class: "typing", "aria-label": "Jarvis is thinking" }, el("span"), el("span"), el("span")));
    const actions = el("div", { class: "msg-actions", hidden: true });
    const errorBox = el("div", { class: "msg-error", hidden: true });
    const statusBox = el("div", { class: "msg-status muted small", hidden: true });
    const node = el("div", { class: "msg assistant" }, el("div", { class: "avatar", "aria-hidden": "true" }, "J"),
      el("div", { class: "body" }, meta, statusBox, sources, thinking, md, errorBox, actions));
    $("#messages-inner").append(node);
    let content = "";
    let frame = 0;
    let thinkingText = "";

    function paint() {
      frame = 0;
      md.innerHTML = MD.renderMarkdown(content);
      scrollToBottom();
    }
    return {
      node,
      setContent(text) {
        content = text;
        if (!frame) frame = requestAnimationFrame(paint);
      },
      addStatus(text) {
        statusBox.hidden = false;
        statusBox.append(el("div", { text: "\u2022 " + text }));
        scrollToBottom();
      },
      addThinking(text) {
        thinkingText += text;
        thinking.hidden = false;
        thinking.querySelector("pre").textContent = thinkingText;
      },
      setSources(list, redactions) {
        if (!list || !list.length) return;
        sources.hidden = false;
        fill(sources, el("span", { class: "muted", text: "Used:" }),
          list.map((s) => s.kind === "command"
            ? el("button", { class: "chip", title: "Real output from running this command was included",
              onclick: () => { state.projectTab = "commands"; switchView("project"); } }, s.path)
            : s.kind === "guide"
            ? el("button", { class: "chip guide", title: "From Jarvis's built-in study guides \u2014 click to read it",
              onclick: () => { const [gid, anchor] = s.path.slice(6).split("#"); switchView("learn");
                if (window.JarvisLearn) window.JarvisLearn.openGuide(gid, anchor); } }, "\ud83d\udcd8 " + (s.title || s.path))
            : el("button", {
              class: "chip", title: `${s.kind === "attached" ? "Attached by you" : "Found by search"} — click to open`,
              onclick: () => openFileInProject(s.path),
            }, `${s.path}${s.kind === "search" ? `:${s.start_line}-${s.end_line}` : ""}`)),
          redactions ? el("span", { class: "muted", text: `(${redactions} secret-looking value${redactions > 1 ? "s" : ""} hidden)` }) : null);
      },
      finish({ model, stopped, stats, cut }) {
        if (frame) { cancelAnimationFrame(frame); frame = 0; }
        if (content) paint();
        else if (!stopped) fill(md);
        if (stopped) {
          if (!content) fill(md, el("p", { class: "muted", text: "(Stopped before any answer was written.)" }));
          meta.append(el("span", { class: "badge cancelled", text: "stopped" }));
        }
        if (model) meta.append(el("span", { text: model }));
        if (stats && stats.seconds) meta.append(el("span", { text: `${stats.seconds}s` }));
        decorateCodeBlocks(md);
        if (content) {
          actions.hidden = false;
          fill(actions,
            cut ? el("button", { class: "small", title: "The answer reached its length limit: write the rest",
              onclick: () => sendMessage("Continue", { noImages: true }) }, "Continue") : null,
            el("button", { class: "ghost small", onclick: () => copyText(content) }, "Copy"),
            el("button", { class: "ghost small", title: "Ask for a longer explanation with examples", onclick: () => sendMessage("Please explain your previous answer in more detail, with examples and definitions of any technical terms.", { detail: "detailed", noImages: true }) }, "More detail"),
            el("button", { class: "ghost small", title: "Save this answer as a file in your project (you'll review it first)", onclick: () => openProposeDialog({ path: `docs/jarvis-notes-${new Date().toISOString().slice(0, 10)}.md`, content, note: "Saved from chat" }) }, "Save to project\u2026"),
            state.settings && state.settings.voice_output ? el("button", { class: "ghost small", onclick: (e) => speak(content, e.currentTarget) }, "Read aloud") : null);
        }
        scrollToBottom();
      },
      showError(message, hint) {
        if (frame) { cancelAnimationFrame(frame); frame = 0; }
        if (content) paint(); else fill(md);
        errorBox.hidden = false;
        fill(errorBox, el("div", { class: "notice bad" }, el("strong", { text: message }),
          hint ? el("div", { class: "small", text: hint }) : null,
          el("div", { class: "row", style: "margin-top:6px" },
            el("button", { class: "small", onclick: () => switchView("help") }, "Setup guide"),
            el("button", { class: "small", onclick: refreshStatus }, "Check model status"))));
        decorateCodeBlocks(md);
        scrollToBottom();
      },
    };
  }

  function decorateCodeBlocks(root) {
    for (const block of $$(".codeblock", root)) {
      const bar = $(".codeactions", block);
      if (!bar || bar.childElementCount) continue;
      bar.append(el("button", { class: "small ghost", "data-code-action": "copy" }, "Copy"));
      bar.append(el("button", { class: "small ghost", "data-code-action": "propose", title: "Create or replace a project file with this code (you'll review a diff first)" }, "Propose as file change\u2026"));
      if (block.dataset.shell) bar.append(el("button", { class: "small ghost", "data-code-action": "run", title: "Run this command in your project (you'll see what it does first)" }, "Run\u2026"));
    }
  }

  $("#messages-inner").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-code-action]");
    if (!btn) return;
    const block = btn.closest(".codeblock");
    const code = $("code", block).textContent;
    const action = btn.dataset.codeAction;
    if (action === "copy") copyText(code);
    if (action === "propose") {
      const cleaned = stripLineNumbers(code);
      if (cleaned.stripped) toast("Removed line numbers the model added to the code.", "info");
      openProposeDialog({ path: block.dataset.path || "", content: cleaned.code, note: "From chat" });
    }
    if (action === "run") runFromCodeBlock(code);
  });

  // Small models sometimes copy "12 | code" style line numbers into their answers.
  function stripLineNumbers(code) {
    const re = /^\s*\d+\s?\|\s?/;
    const lines = code.split("\n");
    const nonEmpty = lines.filter((l) => l.trim());
    if (nonEmpty.length >= 2 && nonEmpty.filter((l) => re.test(l)).length / nonEmpty.length >= 0.8) {
      return { code: lines.map((l) => l.replace(re, "")).join("\n"), stripped: true };
    }
    return { code, stripped: false };
  }

  function setComposerBusy(busy) {
    $("#send").hidden = busy;
    $("#stop").hidden = !busy;
  }

  async function sendMessage(text, opts) {
    opts = opts || {};
    text = (text || "").trim();
    if (!text) return;
    if (state.streaming) return toast("Jarvis is still answering. Press Stop first.", "error");
    const pictures = opts.noImages ? [] : state.images.splice(0);
    renderImageChips();
    appendUserMessage(text, pictures);
    const view = createAssistantMessage();
    const streamId = randomId();
    const controller = new AbortController();
    state.streaming = { streamId, controller };
    setComposerBusy(true);
    const projectOpen = state.status && state.status.project.open;
    const body = {
      message: text,
      conversation_id: state.conversationId,
      mode: state.mode,
      detail: opts.detail || state.detail,
      use_project: !!(projectOpen && $("#use-project").checked),
      attached: projectOpen ? state.attached.slice() : [],
      stream_id: streamId,
      run_tests: !!(projectOpen && !$("#run-tests-wrap").hidden && $("#run-tests").checked),
      images: pictures,
      use_guides: $("#use-guides").checked,
      lang: window.JarvisI18n ? window.JarvisI18n.lang() : "en",
      wellbeing: window.JarvisCompanion ? window.JarvisCompanion.wellbeing() : "",
    };
    let content = "";
    let ended = false;
    const buddy = window.JarvisCompanion;
    if (buddy) buddy.react("thinking", true);
    function handle(ev) {
      if (ev.type === "content" && buddy && !content) buddy.react("thinking", false);
      if (ev.type === "meta") {
        const isNew = state.conversationId !== ev.conversation_id;
        state.conversationId = ev.conversation_id;
        if (isNew) loadConversations();
      } else if (ev.type === "sources") view.setSources(ev.sources, ev.redactions);
      else if (ev.type === "status") view.addStatus(ev.text);
      else if (ev.type === "thinking") view.addThinking(ev.text);
      else if (ev.type === "content") { content += ev.text; view.setContent(content); }
      else if (ev.type === "done") { ended = true; view.finish({ model: ev.model, stats: ev.stats, cut: ev.cut }); }
      else if (ev.type === "stopped") { ended = true; view.finish({ stopped: true }); }
      else if (ev.type === "error") { ended = true; view.showError(ev.message, ev.hint); }
    }
    try {
      const res = await api("/api/chat", { method: "POST", body, raw: true, signal: controller.signal });
      if (!res.ok) throw apiError(res.status, await res.json().catch(() => null));
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
      else view.showError(err.message, err.hint);
    } finally {
      state.streaming = null;
      setComposerBusy(false);
      if (buddy) buddy.react("thinking", false);
      loadConversations();
    }
  }

  async function stopStreaming() {
    const s = state.streaming;
    if (!s) return;
    try { await api("/api/chat/cancel", { method: "POST", body: { stream_id: s.streamId } }); } catch (_) { /* ignore */ }
    setTimeout(() => { if (state.streaming === s) s.controller.abort(); }, 2500);
  }

  // modes where Jarvis's guides help (in Auto they're only added when a guide really answers the question)
  const GUIDE_MODES = ["auto", "study", "explain", "coach", "rules", "business", "stack", "hackathon"];

  function setMode(mode) {
    state.mode = mode;
    $("#mode").value = mode;
    $("#run-tests").checked = mode === "test";
    $("#use-guides").checked = GUIDE_MODES.includes(mode);
  }

  /** Open Chat in a mode with a message ready (or sent right away), for the Learn page. */
  function askInChat(text, mode, send) {
    if (mode) setMode(mode);
    switchView("chat");
    if (send) return sendMessage(text);
    $("#prompt").value = text;
    autoGrow();
    $("#prompt").focus();
  }

  function autoGrow() {
    const ta = $("#prompt");
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 240) + "px";
  }

  function renderAttachments() {
    const box = $("#attachments");
    fill(box, ...state.attached.map((p) => el("span", { class: "chip", title: "This file is included in full with each message" },
      "\uD83D\uDCCE " + p, el("button", { "aria-label": "Remove " + p, title: "Remove", onclick: () => { state.attached = state.attached.filter((x) => x !== p); renderAttachments(); } }, "\u2715"))));
  }

  function attachFile(path) {
    if (!state.attached.includes(path)) state.attached.push(path);
    renderAttachments();
  }

  // ------------------------------------------------------------------ voice output (optional, local voices only)
  function localVoices() {
    if (!("speechSynthesis" in window)) return [];
    return speechSynthesis.getVoices().filter((v) => v.localService);
  }
  function speak(markdown, btn) {
    if (!("speechSynthesis" in window)) return toast("This browser has no speech support.", "error");
    if (state.speaking) {
      speechSynthesis.cancel();
      const was = state.speaking;
      state.speaking = null;
      if (was === btn) return;
    }
    const voices = localVoices();
    if (!voices.length) return toast("No offline voice is installed on this system, so Jarvis won't read aloud.", "error", "Jarvis only uses voices that run on this computer.");
    // Japanese text gets a Japanese voice; otherwise the language picked in Settings (or the browser's)
    const lang = /[぀-ヿ一-鿿]/.test(markdown) ? "ja"
      : window.JarvisI18n && window.JarvisI18n.lang() === "ja" ? "ja" : (navigator.language || "en").slice(0, 2);
    const u = new SpeechSynthesisUtterance(MD.toSpeech(markdown));
    u.voice = voices.find((v) => v.lang && v.lang.startsWith(lang)) || voices[0];
    u.lang = u.voice.lang;
    if (lang === "ja" && !u.voice.lang.startsWith("ja")) {
      toast("No offline Japanese voice is installed, so this is read with another voice.", "error",
        "Windows: Settings > Time & language > Speech > Add voices > Japanese.");
    }
    u.onend = () => { if (state.speaking === btn) { state.speaking = null; btn.textContent = "Read aloud"; } };
    state.speaking = btn;
    btn.textContent = "Stop reading";
    speechSynthesis.speak(u);
  }

  // ------------------------------------------------------------------ file changes (proposals)
  function requireProject() {
    if (state.status && state.status.project.open) return true;
    toast("Open a project folder first.", "error", "Go to the Project tab and choose your project's folder.");
    switchView("project");
    return false;
  }

  function openProposeDialog({ path, content, note }) {
    if (!requireProject()) return;
    const pathInput = el("input", { type: "text", value: path || "", placeholder: "e.g. src/utils/email.py" });
    const ta = el("textarea", { rows: 16, class: "mono", spellcheck: "false" });
    ta.value = content || "";
    const body = el("div", { class: "stack" },
      el("label", { class: "field" }, el("span", { text: "File path (relative to the project folder)" }), pathInput,
        el("small", { text: "If the file exists it will be replaced with the content below; otherwise it is created." })),
      el("label", { class: "field" }, el("span", { text: "New file content" }), ta,
        el("small", { text: "Nothing is written yet. Next you'll see a diff and any warnings." })));
    openModal({
      title: "Propose a file change", body, wide: true,
      actions: [
        { label: "Cancel" },
        { label: "Review changes", kind: "primary", busy: "Preparing\u2026", onClick: async () => {
          const p = pathInput.value.trim();
          if (!p) { toast("Enter a file path.", "error"); return true; }
          const proposal = await api("/api/changes", { method: "POST", body: { path: p, content: ta.value, note: note || "", source: "assistant" } });
          reviewProposal(proposal);
        } },
      ],
    });
  }

  async function proposeDelete(path) {
    try {
      const proposal = await api("/api/changes", { method: "POST", body: { path, delete: true, source: "manual", note: "Delete requested in file viewer" } });
      reviewProposal(proposal);
    } catch (err) { showError(err); }
  }

  function renderDiff(text) {
    const pre = el("pre", { class: "diff" });
    for (const line of (text || "").split("\n")) {
      let cls = "";
      if (line.startsWith("+++") || line.startsWith("---")) cls = "file";
      else if (line.startsWith("@@")) cls = "hunk";
      else if (line.startsWith("+")) cls = "add";
      else if (line.startsWith("-")) cls = "del";
      pre.append(el("span", { class: cls }, line || " "));
    }
    return pre;
  }

  function reviewProposal(p) {
    const verb = { create: "Create", modify: "Modify", delete: "Delete" }[p.kind] || p.kind;
    const confirmBox = el("input", { type: "checkbox" });
    const body = el("div", { class: "stack" },
      el("div", { class: "row" }, el("span", { class: "badge " + p.status, text: p.status }),
        el("span", { class: "mono", text: p.path }), el("span", { class: "muted small", text: `${p.source} · ${fmtTime(p.created_at)}` })),
      p.error ? el("div", { class: "notice bad", text: p.error }) : null,
      p.warnings.length ? el("div", { class: "notice warn" }, el("h4", { text: "Please check" }),
        el("ul", {}, p.warnings.map((w) => el("li", { text: w.message })))) : null,
      p.status === "pending" && p.needs_confirm ? el("label", { class: "check" }, confirmBox, "I've read the warnings and want to apply this change") : null,
      p.status === "applied" && p.backup_path ? el("p", { class: "muted small", text: "Original backed up to: " + p.backup_path }) : null,
      renderDiff(p.diff));
    const actions = [];
    if (p.status === "pending") {
      actions.push({ label: "Reject", onClick: async () => { await api(`/api/changes/${p.id}/reject`, { method: "POST" }); toast("Change rejected", "ok"); afterChange(); } });
      actions.push({ label: "Decide later" });
      actions.push({ label: `${verb} file`, kind: p.kind === "delete" ? "danger" : "primary", busy: "Applying\u2026", onClick: async () => {
        if (p.needs_confirm && !confirmBox.checked) { toast("Tick the confirmation box first.", "error"); return true; }
        await api(`/api/changes/${p.id}/apply`, { method: "POST", body: { confirmed: confirmBox.checked } });
        toast(`${verb}d ${p.path}`, "ok", "You can undo this from Project \u2192 Changes.");
        afterChange(p.path);
      } });
    } else if (p.status === "applied") {
      actions.push({ label: "Close" });
      actions.push({ label: "Undo this change", kind: "danger", busy: "Undoing\u2026", onClick: async () => {
        try {
          await api(`/api/changes/${p.id}/undo`, { method: "POST", body: { force: false } });
        } catch (err) {
          if (err.status !== 400 || !/edited after/.test(err.message)) throw err;
          if (!(await confirmDialog({ title: "File was edited since", message: err.message, confirmLabel: "Undo anyway", danger: true }))) return true;
          await api(`/api/changes/${p.id}/undo`, { method: "POST", body: { force: true } });
        }
        toast(`Undid change to ${p.path}`, "ok");
        afterChange(p.path);
      } });
    } else {
      actions.push({ label: "Close" });
    }
    openModal({ title: `Change #${p.id}: ${verb.toLowerCase()} ${p.path}`, body, wide: true, actions });
  }

  function afterChange(path) {
    if (state.view === "project") {
      if (path && state.currentFile && state.currentFile.path === path) openFile(path, { force: true });
      if (state.projectTab === "changes") renderProjectTab();
      else refreshTree();
    }
  }

  // ------------------------------------------------------------------ commands
  function runFromCodeBlock(code) {
    const lines = code.split("\n").map((l) => l.trim()).filter((l) => l && !/^(#|REM\b|::|\/\/)/i.test(l))
      .map((l) => l.replace(/^(\$|>|PS[^>]*>)\s+/, ""));
    if (!lines.length) return toast("No command found in this block.", "error");
    if (lines.length > 1) toast(`This block has ${lines.length} commands. Jarvis runs one at a time, starting with the first.`, "info");
    openCommandDialog(lines[0]);
  }

  async function openCommandDialog(command) {
    if (!requireProject()) return;
    let check;
    try {
      check = await api("/api/commands/check", { method: "POST", body: { command } });
    } catch (err) { return showError(err); }
    const ack = el("input", { type: "checkbox" });
    const levelText = { safe: "Safe", caution: "Needs your approval", danger: "Risky" }[check.level];
    const body = el("div", { class: "stack" },
      el("pre", { class: "console", style: "min-height:0" }, check.command),
      el("div", { class: "row" }, el("span", { class: "badge " + check.level, text: levelText }),
        el("span", { class: "muted small", text: "Runs in: " + state.status.project.root })),
      el("p", { text: check.summary }),
      check.reasons.length ? el("ul", {}, check.reasons.map((r) => el("li", { text: r }))) : null,
      check.level === "danger" ? el("label", { class: "check" }, ack, "I understand the risk and want to run this command") : null,
      el("p", { class: "muted small", text: "You can stop it at any time. Output appears in Project \u2192 Commands." }));
    openModal({
      title: "Run a command", body,
      actions: [
        { label: "Cancel" },
        { label: check.level === "safe" ? "Run" : "Approve and run", kind: check.level === "danger" ? "danger" : "primary", onClick: async () => {
          if (check.level === "danger" && !ack.checked) { toast("Tick the box to confirm you understand the risk.", "error"); return true; }
          await startCommand(check.command, true, ack.checked);
        } },
      ],
    });
  }

  async function startCommand(command, approved, acknowledge) {
    const run = await api("/api/commands/run", { method: "POST", body: { command, approved: !!approved, acknowledge_risk: !!acknowledge } });
    state.run = run;
    state.projectTab = "commands";
    if (state.view !== "project") switchView("project");
    else renderProjectTab();
    pollRun();
  }

  function pollRun() {
    clearTimeout(state.runTimer);
    const run = state.run;
    if (!run || run.status !== "running") return;
    state.runTimer = setTimeout(async () => {
      try {
        const upd = await api(`/api/commands/${run.id}?since=${run.output_length || 0}`);
        if (state.run !== run) return;
        if (upd.output_length < (run.output_length || 0)) {
          const full = await api(`/api/commands/${run.id}`); // output was trimmed: reload all
          Object.assign(run, full);
        } else {
          run.output = (run.output || "") + upd.output;
          Object.assign(run, { ...upd, output: run.output });
        }
        renderRunConsole();
        if (run.status === "running") pollRun();
        else toast(`Command ${run.status === "finished" ? "finished" : run.status.replace("_", " ")} (exit code ${run.exit_code})`, run.status === "finished" ? "ok" : "error");
      } catch (err) { showError(err); }
    }, 600);
  }

  function renderRunConsole() {
    const box = $("#run-console");
    if (!box) return;
    const run = state.run;
    if (!run) { fill(box, el("p", { class: "muted", text: "No command run yet in this session." })); return; }
    const out = el("pre", { class: "console", id: "run-output" }, run.output || (run.status === "running" ? "Waiting for output\u2026" : "(no output)"));
    fill(box, 
      el("div", { class: "row" },
        el("span", { class: "mono", text: "$ " + run.command }),
        el("span", { class: "badge " + run.status, text: run.status.replace("_", " ") }),
        run.exit_code !== null && run.exit_code !== undefined ? el("span", { class: "muted small", text: "exit code " + run.exit_code }) : null,
        el("span", { class: "muted small", text: run.seconds + "s" }),
        run.truncated ? el("span", { class: "muted small", text: "(older output trimmed)" }) : null,
        el("span", { class: "spacer" }),
        run.status === "running" ? el("button", { class: "danger small", onclick: async () => {
          try { Object.assign(run, await api(`/api/commands/${run.id}/cancel`, { method: "POST" })); renderRunConsole(); } catch (err) { showError(err); }
        } }, "Stop") : null,
        run.status !== "running" ? el("button", { class: "small", onclick: () => copyText(run.output || "") }, "Copy output") : null,
        run.status !== "running" ? el("button", { class: "small primary", onclick: () => askAboutOutput(run) }, "Ask Jarvis about this output") : null),
      out);
    out.scrollTop = out.scrollHeight;
  }

  function askAboutOutput(run) {
    const output = (run.output || "").slice(-6000);
    const ok = run.exit_code === 0;
    const text = `I ran \`${run.command}\` in my project and it ${ok ? "finished" : "failed"} with exit code ${run.exit_code}. ` +
      (ok ? "Please summarize the result and point out any warnings." : "What does this output mean, what is the most likely cause, and how do I fix it?") +
      `\n\n\`\`\`text\n${output}\n\`\`\``;
    setMode("test");
    switchView("chat");
    $("#prompt").value = text;
    autoGrow();
    $("#prompt").focus();
    toast("Review the message, then press Send.", "info");
  }

  // ------------------------------------------------------------------ project view
  async function loadProject() {
    try { state.project = await api("/api/project"); } catch (err) { showError(err); state.project = { open: false, recent: [] }; }
    return state.project;
  }

  async function renderProject() {
    const page = $("#project-page");
    const proj = await loadProject();
    if (!proj.open) return renderProjectChooser(page, proj);
    const idx = proj.index || {};
    const indexText = idx.state === "indexing" ? `Indexing\u2026 ${idx.files_indexed} files` :
      idx.state === "ready" ? `${idx.files_indexed} files indexed${idx.limit_reached ? " (limit reached)" : ""}` +
        ({ ready: " \u00B7 meaning search on", building: ` \u00B7 preparing meaning search ${idx.embedded}/${idx.chunks}`,
          unavailable: " \u00B7 keywords only (embedding model not installed)", error: " \u00B7 keywords only" }[idx.semantic] || "") :
      idx.state === "cancelled" ? `Indexing stopped (${idx.files_indexed} files)` : idx.state === "error" ? "Index error: " + idx.error : idx.state;
    const ov = proj.overview || {};
    fill(page, 
      el("div", { class: "page-head" },
        el("div", { class: "grow" }, el("h2", { text: proj.name }), el("div", { class: "muted small mono", text: proj.root })),
        el("span", { class: "badge " + (idx.state === "ready" ? "safe" : idx.state === "indexing" ? "running" : ""), text: indexText }),
        idx.state === "indexing" ? el("button", { onclick: async () => { await api("/api/project/index/cancel", { method: "POST" }); setTimeout(renderProject, 300); } }, "Stop indexing") : null,
        el("button", { title: "Re-scan files (after big changes)", onclick: async () => { try { await api("/api/project/reindex", { method: "POST" }); renderProject(); } catch (err) { showError(err); } } }, "Re-index"),
        el("button", { onclick: async () => {
          await api("/api/project/close", { method: "POST" });
          state.attached = []; renderAttachments(); state.currentFile = null; state.editing = false; state.editDraft = null;
          await refreshStatus(); renderProject();
        } }, "Close project")),
      ov.languages ? el("p", { class: "muted small" },
        `Languages: ${ov.languages.map((l) => `${l[0]} (${l[1]})`).join(", ") || "unknown"}` +
        (ov.key_files && ov.key_files.length ? ` · Key files: ${ov.key_files.join(", ")}` : "")) : null,
      el("div", { class: "tabs", role: "tablist" }, [["files", "Files"], ["commands", "Commands"], ["changes", "Changes"]].map(([id, label]) =>
        el("button", { role: "tab", "aria-selected": String(state.projectTab === id), onclick: () => { state.projectTab = id; renderProject(); } }, label))),
      el("div", { id: "project-tab" }));
    renderProjectTab();
    if (idx.state === "indexing" || idx.semantic === "building") setTimeout(() => { if (state.view === "project") renderProjectHeaderOnly(); }, 1500);
  }

  async function renderProjectHeaderOnly() {
    const proj = await loadProject();
    if (!proj.open) return;
    if (proj.index && proj.index.state !== "indexing" && proj.index.semantic !== "building") renderProject();
    else setTimeout(() => { if (state.view === "project") renderProjectHeaderOnly(); }, 1500);
  }

  function renderProjectChooser(page, proj) {
    const input = el("input", { type: "text", placeholder: "C:\\Users\\you\\projects\\my-app", "aria-label": "Project folder path" });
    async function open(path) {
      try {
        await api("/api/project/open", { method: "POST", body: { path } });
        state.openDirs = new Set([""]);
        state.currentFile = null;
        state.projectTab = "files";
        await refreshStatus();
        renderProject();
        toast("Project opened. Jarvis is indexing its files for search.", "ok");
      } catch (err) { showError(err); }
    }
    fill(page, 
      el("div", { class: "page-head" }, el("h2", { text: "Choose a project folder" })),
      el("div", { class: "card stack" },
        el("p", { text: "Jarvis can read the code and documents in one folder you choose, answer questions about them, propose changes for you to review, and run your tests and builds." }),
        el("div", { class: "row" },
          el("button", { class: "primary", onclick: async (e) => {
            const b = e.currentTarget; b.disabled = true; b.textContent = "Waiting for folder picker\u2026";
            try {
              const r = await api("/api/project/pick", { method: "POST" });
              if (r.path) open(r.path);
            } catch (err) { showError(err); } finally { b.disabled = false; b.textContent = "Browse\u2026"; }
          } }, "Browse\u2026"),
          el("span", { class: "muted", text: "or paste the path:" }),
          el("div", { class: "grow", style: "min-width:220px" }, input),
          el("button", { onclick: () => input.value.trim() && open(input.value.trim()) }, "Open")),
        el("div", { class: "notice info small" },
          el("strong", { text: "What Jarvis can access: " }),
          "only files inside the folder you choose. Files that may contain secrets (.env, private keys, credentials) are hidden and never sent to the model. Nothing in your project is changed unless you approve it.")),
      proj.recent && proj.recent.length ? el("div", { class: "card" }, el("h3", { text: "Recent projects" }),
        el("div", { class: "stack" }, proj.recent.map((p) => el("div", { class: "row" },
          el("span", { class: "mono grow small", text: p }), el("button", { class: "small", onclick: () => open(p) }, "Open"))))) : null);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") open(input.value.trim()); });
  }

  function renderProjectTab() {
    const box = $("#project-tab");
    if (!box) return;
    if (state.projectTab === "files") return renderFilesTab(box);
    if (state.projectTab === "commands") return renderCommandsTab(box);
    return renderChangesTab(box);
  }

  // ---- files tab
  function renderFilesTab(box) {
    const search = el("input", { type: "search", placeholder: "Search the project (keywords)\u2026", "aria-label": "Search project" });
    const results = el("ul", { class: "search-results" });
    let timer = 0;
    search.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const q = search.value.trim();
        if (!q) { fill(results); return; }
        try {
          const hits = await api("/api/project/search?q=" + encodeURIComponent(q));
          fill(results, ...(hits.length ? hits.map((h) => el("li", {}, el("button", { onclick: () => openFile(h.path) },
            el("div", { class: "mono small", text: `${h.path}:${h.start_line}-${h.end_line}` }),
            el("div", { class: "preview", text: h.preview })))) : [el("li", { class: "muted small", text: "No matches." })]));
        } catch (err) { showError(err); }
      }, 300);
    });
    fill(box, el("div", { class: "files" },
      el("div", {}, search, results, el("div", { class: "tree", id: "tree", style: "margin-top:8px" })),
      el("div", { class: "viewer", id: "viewer" })));
    refreshTree();
    renderViewer();
  }

  async function refreshTree() {
    const tree = $("#tree");
    if (!tree) return;
    const ul = el("ul");
    fill(tree, ul);
    await renderTreeLevel("", ul);
  }

  async function renderTreeLevel(path, ul) {
    let entries;
    try { entries = await api("/api/project/tree?path=" + encodeURIComponent(path)); } catch (err) { ul.append(el("li", { class: "muted small", text: err.message })); return; }
    if (!entries.length) ul.append(el("li", { class: "muted small", style: "padding-left:6px", text: "(empty)" }));
    for (const e of entries) {
      const li = el("li");
      if (e.sensitive) {
        li.append(el("button", { class: "node locked", disabled: true, title: "Hidden: this file may contain secrets, so Jarvis never reads it." }, "\uD83D\uDD12 " + e.name));
      } else if (e.type === "dir") {
        const open = state.openDirs.has(e.path);
        const children = el("ul", { hidden: !open });
        const btn = el("button", { class: "node" + (e.ignored ? " ignored" : ""), "aria-expanded": String(open), title: e.ignored ? "Generated or dependency folder (not searched)" : e.path },
          (open ? "\u25BE " : "\u25B8 ") + "\uD83D\uDCC1 " + e.name);
        let loaded = false;
        btn.addEventListener("click", async () => {
          const nowOpen = children.hidden;
          children.hidden = !nowOpen;
          btn.setAttribute("aria-expanded", String(nowOpen));
          btn.firstChild.textContent = (nowOpen ? "\u25BE " : "\u25B8 ") + "\uD83D\uDCC1 " + e.name;
          if (nowOpen) state.openDirs.add(e.path); else state.openDirs.delete(e.path);
          if (nowOpen && !loaded) { loaded = true; await renderTreeLevel(e.path, children); }
        });
        li.append(btn, children);
        if (open) { loaded = true; renderTreeLevel(e.path, children); }
      } else {
        li.append(el("button", { class: "node" + (state.currentFile && state.currentFile.path === e.path ? " active" : ""), dataset: { path: e.path },
          title: `${e.path} (${fmtBytes(e.size) || "0 KB"})`, onclick: () => openFile(e.path) }, "\uD83D\uDCC4 " + e.name));
      }
      ul.append(li);
    }
  }

  let fileRequest = 0;

  function confirmDiscardEdits() {
    if (!state.editing || state.editDraft === null || !state.currentFile || state.editDraft === state.currentFile.content) {
      return Promise.resolve(true);
    }
    return confirmDialog({ title: "Discard your edits?", danger: true, confirmLabel: "Discard edits",
      message: `You have unsaved edits to ${state.currentFile.path}. Discard them?` });
  }

  async function openFile(path, opts) {
    if (!(opts && opts.force) && !(await confirmDiscardEdits())) return;
    const req = ++fileRequest;
    try {
      const file = await api("/api/project/file?path=" + encodeURIComponent(path));
      if (req !== fileRequest) return; // a newer action (another file, or Edit) superseded this load
      state.currentFile = file;
      state.editing = false;
      state.editDraft = null;
      renderViewer();
      for (const b of $$("#tree button.node")) b.classList.toggle("active", b.dataset.path === path);
    } catch (err) { showError(err); }
  }

  async function openFileInProject(path) {
    state.projectTab = "files";
    switchView("project");
    await openFile(path);
  }

  function renderViewer() {
    const box = $("#viewer");
    if (!box) return;
    const f = state.currentFile;
    if (!f) {
      fill(box, el("div", { class: "placeholder" }, "Select a file to view it. You can attach it to the chat, ask Jarvis to explain it, or edit it."));
      return;
    }
    if (state.editing) {
      const ta = el("textarea", { spellcheck: "false", "aria-label": "Edit " + f.path });
      ta.value = state.editDraft !== null ? state.editDraft : f.content;
      ta.addEventListener("input", () => { state.editDraft = ta.value; });
      fill(box,
        el("div", { class: "viewer-head" }, el("span", { class: "path", text: "Editing " + f.path }),
          el("button", { onclick: () => { state.editing = false; state.editDraft = null; renderViewer(); } }, "Cancel"),
          el("button", { class: "primary", onclick: async () => {
            try {
              const proposal = await api("/api/changes", { method: "POST", body: { path: f.path, content: ta.value, source: "manual", note: "Edited in Jarvis" } });
              state.editing = false;
              state.editDraft = null;
              renderViewer();
              reviewProposal(proposal);
            } catch (err) { showError(err); }
          } }, "Review changes")),
        ta);
      ta.focus();
      return;
    }
    const pre = el("pre", { "aria-label": "Contents of " + f.path });
    const lines = f.content.split("\n");
    if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop(); // trailing newline isn't a line
    for (const line of lines) pre.append(el("span", { class: "ln" }, line || " "));
    fill(box, 
      el("div", { class: "viewer-head" }, el("span", { class: "path", title: f.path, text: f.path }),
        el("span", { class: "muted small", text: `${f.lines} lines` }),
        el("button", { class: "small", title: "Include this whole file with your next chat messages", onclick: () => { attachFile(f.path); toast(`Attached ${f.path} to the chat`, "ok"); } }, "Attach to chat"),
        el("button", { class: "small", onclick: () => {
          attachFile(f.path);
          setMode("explain");
          switchView("chat");
          sendMessage(`Explain what \`${f.path}\` does, step by step, for someone learning.`);
        } }, "Explain"),
        el("button", { class: "small", onclick: () => { fileRequest++; state.editing = true; state.editDraft = null; renderViewer(); } }, "Edit"),
        el("button", { class: "small ghost", title: "Delete this file (you'll confirm and can undo)", onclick: () => proposeDelete(f.path) }, "Delete\u2026")),
      pre);
  }

  // ---- commands tab
  function renderCommandsTab(box) {
    const presets = (state.project && state.project.presets) || [];
    const input = el("input", { type: "text", placeholder: "e.g. python -m pytest tests/test_app.py -q", "aria-label": "Command" });
    input.addEventListener("keydown", (e) => { if (e.key === "Enter" && input.value.trim()) openCommandDialog(input.value.trim()); });
    fill(box, 
      el("div", { class: "card" }, el("h3", { text: "Detected project commands" }),
        presets.length ? presets.map((p) => el("div", { class: "preset" },
          el("div", { class: "grow" },
            el("div", { class: "row" }, el("strong", { text: p.label }), el("code", { text: p.command }),
              el("span", { class: "badge " + p.level, text: p.level === "safe" ? "one click" : "asks first" })),
            el("div", { class: "muted small", text: p.explanation })),
          el("button", { class: p.level === "safe" ? "primary" : "", onclick: async () => {
            try {
              if (p.level === "safe") await startCommand(p.command, false, false);
              else openCommandDialog(p.command);
            } catch (err) { showError(err); }
          } }, "Run")))
          : el("p", { class: "muted", text: "No test or build commands detected. You can still run a command below." })),
      el("div", { class: "card stack" }, el("h3", { text: "Run another command" }),
        el("p", { class: "muted small", text: "Runs inside the project folder, without a shell (no pipes, redirects or &&). Jarvis explains the risk and asks for approval first." }),
        el("div", { class: "row" }, el("div", { class: "grow" }, input),
          el("button", { onclick: () => input.value.trim() && openCommandDialog(input.value.trim()) }, "Check & run\u2026"))),
      el("div", { class: "card" }, el("h3", { text: "Output" }), el("div", { id: "run-console" })));
    renderRunConsole();
  }

  // ---- changes tab
  async function renderChangesTab(box) {
    fill(box, el("p", { class: "muted", text: "Loading\u2026" }));
    let list;
    try { list = await api("/api/changes"); } catch (err) { return showError(err); }
    const order = { pending: 0, applied: 1 };
    list.sort((a, b) => (order[a.status] ?? 2) - (order[b.status] ?? 2) || b.id - a.id);
    fill(box, 
      el("p", { class: "muted small", text: "Every file change Jarvis makes goes through here. Pending changes wait for your decision; applied changes can be undone (the original is backed up)." }),
      list.length ? list.map((p) => el("button", { class: "change-item", onclick: () => reviewProposal(p) },
        el("span", { class: "badge " + p.status, text: p.status }),
        el("span", { class: "mono grow", text: `${p.kind} ${p.path}` }),
        p.warnings.length ? el("span", { class: "badge caution", text: `${p.warnings.length} warning${p.warnings.length > 1 ? "s" : ""}` }) : null,
        el("span", { class: "muted small", text: fmtTime(p.updated_at) }))) : el("div", { class: "empty", text: "No changes yet. Use \u201cPropose as file change\u201d on code in the chat, or Edit a file." }));
  }

  // ------------------------------------------------------------------ tasks
  const PRIORITIES = ["urgent", "high", "medium", "low"];
  const STATUSES = { todo: "To do", in_progress: "In progress", blocked: "Blocked", done: "Done" };

  async function loadTasks() {
    const status = $("#filter-status").value;
    const project = $("#filter-project").value;
    const showDone = $("#show-done").checked || status === "done";
    // Fetch everything (filtered client-side) so finished steps still count toward progress.
    const qs = new URLSearchParams({ include_done: "true" });
    if (project) qs.set("project", project);
    let tasks, projects;
    try {
      [tasks, projects] = await Promise.all([api("/api/tasks?" + qs), api("/api/tasks/projects")]);
    } catch (err) { return showError(err); }
    const sel = $("#filter-project");
    const current = sel.value;
    fill(sel, el("option", { value: "" }, "All projects"), ...projects.map((p) => el("option", { value: p }, p)));
    sel.value = projects.includes(current) ? current : "";
    renderTaskList(tasks, (t) => (status ? t.status === status : showDone || t.status !== "done"));
  }

  function renderTaskList(tasks, matches) {
    const ul = $("#task-list");
    const byId = new Map(tasks.map((t) => [t.id, t]));
    const children = {};
    for (const t of tasks) if (t.parent_id && byId.has(t.parent_id)) (children[t.parent_id] = children[t.parent_id] || []).push(t);
    for (const k in children) children[k].sort((a, b) => a.position - b.position);
    // A matching task is listed at the top level unless its parent is listed (then it appears nested,
    // together with its finished siblings so progress is visible).
    const top = tasks.filter((t) => matches(t) && !(t.parent_id && byId.has(t.parent_id) && matches(byId.get(t.parent_id))));
    if (!top.length) {
      fill(ul, el("li", { class: "empty" }, "No tasks here yet. Click \u201c+ New task\u201d to add one."));
      return;
    }
    fill(ul, ...top.map((t) => taskItem(t, children)));
  }

  function taskItem(t, children, parent) {
    const done = t.status === "done";
    const due = dueInfo(t.due_date, done);
    const subs = children[t.id] || [];
    const doneCount = subs.filter((s) => s.status === "done").length;
    const box = el("input", { type: "checkbox", "aria-label": "Mark done: " + t.title, checked: done });
    box.addEventListener("change", () => updateTask(t.id, { status: box.checked ? "done" : "todo" }));
    return el("li", { class: "task" + (done ? " done" : "") }, box,
      el("div", { class: "task-main" },
        el("div", { class: "task-title", text: t.title }),
        el("div", { class: "task-meta" },
          !parent || parent.priority !== t.priority ? el("span", { class: "badge " + t.priority, text: t.priority }) : null,
          t.status !== "todo" && !done ? el("span", { class: "badge " + t.status, text: STATUSES[t.status] }) : null,
          due ? el("span", { class: "due " + due.cls, text: due.text }) : null,
          t.project ? el("span", { text: "\uD83D\uDCC1 " + t.project }) : null,
          !parent && t.area ? el("span", { class: "badge area-" + t.area, text: t.area === "study" ? "Studying" : "Developing" }) : null,
          subs.length ? el("span", { text: `${doneCount}/${subs.length} steps done` }) : null,
          t.notes ? el("span", { title: t.notes, text: "\uD83D\uDCDD notes" }) : null),
        t.description ? el("div", { class: "task-desc", text: t.description.length > 220 ? t.description.slice(0, 220) + "\u2026" : t.description }) : null,
        subs.length ? el("ul", { class: "subtasks" }, subs.map((s) => taskItem(s, children, t))) : null),
      el("div", { class: "task-actions" },
        !t.parent_id ? el("button", { class: "ghost small", title: "Ask the local model to split this into smaller steps", onclick: (e) => breakDown(t, e.currentTarget) }, "Break down") : null,
        el("button", { class: "ghost small", onclick: () => openTaskEditor(t) }, "Edit"),
        el("button", { class: "ghost small", "aria-label": "Delete " + t.title, onclick: async () => {
          if (!(await confirmDialog({ title: "Delete task?", message: `"${t.title}"${subs.length ? ` and its ${subs.length} step(s)` : ""} will be deleted.`, confirmLabel: "Delete", danger: true }))) return;
          try { await api(`/api/tasks/${t.id}`, { method: "DELETE" }); loadTasks(); } catch (err) { showError(err); }
        } }, "\u2715")));
  }

  async function updateTask(id, changes) {
    try { await api(`/api/tasks/${id}`, { method: "PATCH", body: changes }); loadTasks(); } catch (err) { showError(err); loadTasks(); }
  }

  function openTaskEditor(task) {
    const t = task || { title: "", description: "", due_date: "", priority: "medium", status: "todo", project: "", notes: "", project_path: "", area: "" };
    const f = {
      title: el("input", { type: "text", value: t.title, maxlength: "300" }),
      description: el("textarea", { rows: 3 }),
      due_date: el("input", { type: "date", value: t.due_date || "" }),
      priority: el("select", {}, PRIORITIES.map((p) => el("option", { value: p, selected: p === t.priority }, p[0].toUpperCase() + p.slice(1)))),
      status: el("select", {}, Object.entries(STATUSES).map(([k, v]) => el("option", { value: k, selected: k === t.status }, v))),
      project: el("input", { type: "text", value: t.project, list: "task-project-list", placeholder: "Optional label, e.g. Website" }),
      area: el("select", { title: "Counts this task under Studying or Developing in Progress" },
        [["", "Not set"], ["study", "Studying"], ["dev", "Developing"]].map(([v, l]) => el("option", { value: v, selected: v === (t.area || "") }, l))),
      notes: el("textarea", { rows: 4 }),
    };
    f.description.value = t.description || "";
    f.notes.value = t.notes || "";
    const datalist = el("datalist", { id: "task-project-list" }, $$("#filter-project option").filter((o) => o.value).map((o) => el("option", { value: o.value })));
    const proj = state.status && state.status.project;
    const link = el("input", { type: "checkbox", checked: !!t.project_path });
    const body = el("div", { class: "stack" }, datalist,
      el("label", { class: "field" }, el("span", { text: "Title" }), f.title),
      el("label", { class: "field" }, el("span", { text: "Description" }), f.description),
      el("div", { class: "grid2" },
        el("label", { class: "field" }, el("span", { text: "Due date" }), f.due_date),
        el("label", { class: "field" }, el("span", { text: "Priority" }), f.priority),
        el("label", { class: "field" }, el("span", { text: "Status" }), f.status),
        el("label", { class: "field" }, el("span", { text: "Project" }), f.project),
        el("label", { class: "field" }, el("span", { text: "Area (for Progress)" }), f.area)),
      proj && proj.open ? el("label", { class: "check small" }, link, `Link to the open project folder (${proj.name})`) :
        t.project_path ? el("p", { class: "muted small", text: "Linked folder: " + t.project_path }) : null,
      el("label", { class: "field" }, el("span", { text: "Notes" }), f.notes));
    openModal({
      title: task ? "Edit task" : "New task", body,
      actions: [
        { label: "Cancel" },
        { label: task ? "Save" : "Add task", kind: "primary", onClick: async () => {
          const data = {
            title: f.title.value.trim(), description: f.description.value, due_date: f.due_date.value || null,
            priority: f.priority.value, status: f.status.value, project: f.project.value.trim(), notes: f.notes.value,
            area: f.area.value || (f.project.value.trim() ? "dev" : ""),
          };
          if (!data.title) { toast("Give the task a title.", "error"); return true; }
          if (proj && proj.open) {
            data.project_path = link.checked ? proj.root : "";
            if (link.checked && !data.project) data.project = proj.name;
          }
          if (task) await api(`/api/tasks/${task.id}`, { method: "PATCH", body: data });
          else await api("/api/tasks", { method: "POST", body: data });
          loadTasks();
        } },
      ],
    });
  }

  async function breakDown(task, btn) {
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Thinking\u2026";
    let result;
    try {
      result = await api(`/api/tasks/${task.id}/breakdown`, { method: "POST" });
    } catch (err) {
      showError(err);
      return;
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
    const rows = result.steps.map((s) => ({ check: el("input", { type: "checkbox", checked: true }), title: el("input", { type: "text", value: s.title }), desc: el("textarea", { rows: 2 }, s.description) }));
    const body = el("div", { class: "stack" },
      el("p", { class: "muted small", text: "Suggested by the local model, in a practical order. Edit or untick steps before adding them." }),
      result.notes ? el("div", { class: "notice info small", text: result.notes }) : null,
      el("ol", { class: "steps-edit" }, rows.map((r) => el("li", {}, r.check, el("div", { class: "grow" }, r.title, r.desc)))));
    openModal({
      title: "Steps for: " + task.title, body, wide: true,
      actions: [
        { label: "Cancel" },
        { label: "Add selected steps", kind: "primary", onClick: async () => {
          const steps = rows.filter((r) => r.check.checked && r.title.value.trim()).map((r) => ({ title: r.title.value.trim(), description: r.desc.value }));
          if (!steps.length) { toast("Select at least one step.", "error"); return true; }
          await api(`/api/tasks/${task.id}/subtasks`, { method: "POST", body: { steps } });
          toast(`Added ${steps.length} steps`, "ok");
          loadTasks();
        } },
      ],
    });
  }

  async function planTasks(btn) {
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Thinking\u2026";
    try {
      const project = $("#filter-project").value;
      const plan = await api("/api/tasks/plan" + (project ? "?project=" + encodeURIComponent(project) : ""), { method: "POST" });
      const box = $("#plan-box");
      box.hidden = false;
      fill(box, el("div", { class: "card plan-box", style: "margin-bottom:14px" },
        el("div", { class: "row" }, el("h3", { text: "Suggested order" }), el("span", { class: "spacer" }), el("button", { class: "ghost small", onclick: () => { box.hidden = true; } }, "Close")),
        plan.advice ? el("p", { text: plan.advice }) : null,
        plan.order.length ? el("ol", {}, plan.order.map((o) => el("li", {}, el("strong", { text: o.title }), o.reason ? " \u2014 " + o.reason : ""))) : el("p", { class: "muted", text: "No open tasks." }),
        el("p", { class: "muted small", text: "This is a suggestion from the local model; it doesn't change your tasks." })));
    } catch (err) {
      showError(err);
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
  }

  async function showStandup() {
    let note;
    try { note = await api("/api/learn/standup"); } catch (err) { return showError(err); }
    const box = el("textarea", { class: "standup-text", rows: "14", "aria-label": "Stand-up note" });
    box.value = note.text;
    openModal({
      title: "Stand-up note",
      body: el("div", { class: "stack" },
        el("p", { class: "muted small", text: "Drafted from your tasks: what you finished since the last working day, what's in progress or due, and what's blocked. Edit it, then copy it into your team chat." }),
        box),
      actions: [{ label: "Close" }, { label: "Copy", kind: "primary", onClick: async () => {
        try { await navigator.clipboard.writeText(box.value); toast("Copied", "ok"); }
        catch (_) { box.select(); document.execCommand("copy"); toast("Copied", "ok"); }
        return true;
      } }],
    });
  }

  async function exportTasks() {
    try {
      const res = await api("/api/tasks/export", { raw: true });
      if (!res.ok) throw apiError(res.status, await res.json().catch(() => null));
      const blob = await res.blob();
      const a = el("a", { href: URL.createObjectURL(blob), download: `jarvis-tasks-${new Date().toISOString().slice(0, 10)}.json` });
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (err) { showError(err); }
  }

  // ------------------------------------------------------------------ activity
  async function loadActivity() {
    let items;
    try { items = await api("/api/activity?scope=" + state.activityScope); } catch (err) { return showError(err); }
    const box = $("#activity-list");
    if (!items.length) { fill(box, el("div", { class: "empty", text: "Nothing recorded yet." })); return; }
    fill(box, el("table", { class: "log" },
      el("thead", {}, el("tr", {}, el("th", { text: "When" }), el("th", { text: "What" }), el("th", { text: "Details" }))),
      el("tbody", {}, items.map((a) => el("tr", {},
        el("td", { class: "when", text: fmtTime(a.created_at) }),
        el("td", {}, el("div", { text: a.summary }), el("span", { class: "badge", text: a.kind.replace(/_/g, " ") })),
        el("td", {}, Object.keys(a.details || {}).length ? el("details", {}, el("summary", { text: "show" }), el("pre", { text: JSON.stringify(a.details, null, 2) })) : null))))));
  }

  // ------------------------------------------------------------------ settings
  async function loadSettings() {
    const data = await api("/api/settings");
    state.settings = data.settings;
    state.paths = data.paths;
    state.detail = state.settings.detail;
    for (const b of $$("[data-detail]")) b.setAttribute("aria-pressed", String(b.dataset.detail === state.detail));
  }

  async function renderSettings() {
    try { await loadSettings(); await refreshStatus(); } catch (err) { return showError(err); }
    const s = state.settings;
    const m = state.status.model;
    const page = $("#settings-page");
    const F = {};
    const input = (key, attrs) => (F[key] = el("input", Object.assign({ value: s[key] }, attrs)));
    const check = (key) => (F[key] = el("input", { type: "checkbox", checked: s[key] }));
    F.provider = el("select", {}, el("option", { value: "ollama", selected: s.provider === "ollama" }, "Ollama"),
      el("option", { value: "openai_compatible", selected: s.provider === "openai_compatible" }, "OpenAI-compatible server (llama.cpp, LM Studio\u2026)"));
    const installed = m.models || [];
    F.model = el("select", {}, el("option", { value: "" }, "Automatic (best installed model)"),
      installed.map((x) => el("option", { value: x.name, selected: x.name === s.model }, `${x.name}${x.parameter_size ? " \u00B7 " + x.parameter_size : ""}${x.size_bytes ? " \u00B7 " + fmtBytes(x.size_bytes) : ""}`)));
    const customModel = el("input", { type: "text", placeholder: "or type a model name", value: s.model && !installed.some((x) => x.name === s.model) ? s.model : "" });
    const chatModels = installed.filter((x) => !/embed/i.test(x.name));
    const seeing = installed.filter((x) => (x.capabilities || []).includes("vision"));
    F.vision_model = el("select", {}, el("option", { value: "" }, `Automatic${m.vision_model ? " (" + m.vision_model + ")" : " (none installed)"}`),
      seeing.map((x) => el("option", { value: x.name, selected: x.name === s.vision_model }, x.name)));
    F.code_model = el("select", {}, el("option", { value: "" }, "Same as above"),
      chatModels.map((x) => el("option", { value: x.name, selected: x.name === s.code_model }, x.name)),
      s.code_model && !chatModels.some((x) => x.name === s.code_model) ? el("option", { value: s.code_model, selected: true }, s.code_model + " (not installed)") : null);
    F.extra_exclude_patterns = el("textarea", { rows: 3, placeholder: "One pattern per line, e.g. private/*  or  *.sqlite" });
    F.extra_exclude_patterns.value = (s.extra_exclude_patterns || []).join("\n");
    F.detail = el("select", {}, el("option", { value: "concise", selected: s.detail === "concise" }, "Concise"), el("option", { value: "detailed", selected: s.detail === "detailed" }, "Detailed"));
    const maxKb = el("input", { type: "number", min: "10", max: "5000", value: Math.round(s.max_file_bytes / 1000) });
    F.provider.addEventListener("change", () => {
      const ep = F.endpoint.value.trim();
      if (F.provider.value === "openai_compatible" && ep === "http://127.0.0.1:11434") F.endpoint.value = "http://127.0.0.1:8080/v1";
      if (F.provider.value === "ollama" && ep === "http://127.0.0.1:8080/v1") F.endpoint.value = "http://127.0.0.1:11434";
    });
    const voices = localVoices();

    async function save(quiet) {
      const changes = {
        provider: F.provider.value,
        endpoint: F.endpoint.value.trim(),
        model: customModel.value.trim() || F.model.value,
        code_model: F.code_model.value,
        vision_model: F.vision_model.value,
        daily_backup: F.daily_backup.checked,
        semantic_search: F.semantic_search.checked,
        temperature: parseFloat(F.temperature.value),
        context_window: parseInt(F.context_window.value, 10),
        think: F.think.checked,
        request_timeout: parseInt(F.request_timeout.value, 10),
        allow_remote_endpoint: F.allow_remote_endpoint.checked,
        detail: F.detail.value,
        max_context_chars: parseInt(F.max_context_chars.value, 10),
        max_file_bytes: parseInt(maxKb.value, 10) * 1000,
        max_index_files: parseInt(F.max_index_files.value, 10),
        extra_exclude_patterns: F.extra_exclude_patterns.value.split("\n").map((x) => x.trim()).filter(Boolean),
        command_timeout: parseInt(F.command_timeout.value, 10),
        voice_output: F.voice_output.checked,
      };
      if (changes.allow_remote_endpoint && !s.allow_remote_endpoint) {
        const ok = await confirmDialog({
          title: "Allow a non-local model server?", danger: true, confirmLabel: "Allow",
          message: "If the endpoint is on another computer, your prompts, code and file excerpts will be sent to it over the network. Only do this for a machine you control.",
          check: "I understand my data will leave this computer",
        });
        if (!ok) { F.allow_remote_endpoint.checked = false; return; }
      }
      await api("/api/settings", { method: "PUT", body: changes });
      await loadSettings();
      await refreshStatus();
      if (!quiet) toast("Settings saved", "ok");
    }

    fill(page, 
      el("div", { class: "page-head" }, el("h2", { text: "Settings" }), el("span", { class: "spacer" }),
        el("button", { class: "primary", onclick: async () => { try { await save(); renderSettings(); } catch (err) { showError(err); } } }, "Save settings")),
      el("div", { class: "card settings-section" }, el("h3", { text: "Local model" }),
        el("div", { class: "notice " + (m.state === "ready" ? "ok" : "warn"), style: "margin-bottom:12px" },
          el("strong", { text: m.message }), m.hint ? el("div", { class: "small", text: m.hint }) : null,
          m.version ? el("div", { class: "small muted", text: "Server version " + m.version }) : null),
        el("div", { class: "stack" },
          el("div", { class: "grid2" },
            el("label", { class: "field" }, el("span", { text: "Model server type" }), F.provider),
            el("label", { class: "field" }, el("span", { text: "Server address (endpoint)" }), input("endpoint", { type: "text" }),
              el("small", { text: "Ollama: http://127.0.0.1:11434 · llama.cpp: http://127.0.0.1:8080/v1" }))),
          el("label", { class: "field" }, el("span", { text: "Model" }), el("div", { class: "row" }, el("div", { class: "grow" }, F.model), el("div", { class: "grow" }, customModel)),
            el("small", { text: "Bigger models give better answers but need more memory and are slower. See Help for suggestions." })),
          el("label", { class: "field" }, el("span", { text: "Model for Implementation and Testing & debugging" }), F.code_model,
            el("small", { text: "Optional: a model that is better at code (for example qwen2.5-coder:7b) for those two modes. Measure with: python evals/run_eval.py" })),
          el("label", { class: "field" }, el("span", { text: "Model for pictures (image recognition)" }), F.vision_model,
            el("small", { text: "Used when you attach a photo or screenshot. Needs a model that can see, e.g. gemma3:4b or qwen3-vl:2b." })),
          el("div", { class: "grid2" },
            el("label", { class: "field" }, el("span", { text: "Creativity (temperature)" }), input("temperature", { type: "number", step: "0.1", min: "0", max: "2" }),
              el("small", { text: "0.2–0.4 is good for code; higher is more varied." })),
            el("label", { class: "field" }, el("span", { text: "Context size (tokens)" }), input("context_window", { type: "number", step: "1024", min: "1024", max: "262144" }),
              el("small", { text: "How much text the model sees at once. Larger uses more memory." })),
            el("label", { class: "field" }, el("span", { text: "Model response timeout (seconds)" }), input("request_timeout", { type: "number", min: "10", max: "7200" })),
            el("label", { class: "field" }, el("span", { text: "Default answer length" }), F.detail)),
          el("label", { class: "check" }, check("think"), "Let \u201Cthinking\u201D models reason before answering (slower; only for models that support it)"),
          el("label", { class: "check" }, check("allow_remote_endpoint"), "Allow a model server that is not on this computer (not recommended)"),
          el("div", { class: "row" }, el("button", { onclick: async (e) => {
            const b = e.currentTarget; b.disabled = true;
            try { await save(true); toast(state.status.model.message, state.status.model.state === "ready" ? "ok" : "error", state.status.model.hint); renderSettings(); }
            catch (err) { showError(err); } finally { b.disabled = false; }
          } }, "Save & test connection")))),
      el("div", { class: "card settings-section" }, el("h3", { text: "Project access" }),
        el("div", { class: "stack" },
          el("label", { class: "check" }, check("semantic_search"), "Search by meaning as well as keywords (needs the nomic-embed-text model: ollama pull nomic-embed-text)"),
          el("label", { class: "field" }, el("span", { text: "Extra files/folders to hide from Jarvis" }), F.extra_exclude_patterns,
            el("small", { text: "Added to the built-in list (.env, keys, credentials\u2026). Wildcards: * and ?." })),
          el("div", { class: "grid2" },
            el("label", { class: "field" }, el("span", { text: "Max file size to read (KB)" }), maxKb),
            el("label", { class: "field" }, el("span", { text: "Max files to index" }), input("max_index_files", { type: "number", min: "50", max: "50000" })),
            el("label", { class: "field" }, el("span", { text: "Max project text per question (characters)" }), input("max_context_chars", { type: "number", min: "1000", max: "200000", step: "1000" })),
            el("label", { class: "field" }, el("span", { text: "Command time limit (seconds)" }), input("command_timeout", { type: "number", min: "5", max: "7200" }))))),
      el("div", { class: "card settings-section" }, el("h3", { text: "Voice (optional)" }),
        el("label", { class: "check" }, check("voice_output"), "Show a \u201CRead aloud\u201D button on answers"),
        el("p", { class: "muted small", style: "margin-top:6px", text: voices.length
          ? `${voices.length} offline voice(s) available. Jarvis only uses voices that run on this computer.`
          : "No offline voices detected in this browser, so reading aloud won't be available. Jarvis never uses online voices." }),
        el("p", { class: "muted small", text: "Voice input is not included: the browser's speech recognition sends audio to online services, which Jarvis avoids." })),
      el("div", { class: "card settings-section", id: "phone-card" }),
      window.JarvisCompanion ? el("div", { class: "card settings-section", id: "companion-card" },
        el("h3", { "data-i18n": "set.title", text: window.JarvisI18n ? window.JarvisI18n.t("set.title") : "Study Buddy and encouragement" }),
        el("p", { class: "muted small", text: "Study Buddy, the check-in before you start, Coding Focus, and the Bible verse or quote shown when you open Jarvis. The look and check-in settings are saved in this browser, so the phone can have its own." }),
        window.JarvisCompanion.settingsCard()) : null,
      el("div", { class: "card settings-section", id: "reliability-card" }, el("h3", { text: "Reliability" }),
        el("div", { class: "stack" },
          el("label", { class: "check" }, check("daily_backup"), "Back up my tasks, flashcards and chats every day (keeps the last 7 days)"),
          el("div", { id: "autostart-row" }))),
      el("div", { class: "card settings-section" }, el("h3", { text: "Your data" }),
        el("p", { text: "Everything Jarvis stores lives in one folder on this computer:" }),
        el("dl", { class: "paths" },
          el("dt", { text: "Data folder" }), el("dd", { text: state.paths.data_dir }),
          el("dt", { text: "Settings file" }), el("dd", { text: state.paths.config }),
          el("dt", { text: "Tasks, chats and activity (SQLite database)" }), el("dd", { text: state.paths.database }),
          el("dt", { text: "Backups of files Jarvis changed" }), el("dd", { text: state.paths.backups }),
          el("dt", { text: "Log files" }), el("dd", { text: state.paths.logs })),
        el("ul", { class: "small" },
          el("li", {}, el("strong", { text: "Back up: " }), "close Jarvis, then copy the whole data folder somewhere safe."),
          el("li", {}, el("strong", { text: "Remove all Jarvis data: " }), "close Jarvis, then delete the data folder. Your project folders are not affected.")),
        el("button", { onclick: exportTasks }, "Export tasks as JSON")));
    renderPhoneCard();
    renderAutostart();
  }

  async function renderAutostart() {
    const box = $("#autostart-row");
    if (!box) return;
    let info;
    try { info = await api("/api/system/autostart"); } catch (err) { return; }
    if (!info.supported) { fill(box, el("p", { class: "muted small", text: "Starting automatically is only available on Windows." })); return; }
    const toggle = el("input", { type: "checkbox", checked: info.enabled });
    toggle.addEventListener("change", async () => {
      toggle.disabled = true;
      try {
        const r = await api("/api/system/autostart", { method: "PUT", body: { enabled: toggle.checked } });
        toast(r.enabled ? "Jarvis will start quietly when you sign in to Windows" : "Jarvis won't start automatically any more", "ok");
      } catch (err) { showError(err); }
      renderAutostart();
    });
    fill(box, el("label", { class: "check" }, toggle, "Start Jarvis automatically when I sign in to Windows (runs quietly in the background, so your phone can always reach it)"));
  }

  // ------------------------------------------------------------------ phone access (mobile app)
  async function renderPhoneCard() {
    const card = $("#phone-card");
    if (!card) return;
    let info;
    try { info = await api("/api/phone"); } catch (err) { return showError(err); }
    const toggle = el("input", { type: "checkbox", checked: info.enabled });
    const port = el("input", { type: "number", min: "1024", max: "65535", value: state.settings.phone_port, style: "width:120px" });
    async function apply(changes) {
      toggle.disabled = true;
      try {
        await api("/api/settings", { method: "PUT", body: changes });
        await loadSettings();
        await refreshStatus();
      } catch (err) { showError(err); }
      renderPhoneCard();
    }
    toggle.addEventListener("change", () => apply({ phone_access: toggle.checked, phone_port: parseInt(port.value, 10) }));
    let status;
    if (info.running) {
      status = el("div", { class: "notice ok stack" },
        el("strong", { text: "Phone access is on." }),
        el("div", {}, "On your phone (on the same Wi-Fi), open:",
          el("ul", {}, info.urls.map((u) => el("li", {}, el("code", { text: u }), " ",
            el("button", { class: "small ghost", onclick: () => copyText(u) }, "Copy"))))),
        el("div", { class: "row" }, el("button", { class: "primary", onclick: openPairDialog }, "Pair a phone"),
          el("span", { class: "muted small", text: "You'll get a one-time code to type on the phone." })));
    } else if (info.enabled) {
      status = el("div", { class: "notice bad" }, el("strong", { text: "Phone access couldn't start. " }), info.error || "Unknown error.");
    } else {
      status = el("p", { class: "muted small", text: "Off: nothing on your network can reach Jarvis." });
    }
    fill(card, el("h3", { text: "Phone access (mobile app)" }),
      el("div", { class: "stack" },
        el("p", { class: "small", text: "Use Jarvis from your phone over your home Wi-Fi: chat (including about the open project) and manage tasks. File changes, commands and settings stay on this computer." }),
        el("label", { class: "check" }, toggle, "Let my phone connect over my home Wi-Fi"),
        el("div", { class: "row" }, el("span", { class: "small", text: "Phone port" }), port,
          el("button", { class: "small", onclick: () => apply({ phone_port: parseInt(port.value, 10) }) }, "Apply")),
        status,
        info.devices.length ? el("div", {}, el("strong", { class: "small", text: "Paired phones" }),
          el("ul", { class: "small", style: "list-style:none;padding:0;margin:6px 0 0" }, info.devices.map((d) => el("li", { class: "row", style: "padding:4px 0" },
            el("span", { class: "grow" }, el("strong", { text: d.name }), ` · paired ${fmtTime(d.created_at)} · last used ${fmtTime(d.last_seen)}`),
            el("button", { class: "small", onclick: async () => {
              if (!(await confirmDialog({ title: "Remove this phone?", message: `"${d.name}" will no longer be able to use Jarvis until it is paired again.`, confirmLabel: "Remove", danger: true }))) return;
              try { await api(`/api/phone/devices/${d.id}`, { method: "DELETE" }); } catch (err) { showError(err); }
              renderPhoneCard();
            } }, "Remove"))))) : null,
        el("ul", { class: "small muted" },
          el("li", { text: "The first time, Windows may ask whether Python may use the network. Choose “Private networks”." }),
          el("li", { text: "The connection is encrypted. Your phone warns about the certificate the first time because this computer created it, not a public authority. That's expected." }),
          info.fingerprint ? el("li", {}, "Certificate fingerprint (SHA-256): ", el("code", { style: "word-break:break-all", text: info.fingerprint })) : null,
          el("li", { text: "If your computer's network address changes, open the new address on the phone and pair again." }))));
  }

  async function openPairDialog() {
    let code, before;
    try {
      before = await api("/api/phone");
      code = await api("/api/phone/pairing-code", { method: "POST" });
    } catch (err) { return showError(err); }
    const known = new Set(before.devices.map((d) => d.id));
    let paired = false;
    const countdown = el("p", { class: "muted small" });
    const body = el("div", { class: "stack" },
      el("ol", {},
        el("li", {}, "On your phone, open ", el("code", { text: before.urls[0] || "" }),
          before.urls.length > 1 ? el("span", { class: "muted small", text: ` (or ${before.urls.slice(1).join(", ")})` }) : null),
        el("li", { text: "The first time, the browser says the connection isn't private. That's expected: tap Advanced → Proceed (Android) or Show Details → visit this website (iPhone)." }),
        el("li", { text: "Type this code in the Jarvis page on your phone:" })),
      el("div", { class: "pair-code", "aria-label": "Pairing code " + code.code.split("").join(" ") }, code.code.slice(0, 3) + " " + code.code.slice(3)),
      countdown);
    let left = code.seconds_left;
    const tick = setInterval(() => {
      left -= 1;
      countdown.textContent = left > 0 ? `Code valid for ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}` : "Code expired. Close this and create a new one.";
    }, 1000);
    const poll = setInterval(async () => {
      try {
        const now = await api("/api/phone");
        const fresh = now.devices.find((d) => !known.has(d.id));
        if (fresh) {
          paired = true;
          clearInterval(poll);
          clearInterval(tick);
          fill(body, el("div", { class: "notice ok" }, el("strong", { text: `✓ Paired with “${fresh.name}”.` }),
            el("div", { class: "small", text: "Tip: on the phone, add Jarvis to the home screen so it opens like an app." })));
          modal.setActions([{ label: "Done", kind: "primary" }]);
          renderPhoneCard();
        }
      } catch (_) { /* keep trying */ }
    }, 1500);
    const modal = openModal({
      title: "Pair a phone", body,
      actions: [{ label: "Cancel" }],
      onClose: () => {
        clearInterval(poll);
        clearInterval(tick);
        if (!paired) api("/api/phone/pairing-code", { method: "DELETE" }).catch(() => {});
      },
    });
  }

  // ------------------------------------------------------------------ wiring
  function wire() {
    for (const b of $$(".sidenav button")) b.addEventListener("click", () => switchView(b.dataset.view));
    $("#model-pill").addEventListener("click", () => switchView(state.status && state.status.model.state === "ready" ? "settings" : "help"));
    $("#project-pill").addEventListener("click", () => switchView("project"));
    $("#phone-pill").addEventListener("click", () => switchView("settings"));
    $("#new-chat").addEventListener("click", newChat);
    $("#composer").addEventListener("submit", (e) => {
      e.preventDefault();
      const text = $("#prompt").value;
      if (!text.trim() || state.streaming) return;
      $("#prompt").value = "";
      autoGrow();
      sendMessage(text);
    });
    $("#prompt").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        $("#composer").requestSubmit();
      }
    });
    $("#prompt").addEventListener("input", autoGrow);
    $("#add-image").addEventListener("click", () => $("#image-input").click());
    $("#image-input").addEventListener("change", () => { addImages([...$("#image-input").files]); $("#image-input").value = ""; });
    $("#prompt").addEventListener("paste", (e) => {
      const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
      if (files.length) { e.preventDefault(); addImages(files); }
    });
    $("#composer").addEventListener("dragover", (e) => { if ([...e.dataTransfer.types].includes("Files")) e.preventDefault(); });
    $("#composer").addEventListener("drop", (e) => {
      const files = [...(e.dataTransfer?.files || [])].filter((f) => f.type.startsWith("image/"));
      if (files.length) { e.preventDefault(); addImages(files); }
    });
    $("#stop").addEventListener("click", stopStreaming);
    $("#mode").addEventListener("change", () => {
      state.mode = $("#mode").value;
      $("#run-tests").checked = state.mode === "test"; // debugging works best from real test results
      $("#use-guides").checked = GUIDE_MODES.includes(state.mode);
      if (window.JarvisCompanion) window.JarvisCompanion.setContext({ view: "chat", mode: state.mode });
    });
    for (const b of $$("[data-detail]")) b.addEventListener("click", () => {
      state.detail = b.dataset.detail;
      for (const x of $$("[data-detail]")) x.setAttribute("aria-pressed", String(x === b));
    });
    $("#new-task").addEventListener("click", () => openTaskEditor(null));
    $("#plan-tasks").addEventListener("click", (e) => planTasks(e.currentTarget));
    $("#export-tasks").addEventListener("click", exportTasks);
    $("#standup").addEventListener("click", showStandup);
    for (const id of ["#filter-status", "#filter-project", "#show-done"]) $(id).addEventListener("change", loadTasks);
    for (const b of $$("[data-scope]")) b.addEventListener("click", () => {
      state.activityScope = b.dataset.scope;
      for (const x of $$("[data-scope]")) x.setAttribute("aria-pressed", String(x === b));
      loadActivity();
    });
    $("#refresh-activity").addEventListener("click", loadActivity);
    window.addEventListener("focus", refreshStatus);
  }

  window.JarvisUI = { el, fill, api, openModal, confirmDialog, toast, showError, TOKEN, askInChat, switchView };

  async function init() {
    wire();
    renderWelcome();
    try { await loadSettings(); } catch (err) { showError(err); }
    await refreshStatus();
    loadConversations();
    setInterval(refreshStatus, 20000);
    if (window.JarvisCompanion) {
      const store = {
        get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
        set(k, v) { try { localStorage.setItem(k, v); } catch (_) { /* storage blocked */ } },
      };
      window.JarvisCompanion.mount({ api, store, place: "desktop", navigate(target, message) {
        if (target === "review") switchView("study");
        else if (target === "practice") { switchView("learn"); if (window.JarvisLearn) window.JarvisLearn.openTab("practice"); }
        else if (target === "progress") switchView("progress");
        else if (target === "toast") toast(message, "ok");
        else if (target === "coach") askInChat(`My check-in today: ${message}\n\nHelp me plan a realistic study and coding session for how I feel right now.`, "coach");
        else switchView("chat");
      } });
      if (window.JarvisI18n) window.JarvisI18n.onChange(() => { if (state.view === "build") switchView("build"); });
    }
  }

  init();
})();
