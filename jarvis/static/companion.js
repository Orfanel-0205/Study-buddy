/* Study Buddy: the floating companion, the check-in before you start, focus sessions (sessions.js), and
 * the word of encouragement when Jarvis opens. Shared by the computer page and the phone app.
 *   JarvisCompanion.mount({ api, store, navigate, place: "desktop" | "phone", native })
 * Her art is the original sticker poses, plus frames made from them (tools/make_brand_assets.py): eyes
 * half and fully closed (she blinks), a relaxed closed-eye pose, and a pouty face. The motion is made
 * around them: breathing, a sway, head tilts and nods, a typing bob, a hop when her expression changes,
 * a tilt while you drag her, a squash when she lands, and small effects (sparkles, an anger mark, z's).
 *
 * Her states follow Jarvis's own: idle, a coding session, a study session, a break, a session gone
 * quiet (a short pout and one reminder, then calm), and a finished session (a small celebration).
 * Works offline: the session runs on the device, and her pictures are in the offline copy. */
(function (root) {
  "use strict";

  const BASE = "/static/companion/";
  const PREFS_KEY = "jarvis.companion";
  const T = (k, v) => (root.JarvisI18n ? root.JarvisI18n.t(k, v) : k);
  const DEFAULTS = { enabled: true, pack: "study-buddy-2", size: "m", tips: true, word: "open", kinds: "both", focus: "",
    checkin: "daily", pos: null, recent: [], lastWordDay: "", lastCheckinDay: "", wellbeing: "", wellbeingDay: "",
    grace: 5, cooldown: 15, sessionMinutes: 25, pending: [] };
  const STUDY_MODES = ["study", "explain", "coach"];
  const CODE_MODES = ["implement", "test", "design", "requirements", "rules", "release", "stack"];
  const FX = { celebrate: "sparkle", cheer: "sparkle", pouty: "anger", sleepy: "zzz", code: "code", care: "heart", idea: "think", relax: "music" };
  const REDUCED = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  let host = null, prefs = { ...DEFAULTS }, packs = [], ctx = {}, root$ = null, pet = null, bubble = null, panel = null;
  let imgA = null, imgB = null, half$ = null, shut$ = null, fx = null, react$ = null, current = "", override = null, overrideUntil = 0;
  let bubbleTimer = 0, activeSince = Date.now(), engine = null, sessionTimer = 0, lastSaid = 0;
  let focusState = null, lastAlertId = null, focusPoll = 0, tiltTimer = 0, blinkTimer = 0, nodTimer = 0, currentItem = null;

  function h(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat(Infinity)) if (c !== null && c !== undefined && c !== false) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    return node;
  }
  /** replaceChildren without the nulls (replaceChildren(null) would print the word "null"). */
  const fillNode = (node, ...kids) => node.replaceChildren(...kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
  const today = () => new Date().toLocaleDateString("en-CA");

  function loadPrefs() {
    const phone = host.place === "phone" ? { size: "s" } : {};
    try { prefs = { ...DEFAULTS, ...phone, ...JSON.parse(host.store.get(PREFS_KEY) || "{}") }; } catch (_) { prefs = { ...DEFAULTS, ...phone }; }
    if (prefs.pack === "robot") prefs.pack = DEFAULTS.pack; // the robot companion was retired
  }
  function savePrefs() { try { host.store.set(PREFS_KEY, JSON.stringify(prefs)); } catch (_) { /* storage blocked */ } }

  function currentPack() { return packs.find((p) => p.id === prefs.pack) || packs[0]; }
  /** still: a picture that has to work without the animated effects (cards, notifications, reduced motion). */
  function itemFor(pose, still) {
    const pack = currentPack();
    if (!pack) return null;
    const order = { celebrate: ["celebrate", "cheer"], cheer: ["cheer", "celebrate"], sleepy: ["sleepy"], code: ["code"],
      study: ["study", "idea"], idea: ["idea", "study"], pouty: ["pouty", "code"], care: ["cheer", "idea"],
      relax: ["relax", "sleepy"] }[pose] || [pose, "study"];
    for (const want of order) { const it = pack.items.find((i) => i.mood === want); if (it) return it; }
    return pack.items[0];
  }
  /** The pictures for the floating pet: pouty uses her plain face, because the pet draws its own pulsing
   * anger mark (sb-p-anger); cards and notifications use the sticker with the mark drawn in. */
  function framesFor(item) {
    const animated = item.plain && !REDUCED;
    return { open: animated ? item.plain : item.file, half: animated ? null : item.half || null,
      shut: animated ? item.plain_blink || null : item.blink || null };
  }

  // ------------------------------------------------------------------ which expression, right now
  function poseNow() {
    const now = Date.now();
    if (override && now < overrideUntil) return override;
    const st = engine ? engine.state() : { session: null, breakLeft: 0 };
    if (st.breakLeft > 0) return "relax";
    if (st.session) {
      if (st.pouting) return "pouty";
      return st.session.kind === "study" || st.session.paused ? "study" : "code";
    }
    if (focusState && focusState.state === "distracted") return "pouty";
    if (ctx.thinking) return "idea";
    const hr = new Date().getHours();
    if (hr >= 23 || hr < 5) return "sleepy";
    if (ctx.view === "study" || (ctx.view === "learn" && ctx.tab === "guides") || STUDY_MODES.includes(ctx.mode)) return "study";
    if (ctx.view === "project" || (ctx.view === "learn" && ["practice", "lab", "charts"].includes(ctx.tab)) || ctx.view === "build" || CODE_MODES.includes(ctx.mode)) return "code";
    if (focusState && focusState.state === "coding") return "code";
    if (ctx.view === "progress") return "cheer";
    return "study";
  }

  /** How she moves: a session (typing, or writing with nods), a break, or idle. */
  function modeNow(pose) {
    const st = engine ? engine.state() : { session: null, breakLeft: 0 };
    if (pose === "pouty" || pose === "celebrate" || pose === "idea" || pose === "sleepy") return pose;
    if (st.breakLeft > 0 || pose === "relax") return "relax";
    if (st.session && !st.session.paused) return st.session.kind === "study" ? "studying" : "coding";
    return "idle";
  }

  function refresh() {
    const pose = poseNow();
    if (root$) root$.dataset.mode = modeNow(pose);
    if (pose === current || !imgA) return;
    const item = itemFor(pose);
    if (!item) return;
    const first = !current;
    current = pose;
    currentItem = framesFor(item);
    // crossfade between two stacked pictures, then a little hop/pop
    const [show, hide] = imgA.classList.contains("on") ? [imgB, imgA] : [imgA, imgB];
    show.src = BASE + currentItem.open;
    // her blink frames for this picture, loaded before she needs them
    if (currentItem.half) half$.src = BASE + currentItem.half; else half$.removeAttribute("src");
    if (currentItem.shut) shut$.src = BASE + currentItem.shut; else shut$.removeAttribute("src");
    show.alt = "";
    show.onload = () => { show.classList.add("on"); hide.classList.remove("on"); };
    if (show.complete && show.naturalWidth) { show.classList.add("on"); hide.classList.remove("on"); }
    root$.dataset.pose = pose;
    pet.setAttribute("aria-label", `${T("sb.name")}: ${pose}. ${T("sb.quick")}`);
    if (!first) play(pose === "pouty" ? "sb-shake" : pose === "celebrate" ? "sb-jump" : "sb-pop");
    effect(FX[pose]);
    if (host.native && host.native.companionPose) { try { host.native.companionPose(prefs.pack, pose); } catch (_) { /* old app */ } }
    if (host.place === "desktop") reportPose(pose);
  }

  /** The Windows floating Study Buddy mirrors the page (jarvis/overlay.py asks the server). */
  let reported = "", reportedAt = 0;
  function reportPose(pose, message) {
    const now = Date.now();
    if (!message && pose === reported && now - reportedAt < 10000) return;
    reported = pose;
    reportedAt = now;
    host.api("/api/companion/session", { method: "PUT", body: { pose, message: message || "" } }).catch(() => {});
  }

  // ------------------------------------------------------------------ blinking and nodding
  function scheduleBlink() {
    clearTimeout(blinkTimer);
    blinkTimer = setTimeout(() => { blink(Math.random() < 0.2 ? 2 : 1); scheduleBlink(); }, 2500 + Math.random() * 4000);
  }
  /** Half closed, closed, half closed: about a fifth of a second (sometimes twice). */
  function blink(times) {
    if (REDUCED || document.hidden || !currentItem || !currentItem.shut || !shut$ || !shut$.complete || !shut$.naturalWidth) return;
    const on = (el, yes) => el.classList.toggle("on", yes);
    const mid = currentItem.half && half$.complete && half$.naturalWidth ? half$ : shut$;
    const once = (delay) => {
      setTimeout(() => on(mid, true), delay);
      setTimeout(() => { on(mid, false); on(shut$, true); }, delay + 60);
      setTimeout(() => { on(shut$, false); on(mid, true); }, delay + 150);
      setTimeout(() => on(mid, false), delay + 210);
    };
    once(0);
    if (times > 1) once(330);
  }
  function scheduleNod() {
    clearTimeout(nodTimer);
    nodTimer = setTimeout(() => { if (root$ && root$.dataset.mode === "studying") play("sb-nod"); scheduleNod(); }, 6000 + Math.random() * 6000);
  }

  function flash(pose, ms) { override = pose; overrideUntil = Date.now() + ms; refresh(); setTimeout(refresh, ms + 50); }

  // How long each reaction plays (companion.css). Talking and head tilts are small: they wait for a bigger one to finish.
  const REACTIONS = { "sb-pop": 600, "sb-jump": 950, "sb-shake": 550, "sb-land": 500, "sb-talk": 600, "sb-tilt": 1800, "sb-nod": 1300 };
  let reactingUntil = 0;
  function play(cls) {
    if (REDUCED || !react$) return;
    const small = cls === "sb-talk" || cls === "sb-tilt" || cls === "sb-nod";
    if (small && Date.now() < reactingUntil) return;
    react$.classList.remove(...Object.keys(REACTIONS));
    void react$.offsetWidth; // restart the animation
    react$.classList.add(cls);
    reactingUntil = Date.now() + REACTIONS[cls];
  }

  function effect(kind) {
    if (!fx) return;
    fx.replaceChildren();
    if (!kind || REDUCED) return;
    if (kind === "anger") { // the manga anger mark, drawn (emoji fonts differ between devices)
      const mark = h("span", { class: "sb-p sb-p-anger" });
      mark.innerHTML = ANGER_SVG; // a fixed string, no user content
      fx.append(mark);
      return;
    }
    const glyphs = { sparkle: ["✦", "✧", "✨", "✦", "✧", "✦"], zzz: ["z", "z", "Z"],
      code: ["</>", "{ }", ";"], heart: ["♥", "♥", "♥"], think: ["?", "…"], music: ["♪", "♫"] }[kind] || [];
    glyphs.forEach((g, i) => fx.append(h("span", { class: `sb-p sb-p-${kind}`, style: `--i:${i};--n:${glyphs.length}`, text: g })));
  }
  const ANGER_ARCS = "M9 3A6 6 0 0 1 3 9M15 3A6 6 0 0 0 21 9M3 15A6 6 0 0 1 9 21M21 15A6 6 0 0 0 15 21";
  const ANGER_SVG = `<svg viewBox="0 0 24 24" width="100%" height="100%" aria-hidden="true" fill="none" stroke-linecap="round">` +
    `<path d="${ANGER_ARCS}" stroke="#fff" stroke-width="5.5"/><path d="${ANGER_ARCS}" stroke="#e5323b" stroke-width="3"/></svg>`;

  // ------------------------------------------------------------------ the floating pet
  function build() {
    if (root$) root$.remove();
    root$ = null;
    if (!prefs.enabled || !packs.length) return;
    imgA = h("img", { class: "sb-img on", alt: "", draggable: "false" });
    imgB = h("img", { class: "sb-img", alt: "", draggable: "false" });
    half$ = h("img", { class: "sb-blink", alt: "", draggable: "false" });
    shut$ = h("img", { class: "sb-blink", alt: "", draggable: "false" });
    fx = h("span", { class: "sb-fx", "aria-hidden": "true" });
    react$ = h("span", { class: "sb-react" }, h("span", { class: "sb-sway" }, h("span", { class: "sb-body" }, imgA, imgB, half$, shut$)), fx);
    bubble = h("div", { class: "jc-bubble", role: "status", "aria-live": "polite", hidden: true });
    panel = h("div", { class: "jc-panel", role: "dialog", "aria-label": T("sb.name"), hidden: true });
    pet = h("button", { type: "button", class: "jc-pet", "aria-label": T("sb.quick"), "aria-expanded": "false", title: T("sb.dragHint") },
      react$, h("span", { class: "sb-shadow", "aria-hidden": "true" }));
    root$ = h("div", { class: `jc jc-${prefs.size} jc-${host.place}` }, bubble, panel, pet);
    document.body.append(root$);
    current = "";
    place();
    refresh();
    // Pointer handling: a tap opens the quick actions (decided on pointerup, which also works where
    // Android WebViews drop the click after a pointer capture); a drag moves her, with a tilt.
    let start = null, moved = false, lastX = 0, lastT = 0;
    pet.addEventListener("pointerdown", (e) => {
      if (e.button !== undefined && e.button !== 0) return;
      start = { x: e.clientX, y: e.clientY, right: parseFloat(root$.style.right), bottom: parseFloat(root$.style.bottom) };
      moved = false; lastX = e.clientX; lastT = performance.now();
      try { pet.setPointerCapture(e.pointerId); } catch (_) { /* fine */ }
    });
    pet.addEventListener("pointermove", (e) => {
      if (!start) return;
      const dx = e.clientX - start.x, dy = e.clientY - start.y;
      if (!moved && Math.hypot(dx, dy) < 8) return;
      if (!moved) root$.classList.add("jc-held");
      moved = true;
      const now = performance.now();
      const vx = (e.clientX - lastX) / Math.max(8, now - lastT);
      lastX = e.clientX; lastT = now;
      react$.style.setProperty("--tilt", `${Math.max(-20, Math.min(20, -vx * 18))}deg`);
      prefs.pos = clampPos({ right: start.right - dx, bottom: start.bottom - dy });
      place();
    });
    const finish = (e) => {
      if (!start) return;
      const wasMoved = moved;
      start = null; moved = false;
      root$.classList.remove("jc-held");
      react$.style.setProperty("--tilt", "0deg");
      if (wasMoved) { savePrefs(); play("sb-land"); return; }
      if (e.type === "pointerup") togglePanel();
    };
    pet.addEventListener("pointerup", finish);
    pet.addEventListener("pointercancel", finish);
    pet.addEventListener("click", (e) => { if (e.detail === 0) togglePanel(); }); // keyboard (Enter/Space)
    if (host.place === "desktop" && !REDUCED) {
      let raf = 0;
      document.addEventListener("pointermove", (e) => { // she glances toward the pointer
        if (raf || !root$) return;
        raf = requestAnimationFrame(() => {
          raf = 0;
          const r = pet.getBoundingClientRect();
          const look = Math.max(-4, Math.min(4, (e.clientX - (r.left + r.width / 2)) / 120));
          react$.style.setProperty("--look", `${look}deg`);
        });
      });
    }
    clearInterval(tiltTimer);
    tiltTimer = setInterval(() => { if (!document.hidden && root$ && root$.dataset.mode === "idle" && Math.random() < 0.5) play("sb-tilt"); }, 9000);
    scheduleBlink();
    scheduleNod();
  }

  function defaultPos() { return host.place === "phone" ? { right: 10, bottom: 200 } : { right: 22, bottom: 130 }; }
  function clampPos(p) {
    const size = pet ? pet.offsetWidth || 80 : 80;
    return { right: Math.max(4, Math.min(window.innerWidth - size - 4, p.right)), bottom: Math.max(4, Math.min(window.innerHeight - size - 4, p.bottom)) };
  }
  function place() {
    const p = clampPos(prefs.pos || defaultPos());
    root$.style.right = p.right + "px";
    root$.style.bottom = p.bottom + "px";
    root$.classList.toggle("jc-left", p.right > window.innerWidth / 2);
    root$.classList.toggle("jc-low", p.bottom < window.innerHeight / 2);
  }

  function say(text, ms, quiet) {
    if (!bubble || !prefs.enabled || (panel && !panel.hidden)) return; // not while her menu is open
    clearTimeout(bubbleTimer);
    bubble.textContent = text;
    bubble.hidden = false;
    if (!quiet) play("sb-talk");
    if (ms !== 0) bubbleTimer = setTimeout(() => { bubble.hidden = true; }, ms || 7000);
  }

  function greeting() {
    const hr = new Date().getHours();
    return T(hr < 5 ? "sb.late" : hr < 12 ? "sb.morning" : hr < 18 ? "sb.afternoon" : hr < 23 ? "sb.evening" : "sb.late");
  }

  async function togglePanel(open) {
    const show = open === undefined ? panel.hidden : open;
    panel.hidden = !show;
    pet.setAttribute("aria-expanded", String(show));
    if (!show) return;
    bubble.hidden = true;
    const action = (label, fn, extra) => h("button", { type: "button", class: "jc-action", onclick: () => { togglePanel(false); fn(); } }, label, extra || null);
    const dueBadge = h("span", { class: "jc-badge", hidden: true });
    const f = focusState;
    const st = engine.state();
    fillNode(panel,
      h("div", { class: "jc-panel-head" }, h("strong", { text: greeting() }),
        h("button", { type: "button", class: "jc-close", "aria-label": T("sb.close"), onclick: () => togglePanel(false) }, "×")),
      st.session ? [
        h("p", { class: "jc-session-line", text: sessionLine(st) }),
        st.session.paused ? action(T("sb.resumeSession"), () => { engine.resume(); refresh(); })
          : action(T("sb.pauseSession"), () => { engine.pause(); refresh(); }),
        action(T("sb.snoozeNudges"), () => { engine.snooze(15); refresh(); }),
        action(T("sb.endSession"), endSession),
      ] : [
        action(T("sb.codingSession"), () => startSession("coding")),
        action(T("sb.studySession"), () => startSession("study")),
      ],
      st.breakLeft ? action(T("sb.endBreak"), () => endBreak()) : action(T("sb.break"), () => startBreak(5)),
      f && f.supported && f.enabled && f.state === "distracted" ? action(T("sb.snooze"), () => host.api("/api/focus/snooze", { method: "POST", body: { minutes: 15 } }).then(pollFocus)) : null,
      action(T("sb.checkin"), () => checkin("manual")),
      action(T("sb.word"), () => showWord(true)),
      action(T("sb.review"), () => host.navigate("review"), dueBadge),
      action(T("sb.practice"), () => host.navigate("practice")),
      action(T("sb.ask"), () => host.navigate("chat")),
      action(T("sb.progress"), () => host.navigate("progress")),
      action(T("sb.hide"), () => { prefs.enabled = false; savePrefs(); build(); host.navigate("toast", T("sb.hidden")); }));
    panel.querySelector(".jc-action").focus();
    try {
      const due = await host.api("/api/study/due");
      if (due.length) { dueBadge.textContent = String(due.length); dueBadge.hidden = false; }
    } catch (_) { /* offline */ }
  }

  // ------------------------------------------------------------------ focus sessions and breaks (the rules are in sessions.js)
  const mmss = (ms) => `${Math.floor(ms / 60000)}:${String(Math.floor((ms % 60000) / 1000)).padStart(2, "0")}`;
  const kindName = (kind) => T(kind === "study" ? "sb.kind.study" : "sb.kind.coding");
  function sessionLine(st) {
    const s = st.session;
    return T(s.paused ? "sb.sessionPaused" : "sb.sessionLine", { kind: kindName(s.kind), t: mmss(s.left) });
  }
  function kindFromContext() {
    return ctx.view === "study" || (ctx.view === "learn" && ctx.tab === "guides") || STUDY_MODES.includes(ctx.mode) ? "study" : "coding";
  }

  async function startSession(kind, minutes) {
    kind = kind || kindFromContext();
    if (!minutes) {
      if (prefs.checkin === "session" || (prefs.checkin === "daily" && prefs.lastCheckinDay !== today())) {
        const adv = await checkin("focus", kind);
        if (adv && adv.started) return; // the advice card already started it
        minutes = adv ? adv.minutes : prefs.sessionMinutes;
      } else minutes = prefs.sessionMinutes;
    }
    askNotifications();
    engine.start(kind, minutes || 25);
    lastSaid = Date.now();
    flash("cheer", 1500);
    say(T("sb.sessionStart", { kind: kindName(kind), m: minutes || 25 }), 5000);
  }
  function endSession() { engine.stop(); refresh(); }
  function startBreak(minutes) {
    engine.startBreak(minutes);
    refresh();
    if (focusState && focusState.supported && focusState.enabled) host.api("/api/focus/snooze", { method: "POST", body: { minutes, break: true } }).catch(() => {});
  }
  function endBreak() {
    engine.endBreak();
    activeSince = Date.now();
    flash("cheer", 4000);
    say(T("sb.breakEnded"), 6000);
  }

  /** Every second: the session's clock, its events, and her bubble. */
  function tickSessions() {
    for (const ev of engine.tick()) {
      if (ev.type === "nudge") {
        const msg = T("sb.nudge", { m: ev.minutes });
        say(msg, 15000);
        if (!engine.native) notify(msg, "pouty"); // on Android the app sends the notification itself
        if (host.place === "desktop") reportPose("pouty", msg);
      } else if (ev.type === "back") {
        flash("cheer", 2500);
        say(T("sb.back"), 4000);
      } else if (ev.type === "done") {
        const msg = T("sb.sessionDoneKind", { kind: kindName(ev.kind) });
        flash("celebrate", 8000);
        say(msg, 9000);
        if (!engine.native) notify(msg, "celebrate");
      } else if (ev.type === "breakOver") {
        activeSince = Date.now();
        flash("cheer", 4000);
        say(T("sb.breakEnded"), 6000);
      }
    }
    const st = engine.state();
    if (st.breakLeft > 0) say(T("sb.breakTick", { t: mmss(st.breakLeft) }), 1500, true);
    else if (st.session && !st.session.paused && Date.now() - lastSaid > 10 * 60000) {
      lastSaid = Date.now();
      say(T("sb.sessionTick", { t: mmss(st.session.left) }), 5000);
    }
    refresh();
  }

  /** Activity in Jarvis itself (taps, typing, scrolling): the only thing a session notices. */
  function watchActivity() {
    const seen = () => { if (engine && !document.hidden) engine.activity(); };
    for (const type of ["pointerdown", "keydown", "input", "wheel", "touchstart", "scroll"]) {
      document.addEventListener(type, seen, { passive: true, capture: true });
    }
    document.addEventListener("visibilitychange", () => { if (!document.hidden) seen(); });
  }

  function scheduleTips() {
    setInterval(() => {
      if (!prefs.enabled || !prefs.tips || engine.state().breakLeft || document.hidden) return;
      if ((Date.now() - activeSince) / 60000 >= 50) { activeSince = Date.now(); flash("care", 8000); say(T("sb.longWork"), 12000); }
    }, 60000);
  }

  // ------------------------------------------------------------------ optional on Windows: count time in your coding apps
  async function pollFocus() {
    try { focusState = await host.api("/api/focus"); } catch (_) { focusState = null; return; }
    if (focusState.state === "coding" && engine) engine.activity(); // you opted in: working in VS Code counts
    if (focusState.alert && focusState.alert.id !== lastAlertId && focusState.state === "distracted") {
      const first = lastAlertId === null;
      lastAlertId = focusState.alert.id;
      if (!first || Date.now() - Date.parse(focusState.alert.at) < 60000) {
        const msg = T("sb.distracted", { m: focusState.alert.minutes });
        say(msg, 15000);
        notify(msg, "pouty");
      }
    } else if (focusState.alert && lastAlertId === null) lastAlertId = focusState.alert.id;
    refresh();
  }
  function startFocusWatch() {
    clearInterval(focusPoll);
    if (host.place !== "desktop") return;
    pollFocus();
    focusPoll = setInterval(() => {
      if (document.hasFocus()) host.api("/api/focus/heartbeat", { method: "POST" }).catch(() => {});
      pollFocus();
    }, 4000);
  }
  async function setFocus(on) {
    if (on) askNotifications();
    try { focusState = await host.api("/api/focus", { method: "PUT", body: { focus_enabled: on } }); } catch (_) { /* ignore */ }
    refresh();
  }
  function askNotifications() {
    if (host.place !== "desktop" || typeof Notification === "undefined" || Notification.permission !== "default") return;
    try { Notification.requestPermission(); } catch (_) { /* ignore */ }
  }
  function notify(text, pose) {
    if (typeof Notification === "undefined" || Notification.permission !== "granted" || !document.hidden) return;
    try {
      const item = itemFor(pose, true);
      new Notification(T("sb.notifTitle"), { body: text, icon: item ? BASE + item.file : undefined, tag: "study-buddy" });
    } catch (_) { /* some browsers need a service worker for notifications */ }
  }

  // check-ins made while Jarvis can't be reached wait on this device, then go when it's back
  async function sendPending() {
    while (prefs.pending.length) {
      try { await host.api("/api/checkins", { method: "POST", body: prefs.pending[0] }); } catch (_) { return; }
      prefs.pending.shift();
      savePrefs();
    }
  }

  // ------------------------------------------------------------------ check-in (mood, energy, stress, body)
  function checkin(context, kind) {
    return new Promise((resolve) => {
      const old = document.querySelector(".jc-checkin");
      if (old) old.remove();
      const val = { mood: 0, energy: 0, stress: 0, sleep: null, body: new Set() };
      const scale = (key, faces) => h("div", { class: "ci-scale", role: "radiogroup", "aria-label": T("ci." + key) },
        faces.map((f, i) => h("button", { type: "button", role: "radio", "aria-checked": "false", "aria-label": `${T("ci." + key)} ${i + 1}/5`,
          onclick: (e) => {
            val[key] = i + 1;
            for (const b of e.currentTarget.parentNode.children) b.setAttribute("aria-checked", String(b === e.currentTarget));
          } }, f)));
      const sleep = h("div", { class: "ci-scale ci-hours", role: "radiogroup", "aria-label": T("ci.sleep") },
        [["<5", 4], ["5", 5], ["6", 6], ["7", 7], ["8+", 8.5]].map(([label, v]) => h("button", { type: "button", role: "radio", "aria-checked": "false",
          onclick: (e) => { val.sleep = v; for (const b of e.currentTarget.parentNode.children) b.setAttribute("aria-checked", String(b === e.currentTarget)); } }, label)));
      const bodyKeys = ["rested", "energetic", "tired", "sleepy", "hungry", "thirsty", "headache", "eye_strain", "sore", "sick", "restless"];
      const body = h("div", { class: "ci-chips" }, bodyKeys.map((k) => h("button", { type: "button", "aria-pressed": "false",
        onclick: (e) => { const on = !val.body.has(k); on ? val.body.add(k) : val.body.delete(k); e.currentTarget.setAttribute("aria-pressed", String(on)); } }, T("ci.body." + k))));
      const note = h("input", { type: "text", maxlength: "500", placeholder: T("ci.note"), "aria-label": T("ci.note") });
      const item = itemFor("idea");
      const close = (adv) => { card.remove(); resolve(adv || null); };
      const card = h("div", { class: "jc-word jc-checkin", role: "dialog", "aria-modal": "true", "aria-label": T("ci.title") },
        item ? h("img", { src: BASE + item.file, alt: "", class: "jc-word-pet" }) : null,
        h("div", { class: "jc-word-body" },
          h("strong", { class: "ci-title", text: T("ci.title") }),
          h("div", { class: "ci-row" }, h("span", { text: T("ci.mood") }), scale("mood", ["😞", "😕", "😐", "🙂", "😄"])),
          h("div", { class: "ci-row" }, h("span", { text: T("ci.energy") }), scale("energy", ["🪫", "😪", "🙂", "💪", "⚡"])),
          h("div", { class: "ci-row" }, h("span", { text: T("ci.stress") }), scale("stress", ["😌", "🙂", "😐", "😟", "😣"])),
          h("div", { class: "ci-row" }, h("span", { text: T("ci.sleep") }), sleep),
          h("div", { class: "ci-row" }, h("span", { text: T("ci.body") }), body),
          note,
          h("p", { class: "ci-why", text: T("ci.why") }),
          h("div", { class: "jc-word-actions" },
            h("button", { type: "button", class: "jc-btn", onclick: () => { prefs.lastCheckinDay = today(); savePrefs(); close(null); } }, T("ci.skip")),
            h("button", { type: "button", class: "jc-btn primary", onclick: async () => {
              if (!val.mood || !val.energy || !val.stress) {
                const title = card.querySelector(".ci-title");
                title.classList.add("ci-need");
                title.textContent = T("ci.need");
                return;
              }
              const sent = { mood: val.mood, energy: val.energy, stress: val.stress, sleep_hours: val.sleep, body: [...val.body],
                note: note.value, context: context === "manual" ? "" : context === "focus" ? "focus" : "open" };
              let r;
              try {
                r = await host.api("/api/checkins", { method: "POST", body: sent });
              } catch (_) { // offline: keep it on this device and send it later
                prefs.pending = [...prefs.pending, sent].slice(-30);
                prefs.lastCheckinDay = today();
                prefs.wellbeing = `Mood ${val.mood}/5, energy ${val.energy}/5, stress ${val.stress}/5.`;
                prefs.wellbeingDay = today();
                savePrefs();
                host.navigate("toast", T("ci.savedOffline"));
                close({ minutes: val.energy <= 2 || val.stress >= 4 ? 20 : val.energy >= 4 && val.stress <= 2 ? 50 : 25 });
                return;
              }
              prefs.lastCheckinDay = today();
              prefs.wellbeing = r.advice.summary;
              prefs.wellbeingDay = today();
              savePrefs();
              card.remove();
              showAdvice(r.advice, resolve, kind);
            } }, T("ci.save")))));
      document.body.append(card);
      card.querySelector(".ci-scale button").focus({ preventScroll: true });
      card.addEventListener("keydown", (e) => { if (e.key === "Escape") close(null); });
    });
  }

  function showAdvice(adv, resolve, kind) {
    flash(adv.kind === "gentle" ? "sleepy" : adv.kind === "deep" ? "celebrate" : "care", 5000);
    const item = itemFor(adv.kind === "deep" ? "cheer" : "idea");
    const card = h("div", { class: "jc-word jc-checkin", role: "dialog", "aria-label": T("ci.planTitle") },
      item ? h("img", { src: BASE + item.file, alt: "", class: "jc-word-pet" }) : null,
      h("div", { class: "jc-word-body" },
        h("strong", { text: T("ci.planTitle") }),
        h("p", { text: adv.plan }),
        adv.tips.length ? h("ul", { class: "ci-tips" }, adv.tips.map((t) => h("li", { text: t }))) : null,
        adv.support ? h("p", { class: "ci-support", text: adv.support }) : null,
        h("div", { class: "jc-word-actions wrap" },
          adv.breathing ? h("button", { type: "button", class: "jc-btn", onclick: () => breathe(card.querySelector(".jc-word-body")) }, T("ci.breathe")) : null,
          h("button", { type: "button", class: "jc-btn", onclick: () => { card.remove(); resolve(adv); host.navigate("coach", adv.summary); } }, T("ci.coach")),
          h("button", { type: "button", class: "jc-btn primary", onclick: () => {
            card.remove();
            if (!engine.state().session) { startSession(kind || kindFromContext(), adv.minutes); resolve({ ...adv, started: true }); } else resolve(adv);
          } }, T("ci.startSession", { m: adv.minutes })),
          h("button", { type: "button", class: "jc-btn ghost", onclick: () => { card.remove(); resolve(adv); } }, T("ci.done")))));
    document.body.append(card);
  }

  function breathe(box) {
    const circle = h("div", { class: "ci-breath", "aria-live": "polite" });
    box.prepend(circle);
    const steps = [["ci.breatheIn", "grow"], ["ci.hold", "hold"], ["ci.breatheOut", "shrink"], ["ci.hold", "rest"]];
    let i = 0;
    const tick = () => {
      if (i >= 16 || !circle.isConnected) { circle.remove(); return; } // 4 rounds of 4 x 4 seconds
      const [label, cls] = steps[i % 4];
      circle.textContent = T(label);
      circle.className = "ci-breath " + cls;
      i += 1;
      setTimeout(tick, 4000);
    };
    tick();
  }

  // ------------------------------------------------------------------ word of encouragement
  async function showWord(force) {
    if (!host) return; // not mounted yet
    if (!force) {
      if (prefs.word === "off") return;
      if (prefs.word === "daily" && prefs.lastWordDay === today()) return;
    }
    let w;
    try {
      const q = new URLSearchParams({ kinds: prefs.kinds, focus: prefs.focus, exclude: prefs.recent.slice(-12).join(",") });
      w = await host.api("/api/motivation?" + q);
    } catch (_) { // no connection: one from the copy saved on this device
      const recent = prefs.recent.slice(-12);
      const pool = ((host.offlineWords && host.offlineWords()) || []).filter((x) => !recent.includes(x.id) &&
        (prefs.kinds === "philosophy" ? !!x.school : prefs.kinds === "verses" ? x.kind === "verse" : prefs.kinds === "quotes" ? x.kind !== "verse" : true));
      if (!pool.length) return;
      // Stoicism and philosophy come up more often here too (motivation.PHILOSOPHY_WEIGHT)
      const weight = (x) => (x.school && prefs.kinds !== "philosophy" ? 2.5 : 1);
      let r = Math.random() * pool.reduce((n, x) => n + weight(x), 0);
      const chosen = pool.find((x) => (r -= weight(x)) < 0) || pool[pool.length - 1];
      w = { ...chosen, reason: "" };
    }
    prefs.recent = [...prefs.recent.filter((id) => id !== w.id), w.id].slice(-20);
    prefs.lastWordDay = today();
    savePrefs();
    const item = itemFor(w.themes.includes("rest") ? "sleepy" : w.themes.includes("perseverance") ? "cheer" : w.kind === "verse" ? "study" : "idea");
    const old = document.querySelector(".jc-word:not(.jc-checkin)");
    if (old) old.remove();
    const card = h("div", { class: "jc-word", role: "dialog", "aria-label": T("word.dialog"), "aria-describedby": "jc-word-text" },
      item ? h("img", { src: BASE + item.file, alt: "", class: "jc-word-pet" }) : null,
      h("div", { class: "jc-word-body" },
        h("span", { class: "jc-word-kind", text: T(w.school === "stoic" ? "word.stoic" : w.school ? "word.philosophy"
          : w.kind === "verse" ? "word.verse" : w.kind === "quote" ? "word.quote" : "word.note") }),
        h("blockquote", { id: "jc-word-text", text: w.text }),
        h("cite", { text: w.source }),
        w.reason ? h("span", { class: "jc-word-reason", text: T("word.because", { r: w.reason }) }) : null,
        h("div", { class: "jc-word-actions" },
          h("button", { type: "button", class: "jc-btn", onclick: () => { card.remove(); showWord(true); } }, T("word.another")),
          h("button", { type: "button", class: "jc-btn primary", onclick: () => card.remove() }, T("word.thanks")))));
    document.body.append(card);
    card.addEventListener("keydown", (e) => { if (e.key === "Escape") card.remove(); });
    card.querySelector(".jc-btn.primary").focus({ preventScroll: true });
  }

  // ------------------------------------------------------------------ settings card (each app's settings page)
  function settingsCard() {
    const row = (label, control, hint) => h("label", { class: "jc-set" }, h("span", { class: "jc-set-label", text: label }), control,
      hint ? h("small", { class: "jc-set-hint", text: hint }) : null);
    const select = (key, options, after) => h("select", { onchange: (e) => { prefs[key] = e.target.value; savePrefs(); if (after) after(); } },
      options.map(([v, t]) => h("option", { value: v, text: t, selected: prefs[key] === v })));
    const check = (key, after) => { const el = h("input", { type: "checkbox", onchange: (e) => { prefs[key] = e.target.checked; savePrefs(); if (after) after(); } }); el.checked = !!prefs[key]; return el; };
    const number = (key, min, max) => h("input", { type: "number", min: String(min), max: String(max), value: String(prefs[key]),
      onchange: (e) => { prefs[key] = Math.max(min, Math.min(max, Math.round(Number(e.target.value)) || DEFAULTS[key])); e.target.value = String(prefs[key]); savePrefs(); } });
    const preview = h("div", { class: "jc-previews" });
    const drawPreview = () => {
      preview.replaceChildren(...packs.map((p) => h("div", { class: "jc-pack" + (p.id === prefs.pack ? " on" : "") },
        h("strong", { text: p.name }),
        h("div", { class: "jc-pack-poses" }, p.items.map((i) => h("button", { type: "button", class: "jc-pose", title: i.mood, "aria-label": `${p.name}: ${i.mood}`,
          onclick: () => { prefs.pack = p.id; savePrefs(); if (!root$) { prefs.enabled = true; savePrefs(); build(); } else { current = ""; } flash(i.mood, 3500); drawPreview();
            if (host.place === "desktop") host.api("/api/companion/overlay", { method: "PUT", body: { pack: p.id } }).catch(() => {}); } },
          h("img", { src: BASE + i.file, alt: "" })))))));
    };
    drawPreview();
    const focusBox = h("div", { class: "jc-focus" });
    drawFocus(focusBox);
    const lang = h("select", { onchange: (e) => { if (root.JarvisI18n) root.JarvisI18n.setLang(e.target.value); build(); } },
      [["en", "English"], ["ja", "日本語 (Japanese)"]].map(([v, t]) => h("option", { value: v, text: t, selected: (root.JarvisI18n ? root.JarvisI18n.lang() : "en") === v })));
    return h("div", { class: "jc-settings" },
      row(T("set.lang"), lang),
      row(T("set.show"), check("enabled", build)),
      h("span", { class: "jc-set-label", text: T("set.pack") }), preview,
      row(T("set.size"), select("size", [["s", T("set.small")], ["m", T("set.medium")], ["l", T("set.large")]], build)),
      row(T("set.tips"), check("tips")),
      row(T("set.checkin"), select("checkin", [["daily", T("set.ciDaily")], ["session", T("set.ciSession")], ["off", T("set.ciOff")]])),
      row(T("set.wordWhen"), select("word", [["open", T("set.wordEvery")], ["daily", T("set.wordDaily")], ["off", T("set.wordOff")]])),
      row(T("set.kind"), select("kinds", [["both", T("set.both")], ["philosophy", T("set.philosophy")], ["verses", T("set.verses")], ["quotes", T("set.quotes")]])),
      row(T("set.focusWhat"), select("focus", [["", "Not sure / a mix"], ["success", "Success — becoming capable"],
        ["security", "Security — the people I love will be okay"], ["freedom", "Freedom — control over my time and future"],
        ["recognition", "Recognition — people seeing my worth"], ["peace", "Peace — not having to prove myself all the time"]])),
      h("div", { class: "row wrap" },
        h("button", { type: "button", class: "jc-btn", onclick: () => showWord(true) }, T("set.showNow")),
        h("button", { type: "button", class: "jc-btn", onclick: () => checkin("manual") }, T("set.checkNow"))),
      h("h4", { class: "jc-sub", text: T("set.sessionsTitle") }),
      h("p", { class: "jc-set-hint", text: T("set.sessionPrivacy") }),
      row(T("set.sessionLength"), number("sessionMinutes", 5, 120)),
      row(T("set.sessionGrace"), number("grace", 1, 120)),
      row(T("set.sessionCooldown"), number("cooldown", 1, 240)),
      focusBox);
  }

  async function drawFocus(box) {
    if (host.place === "phone") {
      const n = host.native || {};
      const has = (fn) => typeof n[fn] === "function";
      const phoneCheck = (label, getter, setter, hint) => {
        const el = h("input", { type: "checkbox", onchange: (e) => { try { setter(e.target.checked); } catch (_) { /* old app */ } } });
        try { el.checked = !!getter(); } catch (_) { el.checked = false; }
        return h("label", { class: "jc-set" }, h("span", { class: "jc-set-label", text: label }), el, hint ? h("small", { class: "jc-set-hint", text: hint }) : null);
      };
      fillNode(box,
        has("overlayEnabled") ? phoneCheck(T("set.phoneOverlay"), () => n.overlayEnabled(), (v) => n.setOverlay(v, prefs.pack), T("set.phoneOverlayHint")) : null);
      return;
    }
    let st;
    try { st = await host.api("/api/focus"); } catch (_) { box.replaceChildren(); return; }
    focusState = st;
    if (!st.supported) { box.replaceChildren(); return; }
    const save = async (body) => { try { focusState = await host.api("/api/focus", { method: "PUT", body }); } catch (_) { /* ignore */ } drawFocus(box); refresh(); };
    const enabled = h("input", { type: "checkbox", onchange: (e) => setFocus(e.target.checked).then(() => drawFocus(box)) });
    enabled.checked = st.enabled;
    const overlay = h("input", { type: "checkbox", onchange: async (e) => {
      try { await host.api("/api/companion/overlay", { method: "PUT", body: { enabled: e.target.checked, pack: prefs.pack } }); } catch (_) { /* ignore */ }
    } });
    overlay.checked = st.overlay;
    const num = (key, value, min, max) => h("input", { type: "number", min: String(min), max: String(max), value: String(value),
      onchange: (e) => save({ [key]: Math.max(min, Math.min(max, Number(e.target.value) || value)) }) });
    const apps = new Set(st.apps);
    const appList = h("div", { class: "ci-chips" }, [...apps].sort().map((a) => h("button", { type: "button", "aria-pressed": "true", title: "Remove",
      onclick: () => { apps.delete(a); save({ focus_apps: [...apps] }); } }, a, " ×")));
    const recent = st.recent_apps.filter((a) => !apps.has(a) && !/^(pythonw|python|explorer)\.exe$/.test(a));
    const add = h("input", { type: "text", placeholder: T("set.addApp"), onkeydown: (e) => {
      if (e.key === "Enter" && e.target.value.trim()) { apps.add(e.target.value.trim().toLowerCase()); save({ focus_apps: [...apps] }); } } });
    fillNode(box,
      h("label", { class: "jc-set" }, h("span", { class: "jc-set-label", text: T("set.overlay") }), overlay),
      h("h4", { class: "jc-sub", text: T("set.watchTitle") }),
      h("p", { class: "jc-set-hint", text: T("set.focusPrivacy") }),
      h("label", { class: "jc-set" }, h("span", { class: "jc-set-label", text: T("set.focusOnLabel") }), enabled),
      st.enabled ? h("p", { class: "jc-state", text: `${st.app || "–"}: ${T("set.state." + st.state)} · ${st.coding_minutes_today} min today` }) : null,
      h("label", { class: "jc-set" }, h("span", { class: "jc-set-label", text: T("set.grace") }), num("focus_grace_minutes", st.grace_minutes, 1, 120)),
      h("label", { class: "jc-set" }, h("span", { class: "jc-set-label", text: T("set.cooldown") }), num("focus_cooldown_minutes", st.cooldown_minutes, 1, 240)),
      st.enabled ? h("div", { class: "row wrap" },
        h("button", { type: "button", class: "jc-btn", onclick: () => host.api("/api/focus/snooze", { method: "POST", body: { minutes: 15 } }).then(() => drawFocus(box)) }, T("set.snooze15")),
        h("button", { type: "button", class: "jc-btn", onclick: () => host.api("/api/focus/snooze", { method: "POST", body: { minutes: 60 } }).then(() => drawFocus(box)) }, T("set.snooze60")),
        h("button", { type: "button", class: "jc-btn", onclick: () => host.api(st.paused || st.snoozed_for ? "/api/focus/resume" : "/api/focus/pause", { method: "POST" }).then(() => drawFocus(box)) },
          st.paused || st.snoozed_for ? T("set.resume") : T("set.pause"))) : null,
      h("span", { class: "jc-set-label", text: T("set.apps") }), appList, add,
      recent.length ? h("span", { class: "jc-set-hint", text: T("set.recent") }) : null,
      recent.length ? h("div", { class: "ci-chips" }, recent.map((a) => h("button", { type: "button", "aria-pressed": "false",
        onclick: () => { apps.add(a); save({ focus_apps: [...apps] }); } }, "+ " + a))) : null);
  }

  // ------------------------------------------------------------------ public
  async function mount(hostObj) {
    host = hostObj;
    loadPrefs();
    try { packs = (await (await fetch(BASE + "packs.json", { cache: "no-cache" })).json()).packs || []; } catch (_) { packs = []; }
    const settings = () => ({ grace: prefs.grace, cooldown: prefs.cooldown, lang: root.JarvisI18n ? root.JarvisI18n.lang() : "en" });
    const S = root.JarvisSessions;
    engine = host.native && typeof host.native.sessionState === "function" && S ? S.native(host.native, settings)
      : S ? S.create({ store: host.store, settings }) : null;
    if (!engine) { // sessions.js didn't load: no sessions, but she still works
      const none = () => {};
      engine = { native: false, start: none, stop: none, pause: none, resume: none, snooze: none, startBreak: none, endBreak: none,
        activity: none, tick: () => [], state: () => ({ session: null, breakLeft: 0, snoozedLeft: 0, inactiveFor: 0, pouting: false }) };
    }
    build();
    clearInterval(sessionTimer);
    sessionTimer = setInterval(tickSessions, 1000);
    watchActivity();
    scheduleTips();
    startFocusWatch();
    sendPending();
    setInterval(sendPending, 120000);
    window.addEventListener("resize", () => { if (root$) place(); });
    if (root.JarvisI18n) root.JarvisI18n.onChange(() => build());
    // On opening: the check-in first (if it's due), then the word of the day.
    setTimeout(async () => {
      if (prefs.checkin === "daily" && prefs.lastCheckinDay !== today()) await checkin("open");
      showWord(false);
    }, 700);
    setTimeout(() => { if (prefs.tips) say(greeting() + " " + T("sb.tap"), 5000); }, 1500);
  }

  function setContext(c) { ctx = { ...ctx, ...(c || {}) }; refresh(); }
  function react(event, detail) {
    if (event === "tests_passed") { flash("celebrate", 8000); say(detail || T("sb.passed"), 7000); }
    else if (event === "tests_failed") { flash("care", 6000); say(detail || T("sb.failed"), 7000); }
    else if (event === "review_done") { flash("cheer", 6000); say(detail || T("sb.reviewsDone"), 6000); }
    else if (event === "thinking") { setContext({ thinking: !!detail }); }
  }
  function wellbeing() { return prefs.wellbeingDay === today() ? prefs.wellbeing : ""; }

  const session = () => (engine ? engine.state() : null);
  root.JarvisCompanion = { mount, setContext, react, say, showWord, settingsCard, checkin, wellbeing, startSession, endSession,
    startBreak, poseNow, session, blink };
})(this);
