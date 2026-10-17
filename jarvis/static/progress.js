/* Progress page on the computer: studying and developing, counted separately (see jarvis/progress.py).
 * Uses window.JarvisUI (helpers from app.js) and window.JarvisCharts (charts.js). */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const S = { tab: "study", days: 30 };

  /** Short, honest observations from the numbers (no model needed). */
  function insights(p, tab) {
    const out = [];
    if (tab === "study") {
      const st = p.study;
      const lastWeek = st.daily.slice(-7);
      const activeWeek = lastWeek.filter((d) => d.reviews + d.practice + d.questions + d.tasks > 0).length;
      out.push(activeWeek >= 5 ? `You studied on ${activeWeek} of the last 7 days. That consistency is what makes it stick.`
        : activeWeek ? `You studied on ${activeWeek} of the last 7 days. Short daily sessions (15 minutes) beat long rare ones.`
          : "No study activity in the last 7 days. Start small: review today's flashcards.");
      if (st.retention !== null) {
        out.push(st.retention >= 85 ? `Retention is ${st.retention}%: your cards may be too easy. Add harder cards or a new deck.`
          : st.retention >= 65 ? `Retention is ${st.retention}%: a healthy range for spaced repetition.`
            : `Retention is ${st.retention}%: you're forgetting many cards. Review a bit every day, and split long cards into smaller ones.`);
      }
      if (st.cards.due) out.push(`${st.cards.due} card(s) are due today.`);
      const weakest = st.exercises.by_language.filter((l) => l.total).sort((a, b) => a.solved / a.total - b.solved / b.total)[0];
      if (weakest && weakest.solved < weakest.total) out.push(`Least practised language: ${langName(weakest.language)} (${weakest.solved} of ${weakest.total} solved).`);
    } else {
      const dv = p.dev;
      const runs = dv.test_runs.passed + dv.test_runs.failed;
      const lastWeek = dv.daily.slice(-7);
      const activeWeek = lastWeek.filter((d) => d.tasks + d.changes + d.runs + d.questions > 0).length;
      out.push(activeWeek ? `You worked on code on ${activeWeek} of the last 7 days.` : "No development activity in the last 7 days.");
      if (runs) out.push(`${dv.test_runs.passed} of ${runs} test and build runs passed (${Math.round((100 * dv.test_runs.passed) / runs)}%).`);
      if (dv.open_tasks) out.push(`${dv.open_tasks} development task(s) are still open. Pick the one that unblocks the others.`);
      const top = [...dv.modes].sort((a, b) => b.questions - a.questions)[0];
      if (top && top.questions) out.push(`You ask most in "${modeName(top.mode)}" mode. Remember the other SDLC phases too (requirements, testing, release).`);
    }
    return out;
  }

  const LANGS = { python: "Python", javascript: "JavaScript", typescript: "TypeScript", php: "PHP" };
  const MODES = { requirements: "Requirements", rules: "Business rules", design: "Architecture & design", implement: "Implementation", test: "Testing & debugging", release: "Release & maintenance" };
  const langName = (l) => LANGS[l] || l;
  const modeName = (m) => MODES[m] || m;

  async function render() {
    const { el, fill, api, showError } = window.JarvisUI;
    const C = window.JarvisCharts;
    const page = $("#progress-page");
    const content = el("div", { class: "progress-body" });
    fill(page,
      el("div", { class: "page-head" }, el("h2", { text: "Progress" }),
        el("div", { class: "seg", role: "tablist", "aria-label": "What to show" },
          [["study", "Studying"], ["dev", "Developing"], ["feel", "Wellbeing"]].map(([id, label]) => el("button", { type: "button", role: "tab",
            "aria-pressed": String(S.tab === id), "aria-selected": String(S.tab === id), onclick: () => { S.tab = id; render(); } }, label))),
        el("select", { "aria-label": "Time range", onchange: (e) => { S.days = Number(e.target.value); render(); } },
          [[7, "Last 7 days"], [30, "Last 30 days"], [90, "Last 90 days"]].map(([v, t]) => el("option", { value: v, selected: S.days === v }, t))),
        el("span", { class: "spacer" }),
        el("span", { class: "muted small", text: S.tab === "study"
          ? "Flashcards, practice, study questions and Studying tasks."
          : S.tab === "dev" ? "Developing tasks, code changes, test and build runs, SDLC questions and Coding Focus."
            : "Your check-ins (mood, energy, stress) next to what you got done." })),
      content);
    if (S.tab === "feel") return renderWellbeing(content);
    let p;
    try { p = await api(`/api/progress?days=${S.days}`); } catch (err) { return showError(err); }
    const box = (cls) => el("div", { class: "card " + (cls || "") });
    const tilesBox = el("div"), a = box("chart-card"), b = box("chart-card"), c = box("chart-card");
    const notes = el("ul", { class: "insights" }, insights(p, S.tab).map((t) => el("li", { text: t })));
    fill(content, tilesBox, el("div", { class: "card insights-card" }, el("h3", { text: "What the numbers say" }), notes),
      a, el("div", { class: "chart-grid" }, b, c),
      el("p", { class: "muted small", text: "Flashcard reviews and tasks sync with Jarvis on your phone. Practice, commands and chats are counted on the device where they happened. Set a task's Area to Studying or Developing to count it here." }));
    if (S.tab === "study") {
      const st = p.study;
      C.tiles(tilesBox, [
        { label: "Study streak", value: `${st.streak} day${st.streak === 1 ? "" : "s"}`, note: `active on ${st.active_days} of ${p.days} days` },
        { label: "Cards reviewed", value: String(st.reviews_week), note: "in the last 7 days" },
        { label: "Retention", value: st.retention === null ? "–" : `${st.retention}%`, note: "reviews rated Good or Easy" },
        { label: "Cards learned", value: `${st.cards.learned}`, note: `of ${st.cards.total} · ${st.cards.due} due today` },
        { label: "Exercises solved", value: `${st.exercises.solved} / ${st.exercises.total}`, note: "Learn → Practice" },
        { label: "Studying tasks done", value: String(st.daily.reduce((n, d) => n + d.tasks, 0)), note: `${st.open_tasks} still open` },
      ]);
      C.columns(a, { title: "Study activity per day", subtitle: `Last ${p.days} days`,
        data: st.daily.map((d) => ({ label: d.date, values: d })),
        series: [{ key: "reviews", label: "Flashcard reviews", slot: 0 }, { key: "practice", label: "Practice checks", slot: 1 },
          { key: "questions", label: "Study questions", slot: 2 }],
        empty: "No study activity in this period yet. Review flashcards or try a practice exercise." });
      C.hbars(b, { title: "Practice solved by language", valueLabel: "Solved",
        rows: st.exercises.by_language.map((l) => ({ label: langName(l.language), value: l.solved, max: l.total })),
        format: (r) => `${r.value} of ${r.max}`, max: Math.max(...st.exercises.by_language.map((l) => l.total), 1) });
      const g = st.grades;
      C.hbars(c, { title: "How your reviews went", subtitle: `Last ${p.days} days`, valueLabel: "Reviews",
        rows: [["Again", g.again], ["Hard", g.hard], ["Good", g.good], ["Easy", g.easy]].map(([label, value]) => ({ label, value })),
        empty: "No flashcard reviews in this period." });
    } else {
      const dv = p.dev;
      const runs = dv.test_runs.passed + dv.test_runs.failed;
      C.tiles(tilesBox, [
        { label: "Coding streak", value: `${dv.streak} day${dv.streak === 1 ? "" : "s"}`, note: `active on ${dv.active_days} of ${p.days} days` },
        { label: "Tasks finished", value: String(dv.tasks_week), note: "in the last 7 days" },
        { label: "Code changes applied", value: String(dv.daily.reduce((n, d) => n + d.changes, 0)), note: `last ${p.days} days` },
        { label: "Test and build runs passed", value: runs ? `${dv.test_runs.passed} / ${runs}` : "–", note: runs ? `${Math.round((100 * dv.test_runs.passed) / runs)}% passed` : "run tests from Project" },
        { label: "Open development tasks", value: String(dv.open_tasks), note: "Tasks → Area: Developing" },
        { label: "Coding Focus", value: `${Math.round((dv.focus_week || 0) / 6) / 10} h`, note: "in coding apps, last 7 days" },
      ]);
      const focusCard = box("chart-card");
      content.insertBefore(focusCard, content.lastChild);
      C.columns(focusCard, { title: "Coding Focus per day", subtitle: "Minutes in your coding apps (Settings → Study Buddy → Coding Focus)",
        data: dv.daily.map((d) => ({ label: d.date, values: d })),
        series: [{ key: "focus", label: "Minutes coding", slot: 0 }, { key: "drifts", label: "Reminders", slot: 1 }],
        empty: "No Coding Focus time yet. Turn on Coding Focus in Settings to count time in your coding apps." });
      C.columns(a, { title: "Development activity per day", subtitle: `Last ${p.days} days`,
        data: dv.daily.map((d) => ({ label: d.date, values: d })),
        series: [{ key: "tasks", label: "Tasks finished", slot: 0 }, { key: "changes", label: "Code changes applied", slot: 1 },
          { key: "runs", label: "Test and build runs", slot: 2 }],
        empty: "No development activity in this period yet. Open a project, finish a Developing task, or run its tests." });
      C.hbars(b, { title: "Questions by development phase", subtitle: `Last ${p.days} days`, valueLabel: "Questions",
        rows: [...dv.modes].sort((x, y) => y.questions - x.questions).map((m) => ({ label: modeName(m.mode), value: m.questions })),
        empty: "No questions in the SDLC modes yet (Requirements, Design, Implementation, Testing, Release)." });
      C.columns(c, { title: "Development questions per day", subtitle: `Last ${p.days} days`,
        data: dv.daily.map((d) => ({ label: d.date, values: d })), series: [{ key: "questions", label: "Questions", slot: 0 }],
        empty: "No questions in the SDLC modes in this period." });
    }
  }

  async function renderWellbeing(content) {
    const { el, fill, api, showError } = window.JarvisUI;
    const C = window.JarvisCharts;
    let w;
    try { w = await api(`/api/checkins/insights?days=${Math.max(S.days, 7)}`); } catch (err) { return showError(err); }
    const chart = el("div", { class: "card chart-card" });
    fill(content,
      el("div", { class: "card insights-card" }, el("h3", { text: "What your check-ins say" }),
        el("ul", { class: "insights" }, w.notes.map((t) => el("li", { text: t }))),
        el("p", { class: "muted small", text: `${w.count} check-in(s). Study Buddy asks before you start (Settings → Study Buddy → Check-in). They stay on your devices.` }),
        window.JarvisCompanion ? el("button", { onclick: () => window.JarvisCompanion.checkin("manual").then(() => render()) }, "Check in now") : null),
      chart);
    if (w.series.length < 2) {
      fill(chart, el("h3", { text: "Mood, energy and stress" }), el("p", { class: "muted", text: "Check in on at least two days to see the chart." }));
      return;
    }
    C.line(chart, { title: "Mood, energy and stress", subtitle: "Daily average, 1 (low) to 5 (high)", xIsDate: true, xLabel: "Day",
      points: w.series.map((d) => ({ x: d.date, mood: d.mood, energy: d.energy, stress: d.stress })),
      series: [{ key: "mood", label: "Mood", slot: 0 }, { key: "energy", label: "Energy", slot: 1 }, { key: "stress", label: "Stress", slot: 2 }] });
  }

  window.JarvisProgress = { render, insights };
})();
