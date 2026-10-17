/* Focus sessions (coding or study) with breaks, pause, snooze and one gentle reminder when you've been
 * inactive in Jarvis for the grace period. "Inactive" only means no taps, typing or scrolling in Jarvis
 * (or Jarvis in the background): nothing here looks at other apps, the screen or what you type.
 *
 *   const engine = JarvisSessions.create({ store, now, settings: () => ({ grace, cooldown }) })
 *   engine.start("coding" | "study", minutes), stop(), pause(), resume(), snooze(minutes),
 *   engine.startBreak(minutes), endBreak(), activity(), tick() -> [events], state()
 *   events: { type: "nudge", minutes } | { type: "back" } | { type: "done", kind } | { type: "breakOver" }
 *
 * On Android the app runs the same rules natively (FocusSession.java), so reminders keep working while
 * Jarvis is in the background; JarvisSessions.native(bridge) wraps it with the same interface. */
(function (root) {
  "use strict";

  const KEY = "jarvis.session";
  const POUT_MS = 45000; // she pouts this long after a reminder, then calms down (no nagging)
  const MIN = 60000;

  function create(opts) {
    const now = opts.now || (() => Date.now());
    const settings = opts.settings || (() => ({ grace: 5, cooldown: 15 }));
    let s = load();
    let pending = [];
    let lastSave = 0;

    function blank() {
      return { kind: "", total: 0, endsAt: 0, pausedLeft: null, pausedByBreak: false, snoozeUntil: 0, breakEnds: 0,
        lastActivity: now(), alerted: false, lastAlertAt: -1e15, poutUntil: 0, lastKind: "" };
    }
    function load() {
      try { return { ...blank(), ...JSON.parse(opts.store.get(KEY) || "{}") }; } catch (_) { return blank(); }
    }
    function save(force) {
      const t = now();
      if (!force && t - lastSave < 5000) return;
      lastSave = t;
      try { opts.store.set(KEY, JSON.stringify(s)); } catch (_) { /* storage blocked */ }
    }
    const active = () => !!s.kind;
    const paused = () => active() && s.pausedLeft !== null;

    function start(kind, minutes) {
      const t = now();
      s = { ...s, kind: kind === "study" ? "study" : "coding", total: minutes * MIN, endsAt: t + minutes * MIN, pausedLeft: null,
        pausedByBreak: false, snoozeUntil: 0, breakEnds: 0, lastActivity: t, alerted: false, poutUntil: 0 };
      save(true);
    }
    function stop() { s = { ...s, kind: "", pausedLeft: null, pausedByBreak: false, poutUntil: 0, alerted: false }; save(true); }
    function pause() {
      if (!active() || paused()) return;
      s.pausedLeft = Math.max(0, s.endsAt - now());
      s.poutUntil = 0;
      save(true);
    }
    function resume() {
      if (!paused()) return;
      const t = now();
      s.endsAt = t + s.pausedLeft;
      s.pausedLeft = null;
      s.pausedByBreak = false;
      s.lastActivity = t;
      s.alerted = false;
      save(true);
    }
    function snooze(minutes) { s.snoozeUntil = now() + minutes * MIN; s.poutUntil = 0; save(true); }
    function startBreak(minutes) {
      s.breakEnds = now() + minutes * MIN;
      s.poutUntil = 0;
      if (active() && !paused()) { pause(); s.pausedByBreak = true; }
      save(true);
    }
    function endBreak() {
      s.breakEnds = 0;
      if (s.pausedByBreak) resume();
      save(true);
    }
    function activity() {
      const t = now();
      if (s.alerted && active()) pending.push({ type: "back" });
      s.alerted = false;
      s.poutUntil = 0;
      s.lastActivity = t;
      save(false);
    }

    function tick() {
      const t = now();
      const events = pending;
      pending = [];
      if (s.breakEnds && t >= s.breakEnds) {
        events.push({ type: "breakOver" });
        endBreak();
      }
      if (active() && !paused() && t >= s.endsAt) {
        events.push({ type: "done", kind: s.kind });
        s.lastKind = s.kind;
        stop();
      }
      if (active() && !paused() && !s.breakEnds && t >= s.snoozeUntil) {
        const { grace, cooldown } = settings();
        const idle = t - s.lastActivity;
        if (idle >= grace * MIN && !s.alerted && t - s.lastAlertAt >= cooldown * MIN) {
          s.alerted = true; // one reminder per stretch: the next needs you back first, and the cooldown
          s.lastAlertAt = t;
          s.poutUntil = t + POUT_MS;
          events.push({ type: "nudge", minutes: Math.floor(idle / MIN) });
          save(true);
        }
      }
      return events;
    }

    function state() {
      const t = now();
      return {
        session: active() ? { kind: s.kind, total: s.total, left: paused() ? s.pausedLeft : Math.max(0, s.endsAt - t), paused: paused() } : null,
        breakLeft: s.breakEnds ? Math.max(0, s.breakEnds - t) : 0,
        snoozedLeft: Math.max(0, s.snoozeUntil - t),
        inactiveFor: t - s.lastActivity,
        pouting: active() && t < s.poutUntil,
      };
    }

    return { start, stop, pause, resume, snooze, startBreak, endBreak, activity, tick, state, native: false };
  }

  /** The Android app's own session (keeps going while Jarvis is in the background); same interface. */
  function nativeEngine(bridge, settings) {
    let last = null;
    const read = () => { try { return JSON.parse(bridge.sessionState() || "{}"); } catch (_) { return {}; } };
    const conf = () => JSON.stringify(settings ? settings() : {});
    const call = (fn, ...args) => { try { bridge[fn](...args); } catch (_) { /* old app */ } };
    let lastPing = 0;
    return {
      native: true,
      start: (kind, minutes) => call("sessionStart", kind === "study" ? "study" : "coding", minutes, conf()),
      stop: () => call("sessionStop"),
      pause: () => call("sessionPause", true),
      resume: () => call("sessionPause", false),
      snooze: (minutes) => call("sessionSnooze", minutes),
      startBreak: (minutes) => call("sessionBreak", minutes),
      endBreak: () => call("sessionBreak", 0),
      activity: () => { const t = Date.now(); if (t - lastPing > 3000) { lastPing = t; call("sessionActivity"); } },
      tick() {
        const n = read();
        const events = [];
        if (last) {
          if ((n.alertSeq || 0) > (last.alertSeq || 0)) events.push({ type: "nudge", minutes: Math.floor((n.inactiveFor || 0) / MIN) });
          if ((n.backSeq || 0) > (last.backSeq || 0)) events.push({ type: "back" });
          if ((n.doneSeq || 0) > (last.doneSeq || 0)) events.push({ type: "done", kind: n.lastKind || "coding" });
          if ((n.breakSeq || 0) > (last.breakSeq || 0)) events.push({ type: "breakOver" });
        }
        last = n;
        return events;
      },
      state() {
        const n = read();
        return {
          session: n.active ? { kind: n.kind, total: n.total || 0, left: n.left || 0, paused: !!n.paused } : null,
          breakLeft: n.breakLeft || 0, snoozedLeft: n.snoozed || 0, inactiveFor: n.inactiveFor || 0, pouting: !!n.pouting,
        };
      },
    };
  }

  const api = { create, native: nativeEngine, POUT_MS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.JarvisSessions = api;
})(this);
