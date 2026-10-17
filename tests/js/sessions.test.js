// Run with:  node --test tests/js/sessions.test.js
// Study Buddy's focus sessions (jarvis/static/sessions.js) with a fake clock.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { create, POUT_MS } = require(path.join(__dirname, "..", "..", "jarvis", "static", "sessions.js"));

const MIN = 60000;
function setup(grace = 5, cooldown = 15) {
  const clock = { t: Date.UTC(2026, 9, 17, 9, 0) };
  const data = {};
  const store = { get: (k) => data[k] || null, set: (k, v) => { data[k] = v; } };
  const engine = create({ store, now: () => clock.t, settings: () => ({ grace, cooldown }) });
  const run = (minutes) => { // advance in 1-second steps, collecting events
    const out = [];
    for (let i = 0; i < minutes * 60; i++) { clock.t += 1000; out.push(...engine.tick()); }
    return out;
  };
  return { clock, data, store, engine, run };
}

test("a coding session counts down and celebrates when it ends", () => {
  const { engine, run } = setup();
  engine.start("coding", 25);
  assert.equal(engine.state().session.kind, "coding");
  engine.activity();
  const events = [];
  for (let m = 0; m < 26; m++) { engine.activity(); events.push(...run(1)); } // busy the whole time
  assert.deepEqual(events.map((e) => e.type), ["done"]);
  assert.equal(events[0].kind, "coding");
  assert.equal(engine.state().session, null);
});

test("inactive past the grace period: one reminder, a pout, then calm; back resets it", () => {
  const { engine, run } = setup(5, 15);
  engine.start("study", 50);
  assert.deepEqual(run(4.9).map((e) => e.type), []); // still inside the grace period
  const nudge = run(0.2);
  assert.deepEqual(nudge.map((e) => e.type), ["nudge"]);
  assert.equal(nudge[0].minutes, 5);
  assert.ok(engine.state().pouting);
  run(POUT_MS / MIN + 0.05);
  assert.ok(!engine.state().pouting, "she stops pouting after a while instead of nagging");
  assert.deepEqual(run(20).map((e) => e.type), [], "no second reminder while you stay away");
  engine.activity();
  assert.deepEqual(engine.tick().map((e) => e.type), ["back"]);
  // a new stretch away: allowed again, because the cooldown (15 min) has passed
  assert.deepEqual(run(5.1).map((e) => e.type), ["nudge"]);
});

test("the cooldown limits reminders even across stretches", () => {
  const { engine, run } = setup(1, 15);
  engine.start("coding", 60);
  assert.deepEqual(run(1.1).map((e) => e.type), ["nudge"]);
  engine.activity();
  engine.tick();
  assert.deepEqual(run(3).map((e) => e.type), [], "away again within the cooldown: quiet");
  assert.deepEqual(run(12).map((e) => e.type), ["nudge"], "after the cooldown");
});

test("pause, snooze and breaks don't nag, and pausing stops the clock", () => {
  const { engine, run } = setup(2, 1);
  engine.start("coding", 30);
  engine.pause();
  const left = engine.state().session.left;
  assert.deepEqual(run(10).map((e) => e.type), []);
  assert.equal(engine.state().session.left, left);
  engine.resume();
  engine.snooze(15);
  assert.deepEqual(run(10).map((e) => e.type), []);
  engine.activity();
  engine.tick();
  engine.startBreak(5);
  assert.ok(engine.state().session.paused, "a break pauses the session");
  const ev = run(5.05).map((e) => e.type);
  assert.deepEqual(ev, ["breakOver"]);
  assert.ok(!engine.state().session.paused, "and it resumes after the break");
});

test("the session survives a reload (it's kept on the device)", () => {
  const { engine, store, clock } = setup();
  engine.start("study", 25);
  const again = create({ store, now: () => clock.t, settings: () => ({ grace: 5, cooldown: 15 }) });
  assert.equal(again.state().session.kind, "study");
  assert.ok(again.state().session.left > 24 * MIN);
});
