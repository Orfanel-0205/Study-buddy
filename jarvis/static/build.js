/* Build page, shared by the computer and the phone. Everything here works without the model:
 *   Plan       an idea -> stack options, reliable services and APIs, a file tree, data model, MVP steps
 *   Decide     a weighted decision matrix with a pre-mortem
 *   Numbers    break-even and payback, with a chart
 *   Hackathon  a timeline, roles, pitch outline and cut list (optionally added to your tasks)
 *   JarvisBuild.render(container, { api, ask(text, mode), toast(text), offline() })
 * The Decide and Numbers inputs are kept on this device (localStorage). Without a connection, Decide and
 * Numbers work as usual, and Plan and Hackathon are made here from the saved catalog (host.offline()
 * returns the phone's offline pack: jarvis/build/catalog.py and hackathon.py offline_data()). */
(function (root) {
  "use strict";

  const T = (k, v) => (root.JarvisI18n ? root.JarvisI18n.t(k, v) : k);
  const KEY = "jarvis.build";
  let host = null, box = null;
  const S = load();

  function h(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k === "value") node.value = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat(Infinity)) if (c !== null && c !== undefined && c !== false) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    return node;
  }

  function load() {
    const base = {
      tab: "plan", idea: "", language: "any", plan: null,
      decide: { question: "Which should I build first?", options: ["Option A", "Option B"],
        criteria: [{ name: "What customers asked for", w: 5 }, { name: "Time to build", w: 3 }, { name: "Cost to run", w: 3 }, { name: "I can maintain it", w: 4 }],
        scores: {}, premortem: "" },
      numbers: { currency: "₱", price: 150, cost: 60, fixed: 8000, startup: 15000, sales: 80, growth: 10 },
      hack: { name: "", start: "", hours: 24, team: "", theme: "", criteria: ["innovation", "impact", "technical", "design", "presentation"] },
      hackPlan: null,
    };
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || "{}");
      return { ...base, ...saved, decide: { ...base.decide, ...(saved.decide || {}) }, numbers: { ...base.numbers, ...(saved.numbers || {}) },
        hack: { ...base.hack, ...(saved.hack || {}) } };
    } catch (_) { return base; }
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (_) { /* storage blocked */ } }

  function render(container, hostObj) {
    if (hostObj) host = hostObj;
    if (container) box = container;
    if (!box) return;
    const tabs = [["plan", T("build.plan")], ["decide", T("build.decide")], ["numbers", T("build.numbers")], ["hackathon", T("build.hackathon")]];
    const body = h("div", { class: "bd-body" });
    box.replaceChildren(
      h("div", { class: "bd-head" },
        h("div", { class: "seg bd-tabs", role: "tablist", "aria-label": T("build.title") },
          tabs.map(([id, label]) => h("button", { type: "button", role: "tab", "aria-selected": String(S.tab === id), "aria-pressed": String(S.tab === id),
            onclick: () => { S.tab = id; save(); render(); } }, label)))),
      body);
    ({ plan: renderPlan, decide: renderDecide, numbers: renderNumbers, hackathon: renderHackathon }[S.tab] || renderPlan)(body);
  }

  // ------------------------------------------------------------------ offline: the same rules as jarvis/build/*.py
  const offlinePack = () => (host && typeof host.offline === "function" ? host.offline() : null);
  const unreachable = (err) => !err || !err.status; // no answer at all (not a refusal)

  function localPlan(pack, idea, language) {
    const b = pack.build;
    const text = idea.toLowerCase();
    let best = null, bestScore = 0;
    for (const bp of b.blueprints) {
      const score = bp.keywords.filter((k) => text.includes(k)).length;
      if (score > bestScore) { best = bp; bestScore = score; }
    }
    const bp = best || b.fallback;
    const rank = (st) => (st.langs.includes(language) ? 0 : st.langs.includes("any") ? 1 : 2);
    return {
      blueprint: bp.id, title: bp.title, features: bp.features, data: bp.data, mvp: bp.mvp, skip: bp.skip, offline: true,
      stacks: [...bp.stacks].sort((x, y) => rank(x) - rank(y)).map((st) => ({
        name: st.name, tech: st.tech.filter((t) => b.tech[t]).map((t) => b.tech[t]), structure: b.structures[st.structure] || "" })),
    };
  }

  function localHackathon(pack, form) {
    const H = pack.hackathon;
    const begin = new Date(form.start);
    if (isNaN(begin)) throw new Error("Start must be a date and time.");
    const hours = Math.max(2, Math.min(Number(form.hours) || 24, 96));
    const iso = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    const at = (f) => new Date(begin.getTime() + hours * f * 3600000);
    const team = form.team.split(",").map((t) => t.trim()).filter(Boolean).slice(0, 6);
    if (!team.length) team.push("You");
    const roles = team.length === 1 ? ["Everything (solo): build, design and pitch"] : H.roles[String(team.length)]
      || [...H.roles["4"], ...team.slice(4).map((_, i) => `Builder ${i + 5}`)];
    const chosen = (form.criteria.length ? form.criteria : Object.keys(H.criteria)).filter((c) => H.criteria[c]);
    return {
      name: (form.name || "").trim() || "Hackathon", theme: (form.theme || "").trim(), start: iso(begin), end: iso(at(1)), hours, offline: true,
      team: team.map((m, i) => ({ name: m, role: roles[i] || "Builder" })),
      phases: H.phases.map((ph) => ({ title: ph.title, start: iso(at(ph.from)), end: iso(at(ph.to)),
        hours: Math.round(hours * (ph.to - ph.from) * 10) / 10, todo: ph.todo })),
      criteria: chosen.map((c) => ({ id: c, tip: H.criteria[c] })), before: H.before, pitch: H.pitch, cut_list: H.cut_list,
    };
  }

  const card = (...kids) => h("section", { class: "bd-card" }, ...kids);
  const list = (items, ordered) => h(ordered ? "ol" : "ul", { class: "bd-list" }, items.map((t) => h("li", { text: t })));
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); host.toast("Copied."); } catch (_) { host.toast("Select the text and copy it."); }
  }

  // ------------------------------------------------------------------ Plan an idea
  function renderPlan(body) {
    const idea = h("textarea", { rows: "4", maxlength: "4000", "aria-label": T("build.idea"),
      placeholder: "e.g. A website for small restaurants: menu with prices, owner can edit it, QR code for tables, later online orders.",
      oninput: (e) => { S.idea = e.target.value; save(); } });
    idea.value = S.idea;
    const lang = h("select", { "aria-label": T("build.lang"), onchange: (e) => { S.language = e.target.value; save(); } },
      [["any", "No preference"], ["php", "PHP"], ["python", "Python"], ["js", "JavaScript"], ["ts", "TypeScript"]]
        .map(([v, t]) => h("option", { value: v, text: t, selected: S.language === v })));
    const out = h("div", { class: "bd-out" });
    const go = async () => {
      if (S.idea.trim().length < 3) { idea.focus(); return; }
      out.replaceChildren(h("p", { class: "bd-muted", text: "Planning…" }));
      try { S.plan = await host.api("/api/build/plan", { method: "POST", body: { idea: S.idea, language: S.language } }); }
      catch (err) {
        const pack = offlinePack();
        if (!unreachable(err) || !pack) { out.replaceChildren(h("p", { class: "bd-error", text: "Couldn't plan this: " + (err.message || err) })); return; }
        S.plan = localPlan(pack, S.idea, S.language); // no connection: the same plan, made on this device
      }
      save();
      drawPlan(out);
    };
    body.append(
      card(h("h3", { text: T("build.idea") }),
        h("p", { class: "bd-muted", text: "Describe what you want to build. Jarvis suggests stacks it knows are reliable, the services and APIs to use, a file structure and what to build first. No model needed." }),
        idea,
        h("div", { class: "bd-row" }, h("label", { class: "bd-inline" }, T("build.lang"), " ", lang),
          h("button", { type: "button", class: "primary", onclick: go }, T("build.makePlan")))),
      out);
    if (S.plan) drawPlan(out);
  }

  function drawPlan(out) {
    const p = S.plan;
    const stackCard = (st, i) => {
      const rows = st.tech.map((t) => h("tr", {},
        h("td", { text: t.category }),
        h("td", {}, t.url ? h("a", { href: t.url, target: "_blank", rel: "noopener noreferrer", text: t.name }) : t.name),
        h("td", { text: `${t.for}. ${t.why}.` }),
        h("td", { text: t.cost })));
      return h("details", { class: "bd-stack", open: i === 0 },
        h("summary", {}, h("strong", { text: (i === 0 ? "Recommended: " : "Alternative: ") + st.name })),
        h("div", { class: "bd-table-wrap" }, h("table", { class: "bd-table" },
          h("thead", {}, h("tr", {}, ["Layer", "Use", "What it's for", "Cost"].map((c) => h("th", { scope: "col", text: c })))),
          h("tbody", {}, rows))),
        st.structure ? h("div", { class: "bd-tree-head" }, h("strong", { text: "File structure" }),
          h("button", { type: "button", class: "small", onclick: () => copy(st.structure) }, "Copy")) : null,
        st.structure ? h("pre", { class: "bd-tree", text: st.structure }) : null);
    };
    const summary = [`Idea: ${S.idea.trim()}`, `Closest blueprint: ${p.title}`, `Stack: ${p.stacks[0] ? p.stacks[0].name : "-"}`].join("\n");
    out.replaceChildren(
      p.offline ? h("p", { class: "bd-note", text: "Made on this device from Jarvis's saved catalog (no connection right now). Asking Jarvis to refine it needs Jarvis." }) : null,
      card(h("h3", { text: p.title }), h("p", { class: "bd-muted", text: "Matched from your description. If it's the wrong kind of project, add more detail and plan again." }),
        h("h4", { text: "Features" }), list(p.features)),
      card(h("h3", { text: "Tech stack options" }),
        h("p", { class: "bd-muted", text: "Costs change: check each service's current pricing page before you commit. “Free tier” means limits apply." }),
        p.stacks.map(stackCard)),
      card(h("h3", { text: "Data model (first tables)" }), list(p.data)),
      card(h("h3", { text: "Build it in this order (MVP)" }), list(p.mvp, true),
        p.skip && p.skip.length ? [h("h4", { text: "Skip for now" }), list(p.skip)] : null),
      h("div", { class: "bd-row" },
        h("button", { type: "button", class: "primary", onclick: () => host.ask(
          `${summary}\n\nRefine this plan for me: check the stack fits my idea, point out risks, and tell me exactly what to build this week.`, "stack") }, T("build.ask")),
        h("button", { type: "button", onclick: () => host.ask(`${summary}\n\nIs this a good business idea? Who would pay, how do I test it cheaply this week, and what should I say to the first customers?`, "business") },
          "Ask the business advisor")));
  }

  // ------------------------------------------------------------------ Decide (weighted matrix + pre-mortem)
  function renderDecide(body) {
    const d = S.decide;
    const key = (o, c) => `${o}|${c}`;
    const score = (o, c) => d.scores[key(o, c)] || 3;
    const totals = () => d.options.map((o, oi) => {
      const max = d.criteria.reduce((a, c) => a + c.w * 5, 0) || 1;
      const got = d.criteria.reduce((a, c, ci) => a + c.w * score(oi, ci), 0);
      return { name: o, pct: Math.round((got / max) * 100) };
    });
    const out = h("div", { class: "bd-out" });
    const redraw = () => { save(); drawResult(); };
    const table = h("table", { class: "bd-table bd-matrix" });
    const drawTable = () => {
      table.replaceChildren(
        h("thead", {}, h("tr", {}, h("th", { scope: "col", text: "Criteria (weight 1–5)" }),
          d.options.map((o, oi) => h("th", { scope: "col" }, h("input", { type: "text", value: o, maxlength: "60", "aria-label": `Option ${oi + 1} name`,
            oninput: (e) => { d.options[oi] = e.target.value; redraw(); } }),
            d.options.length > 2 ? h("button", { type: "button", class: "small ghost", "aria-label": `Remove ${o}`,
              onclick: () => { d.options.splice(oi, 1); d.scores = {}; drawTable(); redraw(); } }, "×") : null)))),
        h("tbody", {}, d.criteria.map((c, ci) => h("tr", {},
          h("th", { scope: "row" }, h("input", { type: "text", value: c.name, maxlength: "60", "aria-label": `Criterion ${ci + 1}`,
            oninput: (e) => { c.name = e.target.value; redraw(); } }),
            h("select", { "aria-label": `Weight of ${c.name}`, onchange: (e) => { c.w = Number(e.target.value); redraw(); } },
              [1, 2, 3, 4, 5].map((w) => h("option", { value: String(w), text: "×" + w, selected: c.w === w }))),
            d.criteria.length > 1 ? h("button", { type: "button", class: "small ghost", "aria-label": `Remove ${c.name}`,
              onclick: () => { d.criteria.splice(ci, 1); d.scores = {}; drawTable(); redraw(); } }, "×") : null),
          d.options.map((o, oi) => h("td", {}, h("select", { "aria-label": `${o}: ${c.name}`, onchange: (e) => { d.scores[key(oi, ci)] = Number(e.target.value); redraw(); } },
            [1, 2, 3, 4, 5].map((v) => h("option", { value: String(v), text: String(v), selected: score(oi, ci) === v })))))))));
    };
    const drawResult = () => {
      const t = totals().sort((a, b) => b.pct - a.pct);
      const close = t.length > 1 && t[0].pct - t[1].pct <= 5;
      const pm = h("textarea", { rows: "3", maxlength: "2000", placeholder: `Imagine it's 6 months from now and "${t[0].name}" failed. Write the most likely reasons.`,
        oninput: (e) => { d.premortem = e.target.value; save(); } });
      pm.value = d.premortem;
      const text = [`Decision: ${d.question}`, ...t.map((r) => `- ${r.name}: ${r.pct}%`),
        `Criteria: ${d.criteria.map((c) => `${c.name} (x${c.w})`).join(", ")}`, d.premortem ? `My pre-mortem: ${d.premortem}` : ""].filter(Boolean).join("\n");
      out.replaceChildren(card(
        h("h3", { text: "Result" }),
        h("ol", { class: "bd-rank" }, t.map((r, i) => h("li", {}, h("span", { text: r.name || "(unnamed)" }),
          h("span", { class: "bd-bar" }, h("span", { style: `width:${r.pct}%`, class: i === 0 ? "top" : "" })), h("strong", { text: r.pct + "%" })))),
        h("p", { class: close ? "bd-note warn" : "bd-note", text: close
          ? "It's a close call. The scores can't decide this one: test the riskiest assumption of each option with a real customer this week, then score again."
          : `"${t[0].name}" wins on what you said matters. Before committing, do the pre-mortem below.` }),
        h("h4", { text: "Pre-mortem" }), pm,
        h("div", { class: "bd-row" }, h("button", { type: "button", class: "primary", onclick: () => host.ask(text +
          "\n\nChallenge my decision: what am I missing, which assumption is riskiest, and how can I test it cheaply in 7 days?", "business") }, "Ask the business advisor"))));
    };
    const question = h("input", { type: "text", value: d.question, maxlength: "200", "aria-label": "The decision", oninput: (e) => { d.question = e.target.value; redraw(); } });
    drawTable();
    body.append(
      card(h("h3", { text: "What are you deciding?" }), question,
        h("p", { class: "bd-muted", text: "Score each option 1 (bad) to 5 (great) on each criterion. Weights say how much a criterion matters. Use evidence (what customers said, real quotes) where you can, not hope." }),
        h("div", { class: "bd-table-wrap" }, table),
        h("div", { class: "bd-row" },
          h("button", { type: "button", onclick: () => { if (d.options.length < 6) { d.options.push(`Option ${String.fromCharCode(65 + d.options.length)}`); drawTable(); redraw(); } } }, "+ Option"),
          h("button", { type: "button", onclick: () => { if (d.criteria.length < 10) { d.criteria.push({ name: "New criterion", w: 3 }); drawTable(); redraw(); } } }, "+ Criterion"))),
      out);
    drawResult();
  }

  // ------------------------------------------------------------------ Numbers (break-even + payback)
  function renderNumbers(body) {
    const n = S.numbers;
    const out = h("div", { class: "bd-out" });
    const field = (k, label, hint, step) => h("label", { class: "bd-field" }, h("span", { text: label }),
      h("input", { type: "number", step: step || "any", min: "0", value: String(n[k]), oninput: (e) => { n[k] = Number(e.target.value) || 0; save(); draw(); } }),
      hint ? h("small", { text: hint }) : null);
    const money = (v) => `${n.currency}${Math.round(v).toLocaleString()}`;
    const draw = () => {
      const margin = n.price - n.cost;
      const months = [];
      let cum = -n.startup, payback = 0;
      for (let k = 1; k <= 24; k++) {
        const sales = n.sales * Math.pow(1 + n.growth / 100, k - 1);
        const profit = sales * margin - n.fixed;
        cum += profit;
        if (!payback && cum >= 0) payback = k;
        months.push({ x: `M${k}`, monthly: Math.round(profit), cumulative: Math.round(cum) });
      }
      const be = margin > 0 ? Math.ceil(n.fixed / margin) : null;
      const chart = h("div", { class: "bd-chart" });
      const facts = margin <= 0
        ? [h("p", { class: "bd-note warn", text: "Each sale loses money (cost per sale is at or above the price). Raise the price, cut the cost per sale, or rethink the offer before anything else." })]
        : [h("div", { class: "bd-kpis" },
          h("div", {}, h("small", { text: "Profit per sale" }), h("strong", { text: money(margin) })),
          h("div", {}, h("small", { text: "Break-even" }), h("strong", { text: `${be.toLocaleString()} sales / month` })),
          h("div", {}, h("small", { text: "Month 1 profit" }), h("strong", { text: money(months[0].monthly) })),
          h("div", {}, h("small", { text: "Startup cost paid back" }), h("strong", { text: payback ? `month ${payback}` : "not within 24 months" }))),
        h("p", { class: "bd-note", text: n.sales >= be
          ? `You expect ${n.sales} sales in month 1, above the ${be} you need. Check that number by asking real customers before you spend the startup money.`
          : `You need ${be} sales a month to cover fixed costs but expect ${n.sales}. Find ${be - n.sales} more sales a month, raise the price, or cut fixed costs.` })];
      out.replaceChildren(card(h("h3", { text: "What the numbers say" }), facts, chart,
        h("p", { class: "bd-muted", text: "These are your estimates, not market data. Replace them with real quotes and what customers actually said." }),
        h("div", { class: "bd-row" }, h("button", { type: "button", class: "primary", onclick: () => host.ask(
          `My numbers (${n.currency}): price ${n.price}, cost per sale ${n.cost}, fixed costs ${n.fixed}/month, startup cost ${n.startup}, expected sales ${n.sales} in month 1, growth ${n.growth}%/month.` +
          (be ? ` Break-even is ${be} sales/month; payback ${payback ? "in month " + payback : "not within 24 months"}.` : " Each sale loses money.") +
          "\n\nWhat do these numbers mean for my decision, which number is the riskiest guess, and how do I check it this week?", "business") }, "Ask the business advisor"))));
      if (margin > 0 && root.JarvisCharts) {
        root.JarvisCharts.line(chart, { points: months.slice(0, 12), title: "First 12 months", subtitle: `Profit in ${n.currency}; below 0 means you're still paying back`,
          series: [{ key: "cumulative", label: "Total so far", slot: 0 }, { key: "monthly", label: "Each month", slot: 1 }], xLabel: "Month" });
      }
    };
    const cur = h("input", { type: "text", maxlength: "3", value: n.currency, "aria-label": "Currency symbol", oninput: (e) => { n.currency = e.target.value; save(); draw(); } });
    body.append(
      card(h("h3", { text: "Break-even and payback" }),
        h("div", { class: "bd-grid" },
          field("price", "Price per sale", "what a customer pays"),
          field("cost", "Cost per sale", "ingredients, packaging, fees per order"),
          field("fixed", "Fixed costs per month", "rent, hosting, salaries, subscriptions"),
          field("startup", "One-time startup cost", "equipment, setup, design"),
          field("sales", "Sales in month 1", "be honest: from real conversations", "1"),
          field("growth", "Growth per month (%)", "0 if unsure", "1"),
          h("label", { class: "bd-field" }, h("span", { text: "Currency" }), cur))),
      out);
    draw();
  }

  // ------------------------------------------------------------------ Hackathon
  function renderHackathon(body) {
    const k = S.hack;
    if (!k.start) {
      const d = new Date(Date.now() + 7 * 86400000);
      d.setHours(9, 0, 0, 0);
      k.start = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    }
    const out = h("div", { class: "bd-out" });
    const input = (key, label, attrs) => h("label", { class: "bd-field" }, h("span", { text: label }),
      h("input", { ...attrs, value: String(k[key]), oninput: (e) => { k[key] = attrs.type === "number" ? Number(e.target.value) : e.target.value; save(); } }));
    const CRIT = [["innovation", "Innovation"], ["impact", "Impact"], ["technical", "Technical"], ["design", "Design"], ["presentation", "Presentation"], ["feasibility", "Feasibility"]];
    const crit = h("div", { class: "bd-chips" }, CRIT.map(([id, label]) => h("button", { type: "button", "aria-pressed": String(k.criteria.includes(id)),
      onclick: (e) => { k.criteria = k.criteria.includes(id) ? k.criteria.filter((c) => c !== id) : [...k.criteria, id]; e.currentTarget.setAttribute("aria-pressed", String(k.criteria.includes(id))); save(); } }, label)));
    const send = async (addTasks) => {
      out.replaceChildren(h("p", { class: "bd-muted", text: "Planning…" }));
      try {
        S.hackPlan = await host.api("/api/build/hackathon", { method: "POST", body: { name: k.name || "Hackathon", start: k.start, hours: k.hours || 24,
          team: k.team.split(",").map((t) => t.trim()).filter(Boolean), theme: k.theme, criteria: k.criteria, add_tasks: addTasks } });
        if (addTasks) host.toast("Added to your tasks, one per phase.");
      } catch (err) {
        const pack = offlinePack();
        if (!unreachable(err) || !pack) { out.replaceChildren(h("p", { class: "bd-error", text: err.message || String(err) })); return; }
        try { S.hackPlan = localHackathon(pack, k); } catch (e) { out.replaceChildren(h("p", { class: "bd-error", text: e.message })); return; }
      }
      save();
      drawHack(out);
    };
    body.append(
      card(h("h3", { text: T("build.hackathon") }),
        h("div", { class: "bd-grid" },
          input("name", "Event name", { type: "text", maxlength: "120", placeholder: "e.g. DevNet Hack 2026" }),
          input("start", "Starts", { type: "datetime-local" }),
          input("hours", "Length (hours)", { type: "number", min: "2", max: "96", step: "1" }),
          input("team", "Team (names, comma separated)", { type: "text", maxlength: "300", placeholder: "You, Ana, Ben" }),
          input("theme", "Theme or problem (if known)", { type: "text", maxlength: "300" })),
        h("span", { class: "bd-label", text: "Judging criteria" }), crit,
        h("div", { class: "bd-row" }, h("button", { type: "button", class: "primary", onclick: () => send(false) }, "Make the plan"))),
      out);
    if (S.hackPlan) drawHack(out);
  }

  function drawHack(out) {
    const p = S.hackPlan;
    const when = (iso) => { const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" }); };
    out.replaceChildren(
      p.offline ? h("p", { class: "bd-note", text: "Made on this device (no connection right now). Adding it to Tasks needs Jarvis." }) : null,
      card(h("h3", { text: `${p.name}: ${p.hours} hours` }), p.theme ? h("p", { class: "bd-muted", text: "Theme: " + p.theme }) : null,
        h("ol", { class: "bd-timeline" }, p.phases.map((ph) => h("li", {},
          h("div", { class: "bd-time", text: `${when(ph.start)} – ${when(ph.end)} · ${ph.hours} h` }),
          h("strong", { text: ph.title }), list(ph.todo))))),
      card(h("h3", { text: "Team roles" }), h("ul", { class: "bd-list" }, p.team.map((m) => h("li", {}, h("strong", { text: m.name }), ": " + m.role)))),
      card(h("h3", { text: "Score well with the judges" }), h("ul", { class: "bd-list" }, p.criteria.map((c) => h("li", {}, h("strong", { text: c.id }), ": " + c.tip)))),
      card(h("h3", { text: "Before the event" }), list(p.before)),
      card(h("h3", { text: "Pitch outline" }), list(p.pitch, true)),
      card(h("h3", { text: "Cut these if time runs short" }), list(p.cut_list)),
      h("div", { class: "bd-row" },
        p.task_id ? h("span", { class: "bd-muted", text: "Added to Tasks ✓" }) : p.offline ? null : h("button", { type: "button", class: "primary", onclick: async () => {
          try {
            S.hackPlan = await host.api("/api/build/hackathon", { method: "POST", body: { name: p.name, start: p.start, hours: p.hours,
              team: p.team.map((m) => m.name), theme: p.theme, criteria: p.criteria.map((c) => c.id), add_tasks: true } });
            save(); drawHack(out); host.toast("Added to your tasks, one per phase.");
          } catch (err) { host.toast(err.message || String(err)); }
        } }, "Add to my tasks"),
        h("button", { type: "button", onclick: () => host.ask(`Hackathon: ${p.name}, ${p.hours} hours, team of ${p.team.length}${p.theme ? ", theme: " + p.theme : ""}.` +
          "\n\nHelp me pick a problem worth solving and a demo the judges will remember. Give me three ideas with the stack for each.", "hackathon") }, "Ask the hackathon coach")));
  }

  root.JarvisBuild = { render };
})(this);
