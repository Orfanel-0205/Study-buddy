/* Small offline chart kit (inline SVG, no libraries) shared by the computer and phone pages.
 * Follows one set of rules everywhere: thin marks with a rounded data end, hairline grid, a legend for
 * two or more series, hover/focus tooltips, and a "Show as table" view so no value depends on color
 * or hovering. Colors come from CSS variables (--series-1..3) defined for light and dark mode. */
(function (root) {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const SLOTS = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];

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
  function s(tag, attrs) {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== undefined && v !== null) node.setAttribute(k, v);
    return node;
  }

  const compact = (n) => (Math.abs(n) >= 1e6 ? (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M"
    : Math.abs(n) >= 1e3 ? (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K" : String(Math.round(n * 100) / 100));

  function niceMax(v) {
    if (v <= 0) return 4;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 2, 2.5, 4, 5, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }
  function niceRange(min, max) {
    if (min === max) { min -= 1; max += 1; }
    const span = niceMax(max - min);
    const step = span / 4;
    const lo = Math.floor(min / step) * step;
    return { lo, hi: lo + step * Math.ceil((max - lo) / step), step };
  }

  /** A path for a bar with a 4px rounded data end and a square base. */
  function barPath(x, yTop, w, yBase, r) {
    const hgt = yBase - yTop;
    if (hgt <= 0) return "";
    r = Math.min(r, w / 2, hgt);
    return `M${x},${yBase}V${yTop + r}Q${x},${yTop} ${x + r},${yTop}H${x + w - r}Q${x + w},${yTop} ${x + w},${yTop + r}V${yBase}Z`;
  }

  function shortDate(iso) {
    const d = new Date(iso + "T00:00:00");
    return isNaN(d) ? iso : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  // ------------------------------------------------------------------ frame: title, legend, chart/table toggle
  function frame(el, { title, subtitle, series, rows, columns }) {
    const body = h("div", { class: "viz-body" });
    const tableWrap = h("div", { class: "viz-table", hidden: true });
    const toggle = h("button", { type: "button", class: "viz-toggle", "aria-pressed": "false", onclick: () => {
      const showTable = tableWrap.hidden;
      tableWrap.hidden = !showTable;
      body.hidden = showTable;
      toggle.setAttribute("aria-pressed", String(showTable));
      toggle.textContent = showTable ? "Show chart" : "Show as table";
    } }, "Show as table");
    tableWrap.append(h("table", {}, h("thead", {}, h("tr", {}, columns.map((c) => h("th", { scope: "col", text: c })))),
      h("tbody", {}, rows.map((r) => h("tr", {}, r.map((v, i) => (i === 0 ? h("th", { scope: "row", text: v }) : h("td", { text: v }))))))));
    const legend = series && series.length > 1 ? h("ul", { class: "viz-legend" }, series.map((sr, i) =>
      h("li", {}, h("span", { class: "viz-swatch", style: `background:${SLOTS[sr.slot ?? i]}` }), sr.label))) : null;
    el.replaceChildren(h("div", { class: "viz" },
      h("div", { class: "viz-head" }, h("div", { class: "viz-titles" }, title ? h("h4", { text: title }) : null,
        subtitle ? h("p", { class: "viz-sub", text: subtitle }) : null), toggle),
      legend, body, tableWrap));
    return body;
  }

  function tooltip(body) {
    const tip = h("div", { class: "viz-tip", role: "status", hidden: true });
    body.append(tip);
    return {
      show(x, y, lines) {
        tip.replaceChildren(...lines.map(([value, label, slot]) => h("div", { class: "viz-tip-row" },
          slot !== undefined ? h("span", { class: "viz-key", style: `background:${SLOTS[slot]}` }) : null,
          h("strong", { text: value }), label ? h("span", { text: " " + label }) : null)));
        tip.hidden = false;
        const bw = body.clientWidth;
        tip.style.left = Math.max(4, Math.min(x + 12, bw - tip.offsetWidth - 4)) + "px";
        tip.style.top = Math.max(0, y - tip.offsetHeight - 8) + "px";
      },
      hide() { tip.hidden = true; },
    };
  }

  // ------------------------------------------------------------------ columns (one or stacked series over time / categories)
  function columns(el, opts) {
    const { data, series, title, subtitle, height = 180, dates = true, unit = "" } = opts;
    const cols = [dates ? "Date" : "Category", ...series.map((sr) => sr.label), ...(series.length > 1 ? ["Total"] : [])];
    const rows = data.map((d) => {
      const vals = series.map((sr) => d.values[sr.key] || 0);
      return [dates ? shortDate(d.label) : d.label, ...vals.map(String), ...(series.length > 1 ? [String(vals.reduce((a, b) => a + b, 0))] : [])];
    });
    const body = frame(el, { title, subtitle, series, rows, columns: cols });
    const totals = data.map((d) => series.reduce((a, sr) => a + (d.values[sr.key] || 0), 0));
    if (!totals.some((t) => t > 0)) {
      body.append(h("p", { class: "viz-empty", text: opts.empty || "Nothing recorded in this period yet." }));
      return;
    }
    const W = Math.max(280, body.clientWidth || el.clientWidth || 600);
    const pad = { l: 34, r: 8, t: 10, b: 24 };
    // Counts get whole-number ticks: a scale of 0-4 instead of 0, 0.5, 1, 1.5, 2.
    const whole = totals.every(Number.isInteger);
    const max = whole && Math.max(...totals) <= 4 ? 4 : niceMax(Math.max(...totals));
    const plotW = W - pad.l - pad.r, plotH = height - pad.t - pad.b;
    const band = plotW / data.length;
    const bw = Math.max(2, Math.min(24, band * 0.7));
    const svg = s("svg", { viewBox: `0 0 ${W} ${height}`, width: "100%", height, role: "img",
      "aria-label": `${title || "Chart"}. Use "Show as table" to read every value.` });
    for (let i = 0; i <= 4; i++) {
      const v = (max / 4) * i, y = pad.t + plotH - (v / max) * plotH;
      svg.append(s("line", { x1: pad.l, x2: W - pad.r, y1: y, y2: y, class: i === 0 ? "viz-axis" : "viz-grid" }));
      const t = s("text", { x: pad.l - 6, y: y + 4, "text-anchor": "end", class: "viz-tick" });
      t.textContent = compact(v);
      svg.append(t);
    }
    const every = Math.ceil(data.length / Math.max(2, Math.floor(plotW / 64)));
    const tip = tooltip(body);
    data.forEach((d, i) => {
      const x = pad.l + band * i + (band - bw) / 2;
      let base = pad.t + plotH;
      series.forEach((sr, si) => {
        const v = d.values[sr.key] || 0;
        if (!v) return;
        const hgt = (v / max) * plotH;
        const isTop = series.slice(si + 1).every((o) => !(d.values[o.key] || 0));
        const top = base - hgt;
        const gap = si > 0 ? 2 : 0; // surface gap between stacked segments
        svg.append(s("path", { d: isTop ? barPath(x, top, bw, base - gap, 4) : `M${x},${base - gap}V${top}H${x + bw}V${base - gap}Z`,
          fill: SLOTS[sr.slot ?? si], class: "viz-mark" }));
        base = top;
      });
      const last = i === data.length - 1;
      if (last || (i % every === 0 && data.length - 1 - i >= Math.max(1, every * 0.6))) { // keep clear of the last label
        const t = s("text", { x: x + bw / 2, y: height - 6, "text-anchor": "middle", class: "viz-tick" });
        t.textContent = dates ? shortDate(d.label) : d.label;
        svg.append(t);
      }
      const hit = s("rect", { x: pad.l + band * i, y: pad.t, width: band, height: plotH, class: "viz-hit", tabindex: "0",
        "aria-label": `${dates ? shortDate(d.label) : d.label}: ${series.map((sr) => `${sr.label} ${d.values[sr.key] || 0}`).join(", ")}` });
      const showTip = () => {
        hit.classList.add("on");
        tip.show(pad.l + band * i + band / 2, pad.t + plotH - (totals[i] / max) * plotH,
          [[dates ? shortDate(d.label) : d.label, ""], ...series.map((sr, si) => [String(d.values[sr.key] || 0) + unit, sr.label, sr.slot ?? si])]);
      };
      hit.addEventListener("pointerenter", showTip);
      hit.addEventListener("focus", showTip);
      hit.addEventListener("pointerleave", () => { hit.classList.remove("on"); tip.hide(); });
      hit.addEventListener("blur", () => { hit.classList.remove("on"); tip.hide(); });
      svg.append(hit);
    });
    body.prepend(svg);
  }

  // ------------------------------------------------------------------ horizontal bars (one series, sorted by the caller)
  function hbars(el, opts) {
    const { rows, title, subtitle, format = (r) => String(r.value), max: givenMax } = opts;
    const body = frame(el, { title, subtitle, rows: rows.map((r) => [r.label, format(r)]), columns: ["", opts.valueLabel || "Value"] });
    if (!rows.length || !rows.some((r) => r.value > 0 || r.max)) {
      body.append(h("p", { class: "viz-empty", text: opts.empty || "Nothing recorded yet." }));
      return;
    }
    const max = givenMax || Math.max(...rows.map((r) => r.max || r.value), 1);
    body.append(h("div", { class: "viz-hbars" }, rows.map((r) => h("div", { class: "viz-hrow" },
      h("span", { class: "viz-hlabel", text: r.label }),
      h("span", { class: "viz-htrack", title: `${r.label}: ${format(r)}` },
        r.max ? h("span", { class: "viz-hmax", style: `width:${(r.max / max) * 100}%` }) : null,
        h("span", { class: "viz-hfill", style: `width:${(r.value / max) * 100}%` })),
      h("span", { class: "viz-hvalue", text: format(r) })))));
  }

  // ------------------------------------------------------------------ line (time or numeric x; up to three series)
  function line(el, opts) {
    const { points, series, title, subtitle, height = 200, xLabel = "", xIsDate = false } = opts;
    const cols = [xLabel || "x", ...series.map((sr) => sr.label)];
    const rows = points.map((p) => [xIsDate ? shortDate(p.x) : String(p.x), ...series.map((sr) => p[sr.key] == null ? "" : String(p[sr.key]))]);
    const body = frame(el, { title, subtitle, series, rows, columns: cols });
    if (points.length < 2) { body.append(h("p", { class: "viz-empty", text: "Needs at least two points." })); return; }
    const W = Math.max(280, body.clientWidth || el.clientWidth || 600);
    const pad = { l: 40, r: 12, t: 10, b: 24 };
    const vals = points.flatMap((p) => series.map((sr) => p[sr.key])).filter((v) => typeof v === "number" && isFinite(v));
    const { lo, hi, step } = niceRange(Math.min(0, ...vals), Math.max(...vals));
    const plotW = W - pad.l - pad.r, plotH = height - pad.t - pad.b;
    const X = (i) => pad.l + (plotW * i) / (points.length - 1);
    const Y = (v) => pad.t + plotH - ((v - lo) / (hi - lo)) * plotH;
    const svg = s("svg", { viewBox: `0 0 ${W} ${height}`, width: "100%", height, role: "img", "aria-label": `${title || "Line chart"}. Use "Show as table" to read every value.` });
    for (let v = lo; v <= hi + step / 2; v += step) {
      svg.append(s("line", { x1: pad.l, x2: W - pad.r, y1: Y(v), y2: Y(v), class: Math.abs(v) < 1e-9 ? "viz-axis" : "viz-grid" }));
      const t = s("text", { x: pad.l - 6, y: Y(v) + 4, "text-anchor": "end", class: "viz-tick" });
      t.textContent = compact(v);
      svg.append(t);
    }
    const every = Math.ceil(points.length / Math.max(2, Math.floor(plotW / 70)));
    points.forEach((p, i) => {
      if (i % every && i !== points.length - 1) return;
      const t = s("text", { x: X(i), y: height - 6, "text-anchor": "middle", class: "viz-tick" });
      t.textContent = xIsDate ? shortDate(p.x) : String(p.x).slice(0, 12);
      svg.append(t);
    });
    series.forEach((sr, si) => {
      const d = points.map((p, i) => (typeof p[sr.key] === "number" ? `${i === 0 ? "M" : "L"}${X(i)},${Y(p[sr.key])}` : "")).join("");
      if (series.length === 1) svg.append(s("path", { d: `${d}L${X(points.length - 1)},${Y(Math.max(lo, 0))}L${X(0)},${Y(Math.max(lo, 0))}Z`, fill: SLOTS[sr.slot ?? si], class: "viz-area" }));
      svg.append(s("path", { d, stroke: SLOTS[sr.slot ?? si], class: "viz-line" }));
      const last = points[points.length - 1][sr.key];
      if (typeof last === "number") svg.append(s("circle", { cx: X(points.length - 1), cy: Y(last), r: 4, fill: SLOTS[sr.slot ?? si], class: "viz-dot" }));
    });
    const cross = s("line", { y1: pad.t, y2: pad.t + plotH, class: "viz-cross", visibility: "hidden" });
    svg.append(cross);
    const tip = tooltip(body);
    const hit = s("rect", { x: pad.l, y: pad.t, width: plotW, height: plotH, class: "viz-hit", tabindex: "0", "aria-label": "Move along the chart to read values" });
    let focusIndex = points.length - 1;
    const at = (i) => {
      const p = points[i];
      cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("visibility", "visible");
      tip.show(X(i), pad.t + 10, [[xIsDate ? shortDate(p.x) : String(p.x), ""], ...series.map((sr, si) => [p[sr.key] == null ? "–" : compact(p[sr.key]), sr.label, sr.slot ?? si])]);
    };
    hit.addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect();
      const x = ((e.clientX - r.left) / r.width) * W;
      focusIndex = Math.max(0, Math.min(points.length - 1, Math.round(((x - pad.l) / plotW) * (points.length - 1))));
      at(focusIndex);
    });
    hit.addEventListener("focus", () => at(focusIndex));
    hit.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); focusIndex = Math.max(0, Math.min(points.length - 1, focusIndex + (e.key === "ArrowRight" ? 1 : -1))); at(focusIndex); }
    });
    const off = () => { cross.setAttribute("visibility", "hidden"); tip.hide(); };
    hit.addEventListener("pointerleave", off);
    hit.addEventListener("blur", off);
    svg.append(hit);
    body.prepend(svg);
  }

  // ------------------------------------------------------------------ scatter (two numbers)
  function scatter(el, opts) {
    const { points, title, subtitle, xLabel = "x", yLabel = "y", height = 220 } = opts;
    const body = frame(el, { title, subtitle, rows: points.map((p) => [p.label || "", String(p.x), String(p.y)]), columns: ["", xLabel, yLabel] });
    const W = Math.max(280, body.clientWidth || el.clientWidth || 600);
    const pad = { l: 44, r: 12, t: 10, b: 30 };
    const xr = niceRange(Math.min(...points.map((p) => p.x)), Math.max(...points.map((p) => p.x)));
    const yr = niceRange(Math.min(...points.map((p) => p.y)), Math.max(...points.map((p) => p.y)));
    const plotW = W - pad.l - pad.r, plotH = height - pad.t - pad.b;
    const X = (v) => pad.l + ((v - xr.lo) / (xr.hi - xr.lo)) * plotW;
    const Y = (v) => pad.t + plotH - ((v - yr.lo) / (yr.hi - yr.lo)) * plotH;
    const svg = s("svg", { viewBox: `0 0 ${W} ${height}`, width: "100%", height, role: "img", "aria-label": `${title || "Scatter plot"} of ${yLabel} against ${xLabel}` });
    for (let v = yr.lo; v <= yr.hi + yr.step / 2; v += yr.step) {
      svg.append(s("line", { x1: pad.l, x2: W - pad.r, y1: Y(v), y2: Y(v), class: "viz-grid" }));
      const t = s("text", { x: pad.l - 6, y: Y(v) + 4, "text-anchor": "end", class: "viz-tick" }); t.textContent = compact(v); svg.append(t);
    }
    for (let v = xr.lo; v <= xr.hi + xr.step / 2; v += xr.step) {
      const t = s("text", { x: X(v), y: height - 14, "text-anchor": "middle", class: "viz-tick" }); t.textContent = compact(v); svg.append(t);
    }
    const xl = s("text", { x: W - pad.r, y: height - 2, "text-anchor": "end", class: "viz-tick" }); xl.textContent = xLabel; svg.append(xl);
    const tip = tooltip(body);
    points.slice(0, 2000).forEach((p) => {
      svg.append(s("circle", { cx: X(p.x), cy: Y(p.y), r: 4, fill: SLOTS[0], class: "viz-dot" }));
      const hit = s("circle", { cx: X(p.x), cy: Y(p.y), r: 12, class: "viz-hit", tabindex: "0", "aria-label": `${p.label || ""} ${xLabel} ${p.x}, ${yLabel} ${p.y}` });
      const show = () => tip.show(X(p.x), Y(p.y), [[String(p.y), yLabel], [String(p.x), xLabel], ...(p.label ? [[p.label, ""]] : [])]);
      hit.addEventListener("pointerenter", show); hit.addEventListener("focus", show);
      hit.addEventListener("pointerleave", () => tip.hide()); hit.addEventListener("blur", () => tip.hide());
      svg.append(hit);
    });
    body.prepend(svg);
  }

  // ------------------------------------------------------------------ stat tiles
  function tiles(el, items) {
    el.replaceChildren(h("div", { class: "viz-tiles" }, items.map((t) => h("div", { class: "viz-tile" },
      h("span", { class: "viz-tile-label", text: t.label }),
      h("strong", { class: "viz-tile-value", text: t.value }),
      t.note ? h("span", { class: "viz-tile-note", text: t.note }) : null))));
  }

  // ------------------------------------------------------------------ chart suggestions for a table of data
  function parseTable(text) {
    const lines = text.replace(/\r/g, "").split("\n").filter((l) => l.trim());
    if (lines.length < 2) return null;
    const delim = lines[0].includes("\t") ? "\t" : (lines[0].split(";").length > lines[0].split(",").length ? ";" : ",");
    const split = (line) => {
      const out = []; let cur = "", q = false;
      for (let i = 0; i < line.length; i++) {
        const c = line[i];
        if (q) { if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') q = false; else cur += c; }
        else if (c === '"') q = true; else if (c === delim) { out.push(cur.trim()); cur = ""; } else cur += c;
      }
      out.push(cur.trim());
      return out;
    };
    const header = split(lines[0]).map((x, i) => x || `Column ${i + 1}`);
    const rows = lines.slice(1, 5001).map(split).filter((r) => r.some((v) => v !== ""));
    return { header, rows };
  }

  function profile(table) {
    const num = (v) => { const n = Number(String(v).replace(/[, %$₱€£]/g, "")); return v !== "" && isFinite(n) ? n : null; };
    const isDate = (v) => /^\d{4}-\d{1,2}(-\d{1,2})?([ T].*)?$/.test(v) || /^\d{1,2}\/\d{1,2}\/\d{2,4}$/.test(v) || /^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* ?\d{0,4}$/i.test(v);
    return table.header.map((name, i) => {
      const vals = table.rows.map((r) => r[i] ?? "").filter((v) => v !== "");
      const nums = vals.map(num).filter((n) => n !== null);
      const dates = vals.filter(isDate).length;
      const distinct = new Set(vals).size;
      let type = "text";
      if (vals.length && dates / vals.length > 0.8) type = "date";
      else if (vals.length && nums.length / vals.length > 0.9) type = "number";
      else if (vals.length > 5 && distinct === vals.length) type = "label"; // every value different: a name or id
      else if (distinct <= Math.max(12, vals.length * 0.5)) type = "category";
      return { name, index: i, type, distinct, count: vals.length };
    });
  }

  /** Suggest charts for a table: returns [{kind, title, why, columns}] best first. */
  function suggest(table) {
    const cols = profile(table);
    const nums = cols.filter((c) => c.type === "number");
    const cats = cols.filter((c) => c.type === "category");
    const dates = cols.filter((c) => c.type === "date");
    const out = [];
    if (table.rows.length === 1 && nums.length) {
      out.push({ kind: "tiles", title: "Stat tiles", why: "There's only one row: the numbers themselves are the clearest way to show it.", columns: nums.slice(0, 4).map((c) => c.index) });
    }
    if (dates.length && nums.length) {
      out.push({ kind: "line", title: `Line chart: ${nums.slice(0, 3).map((c) => c.name).join(", ")} over ${dates[0].name}`,
        why: "A date column plus numbers: a line shows the trend over time. Up to three series stay readable; more need separate charts.",
        columns: [dates[0].index, ...nums.slice(0, 3).map((c) => c.index)] });
    }
    if (cats.length && nums.length) {
      const c = cats[0];
      out.push({ kind: "bars", title: `Bar chart: ${nums[0].name} by ${c.name}`,
        why: c.distinct > 12 ? `Compare amounts across ${c.distinct} categories; showing the top 12 (sorted), the rest in "Other".`
          : "A category plus a number: bars sorted from largest to smallest make comparisons easy. Avoid pie charts for close values.",
        columns: [c.index, nums[0].index] });
      if (cats.length >= 2) {
        out.push({ kind: "info", title: `Stacked or grouped bars: ${nums[0].name} by ${cats[0].name} and ${cats[1].name}`,
          why: "Two categories and a number: use stacked bars for part-to-whole, grouped bars to compare within groups, or a heatmap for many combinations. (Not drawn here.)", columns: [] });
      }
    }
    const labels = cols.filter((c) => c.type === "label");
    if (nums.length >= 2) {
      out.push({ kind: "scatter", title: `Scatter plot: ${nums[1].name} against ${nums[0].name}`,
        why: "Two number columns: a scatter plot shows whether they move together. The correlation (r) is under the chart.",
        columns: [nums[0].index, nums[1].index, ...(labels.length ? [labels[0].index] : [])] });
    }
    if (!cats.length && labels.length && nums.length && table.rows.length <= 30) {
      out.push({ kind: "bars", title: `Bar chart: ${nums[0].name} for each ${labels[0].name}`,
        why: `Each row is a different ${labels[0].name}, so sorted bars compare them one by one.`, columns: [labels[0].index, nums[0].index] });
    }
    if (nums.length) {
      out.push({ kind: "histogram", title: `Histogram of ${nums[0].name}`,
        why: "One number column: a histogram shows how the values are spread out (typical values, outliers).", columns: [nums[0].index] });
    }
    if (!out.length) out.push({ kind: "info", title: "A table", why: "No number columns were found, so a chart can't show amounts. Count the rows per category first, or keep it as a table.", columns: [] });
    return { columns: cols, suggestions: out };
  }

  function draw(el, table, sug) {
    const num = (v) => Number(String(v).replace(/[, %$₱€£]/g, ""));
    const col = (i) => table.rows.map((r) => r[i] ?? "");
    if (sug.kind === "line") {
      const [di, ...ni] = sug.columns;
      const pts = table.rows.map((r) => ({ x: r[di], ...Object.fromEntries(ni.map((i) => [`c${i}`, isFinite(num(r[i])) && r[i] !== "" ? num(r[i]) : null])) }))
        .sort((a, b) => (Date.parse(a.x) || 0) - (Date.parse(b.x) || 0));
      line(el, { points: pts, series: ni.map((i, k) => ({ key: `c${i}`, label: table.header[i], slot: k })), title: sug.title, xLabel: table.header[di] });
    } else if (sug.kind === "bars") {
      const [ci, ni] = sug.columns;
      const sums = new Map();
      table.rows.forEach((r) => { const k = r[ci] || "(blank)"; sums.set(k, (sums.get(k) || 0) + (isFinite(num(r[ni])) ? num(r[ni]) : 0)); });
      let rows = [...sums.entries()].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value);
      if (rows.length > 12) rows = [...rows.slice(0, 11), { label: "Other", value: rows.slice(11).reduce((a, r) => a + r.value, 0) }];
      hbars(el, { rows, title: sug.title, valueLabel: table.header[ni], format: (r) => compact(r.value) });
    } else if (sug.kind === "scatter") {
      const [xi, yi, li] = sug.columns;
      const pts = table.rows.map((r) => ({ x: num(r[xi]), y: num(r[yi]), label: li !== undefined ? r[li] : "" })).filter((p) => isFinite(p.x) && isFinite(p.y));
      scatter(el, { points: pts, title: sug.title, xLabel: table.header[xi], yLabel: table.header[yi], subtitle: `Correlation r = ${correlation(pts).toFixed(2)} (1 = rise together, −1 = opposite, 0 = no straight-line link)` });
    } else if (sug.kind === "histogram") {
      const vals = col(sug.columns[0]).map(num).filter(isFinite);
      const lo = Math.min(...vals), hi = Math.max(...vals);
      const bins = Math.min(12, Math.max(4, Math.ceil(Math.sqrt(vals.length))));
      const width = (hi - lo) / bins || 1;
      const counts = Array.from({ length: bins }, (_, i) => ({ label: `${compact(lo + i * width)}–${compact(lo + (i + 1) * width)}`, values: { n: 0 } }));
      vals.forEach((v) => { counts[Math.min(bins - 1, Math.floor((v - lo) / width))].values.n += 1; });
      columns(el, { data: counts, series: [{ key: "n", label: "Rows" }], title: sug.title, dates: false });
    } else if (sug.kind === "tiles") {
      tiles(el, sug.columns.map((i) => ({ label: table.header[i], value: compact(num(table.rows[0][i])) })));
    } else {
      el.replaceChildren(h("p", { class: "viz-empty", text: sug.why }));
    }
  }

  function correlation(pts) {
    const n = pts.length;
    if (n < 3) return 0;
    const mx = pts.reduce((a, p) => a + p.x, 0) / n, my = pts.reduce((a, p) => a + p.y, 0) / n;
    let sxy = 0, sxx = 0, syy = 0;
    for (const p of pts) { sxy += (p.x - mx) * (p.y - my); sxx += (p.x - mx) ** 2; syy += (p.y - my) ** 2; }
    return sxx && syy ? sxy / Math.sqrt(sxx * syy) : 0;
  }

  root.JarvisCharts = { columns, hbars, line, scatter, tiles, parseTable, profile, suggest, draw, correlation, compact };
})(this);
