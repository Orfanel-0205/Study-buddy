/* Study page on the computer: flashcard decks, spaced-repetition reviews, and making
 * flashcards with the local model from your notes or photos of pages.
 * Uses the helpers app.js exposes as window.JarvisUI. */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  let review = null; // the review session in progress, if any

  function ui() { return window.JarvisUI; }

  async function render() {
    const { el, fill, api, showError } = ui();
    if (review) return renderReview();
    const page = $("#study-page");
    let decks;
    try { decks = await api("/api/study/decks"); } catch (err) { return showError(err); }
    const due = decks.reduce((n, d) => n + d.due, 0);
    fill(page,
      el("div", { class: "page-head" }, el("h2", { text: "Study" }), el("span", { class: "spacer" }),
        el("button", { onclick: () => makeWithAI(decks, null) }, "✨ Make flashcards with AI"),
        el("button", { class: "primary", onclick: () => editDeck(null) }, "+ New deck")),
      el("div", { class: "card study-hero" },
        el("div", { class: "grow" },
          el("h3", { text: due ? `${due} card${due === 1 ? "" : "s"} to review today` : decks.length ? "You're all caught up for today" : "Start studying" }),
          el("p", { class: "muted small", text: "Spaced repetition shows each card again just before you'd forget it. A few minutes every day works better than cramming." })),
        due ? el("button", { class: "primary", onclick: () => startReview(null) }, "Review now") : null),
      decks.length ? el("div", { class: "deck-grid" }, decks.map((d) => deckCard(d, decks)))
        : el("div", { class: "empty" }, "No decks yet. Create one, or let Jarvis make flashcards from your notes or a photo of a page."),
      el("p", { class: "muted small", style: "margin-top:16px", text: "Tip: in Chat, pick the “Study companion” mode for explanations, hints and quizzes, and attach a photo of your notes to ask about them." }));
  }

  function deckCard(d, decks) {
    const { el } = ui();
    return el("div", { class: "card deck" },
      el("div", { class: "row" }, el("h3", { class: "grow", text: d.name }),
        el("button", { class: "ghost small", title: "Rename or delete", onclick: () => editDeck(d) }, "⋯")),
      d.description ? el("p", { class: "muted small", text: d.description }) : null,
      el("div", { class: "row small muted" }, `${d.cards} card${d.cards === 1 ? "" : "s"}`,
        d.due ? el("span", { class: "badge caution", text: `${d.due} due` }) : el("span", { class: "badge safe", text: "up to date" }),
        d.new ? `${d.new} new` : null),
      el("div", { class: "row", style: "margin-top:10px" },
        el("button", { class: d.due ? "primary small" : "small", disabled: !d.due, onclick: () => startReview(d) }, "Review"),
        el("button", { class: "small", onclick: () => openDeck(d) }, "Cards"),
        el("button", { class: "small", onclick: () => makeWithAI(decks, d) }, "✨ Add with AI")));
  }

  // ------------------------------------------------------------------ decks
  function editDeck(deck) {
    const { el, api, openModal, confirmDialog, toast } = ui();
    const name = el("input", { type: "text", value: deck ? deck.name : "", maxlength: "120", placeholder: "e.g. Biology – cells" });
    const desc = el("input", { type: "text", value: deck ? deck.description : "", maxlength: "2000", placeholder: "Optional" });
    let modal = null;
    modal = openModal({
      title: deck ? "Edit deck" : "New deck",
      body: el("div", { class: "stack" }, el("label", { class: "field" }, el("span", { text: "Name" }), name),
        el("label", { class: "field" }, el("span", { text: "Description" }), desc),
        deck ? el("button", { class: "ghost", style: "color:var(--danger)", onclick: async () => {
          if (!(await confirmDialog({ title: "Delete deck?", message: `"${deck.name}" and all ${deck.cards} card(s) will be deleted.`, confirmLabel: "Delete", danger: true }))) return;
          await api(`/api/study/decks/${deck.id}`, { method: "DELETE" });
          modal.close();
          toast("Deck deleted", "ok");
          render();
        } }, "Delete this deck") : null),
      actions: [{ label: "Cancel" }, { label: deck ? "Save" : "Create", kind: "primary", onClick: async () => {
        if (!name.value.trim()) { toast("Give the deck a name.", "error"); return true; }
        const body = { name: name.value.trim(), description: desc.value.trim() };
        if (deck) await api(`/api/study/decks/${deck.id}`, { method: "PATCH", body });
        else await api("/api/study/decks", { method: "POST", body });
        render();
      } }],
    });
  }

  async function openDeck(deck) {
    const { el, fill, api, openModal, toast, showError } = ui();
    const list = el("div", { class: "card-list" });
    const front = el("input", { type: "text", placeholder: "Front (question or term)", maxlength: "2000" });
    const back = el("input", { type: "text", placeholder: "Back (answer)", maxlength: "4000" });
    const fileInput = el("input", { type: "file", accept: ".csv,.txt,.tsv,text/csv,text/plain", hidden: true });

    async function load() {
      let cards;
      try { cards = await api(`/api/study/decks/${deck.id}/cards`); } catch (err) { return showError(err); }
      fill(list, cards.length ? cards.map((c) => cardRow(c, load)) : el("p", { class: "muted", text: "No cards yet." }));
    }
    async function add() {
      if (!front.value.trim() || !back.value.trim()) return toast("Fill in both sides.", "error");
      await api(`/api/study/decks/${deck.id}/cards`, { method: "POST", body: { cards: [{ front: front.value, back: back.value }] } });
      front.value = ""; back.value = ""; front.focus();
      load();
    }
    back.addEventListener("keydown", (e) => { if (e.key === "Enter") add().catch(showError); });
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files[0];
      if (!file) return;
      try {
        const r = await api(`/api/study/decks/${deck.id}/import`, { method: "POST", body: { text: await file.text() } });
        toast(`Imported ${r.added} card${r.added === 1 ? "" : "s"}`, "ok");
        load();
      } catch (err) { showError(err); }
      fileInput.value = "";
    });
    openModal({
      title: deck.name, wide: true,
      body: el("div", { class: "stack" },
        el("div", { class: "row" }, el("div", { class: "grow" }, front), el("div", { class: "grow" }, back),
          el("button", { class: "primary", onclick: () => add().catch(showError) }, "Add card")),
        el("div", { class: "row small" },
          el("button", { class: "small", onclick: () => fileInput.click() }, "Import CSV / Anki / Quizlet…"),
          el("button", { class: "small", onclick: () => exportDeck(deck) }, "Export CSV"),
          el("span", { class: "muted", text: "Import format: one card per line, front and back separated by a comma or tab." }), fileInput),
        list),
      actions: [{ label: "Close", onClick: () => { render(); } }],
    });
    load();
  }

  function cardRow(c, reload) {
    const { el, api, toast, showError } = ui();
    const due = c.due <= new Date().toISOString().slice(0, 10);
    return el("div", { class: "card-row" },
      el("div", { class: "grow" }, el("div", { class: "card-front", text: c.front }), el("div", { class: "muted small", text: c.back })),
      el("span", { class: "muted small", title: `Reviewed ${c.reps} time(s), ${c.lapses} lapse(s)`, text: c.reps === 0 && !c.last_reviewed ? "new" : due ? "due" : `next ${c.due}` }),
      el("button", { class: "ghost small", onclick: () => editCard(c, reload) }, "Edit"),
      el("button", { class: "ghost small", "aria-label": "Delete card", onclick: async () => {
        try { await api(`/api/study/cards/${c.id}`, { method: "DELETE" }); toast("Card deleted", "ok"); reload(); } catch (err) { showError(err); }
      } }, "✕"));
  }

  function editCard(c, reload) {
    const { el, api, openModal } = ui();
    const front = el("textarea", { rows: 2 });
    const back = el("textarea", { rows: 3 });
    front.value = c.front;
    back.value = c.back;
    openModal({
      title: "Edit card",
      body: el("div", { class: "stack" }, el("label", { class: "field" }, el("span", { text: "Front" }), front),
        el("label", { class: "field" }, el("span", { text: "Back" }), back)),
      actions: [{ label: "Cancel" }, { label: "Save", kind: "primary", onClick: async () => {
        await api(`/api/study/cards/${c.id}`, { method: "PATCH", body: { front: front.value, back: back.value } });
        reload();
      } }],
    });
  }

  async function exportDeck(deck) {
    const { api, showError } = ui();
    try {
      const res = await api(`/api/study/decks/${deck.id}/export`, { raw: true });
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${deck.name}.csv`;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (err) { showError(err); }
  }

  // ------------------------------------------------------------------ make flashcards with AI
  function makeWithAI(decks, deck) {
    const { el, fill, api, openModal, toast, showError } = ui();
    const pictures = [];
    const notes = el("textarea", { rows: 7, placeholder: "Paste your notes, a textbook paragraph, or vocabulary… (you can also paste a screenshot here)" });
    const thumbs = el("div", { class: "thumbs" });
    const fileInput = el("input", { type: "file", accept: "image/*", multiple: true, hidden: true });
    const count = el("select", {}, [5, 10, 15, 20, 30].map((n) => el("option", { value: n, selected: n === 10 }, `${n} cards`)));
    const target = el("select", {}, el("option", { value: "" }, "New deck"),
      (decks || []).map((d) => el("option", { value: d.id, selected: deck && d.id === deck.id }, d.name)));
    if (!decks && deck) target.append(el("option", { value: deck.id, selected: true }, deck.name));

    async function addFiles(files) {
      for (const file of files) {
        if (pictures.length >= 4) { toast("Up to 4 pictures at a time.", "error"); break; }
        try { pictures.push(await window.JarvisImages.toDataUrl(file)); } catch (err) { showError(err); }
      }
      fill(thumbs, pictures.map((src, i) => el("span", { class: "thumb-wrap" }, window.JarvisImages.thumb(src),
        el("button", { class: "thumb-x", "aria-label": "Remove picture", onclick: () => { pictures.splice(i, 1); addFiles([]); } }, "✕"))));
    }
    fileInput.addEventListener("change", () => { addFiles([...fileInput.files]); fileInput.value = ""; });
    notes.addEventListener("paste", (e) => {
      const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
      if (files.length) { e.preventDefault(); addFiles(files); }
    });

    const body = el("div", { class: "stack" },
      el("label", { class: "field" }, el("span", { text: "Notes or text" }), notes),
      el("div", { class: "row" }, el("button", { onclick: () => fileInput.click() }, "📷 Add photos of pages or slides"), fileInput,
        el("span", { class: "muted small", text: "Jarvis reads the text in the picture first, then writes the cards." })),
      thumbs,
      el("div", { class: "grid2" }, el("label", { class: "field" }, el("span", { text: "Save to" }), target),
        el("label", { class: "field" }, el("span", { text: "How many" }), count)));

    const modal = openModal({
      title: "Make flashcards with AI", body, wide: true,
      actions: [{ label: "Cancel" }, { label: "Make cards", kind: "primary", busy: "Reading and writing cards…", onClick: async () => {
        if (!notes.value.trim() && !pictures.length) { toast("Paste some notes or add a photo first.", "error"); return true; }
        const result = await api("/api/study/generate", { method: "POST", body: { text: notes.value, images: pictures, count: parseInt(count.value, 10) } });
        showResult(result);
        return true;
      } }],
    });

    function showResult(result) {
      const rows = result.cards.map((c) => ({ check: el("input", { type: "checkbox", checked: true }),
        front: el("input", { type: "text", value: c.front }), back: el("textarea", { rows: 2 }, c.back) }));
      const deckName = el("input", { type: "text", value: result.title || "New deck", maxlength: "120" });
      fill(body,
        result.transcript ? el("details", { class: "transcript" }, el("summary", { text: "Text Jarvis read from the picture(s) — check for mistakes" }),
          el("pre", { text: result.transcript })) : null,
        !target.value ? el("label", { class: "field" }, el("span", { text: "New deck name" }), deckName) : null,
        el("p", { class: "muted small", text: "Check each card: small models can make mistakes. Untick or edit any before saving." }),
        el("ol", { class: "steps-edit" }, rows.map((r) => el("li", {}, r.check, el("div", { class: "grow" }, r.front, r.back)))));
      modal.setActions([{ label: "Cancel" }, { label: "Save cards", kind: "primary", onClick: async () => {
        const cards = rows.filter((r) => r.check.checked && r.front.value.trim() && r.back.value.trim())
          .map((r) => ({ front: r.front.value.trim(), back: r.back.value.trim() }));
        if (!cards.length) { toast("Select at least one card.", "error"); return true; }
        let deckId = target.value;
        if (!deckId) deckId = (await api("/api/study/decks", { method: "POST", body: { name: deckName.value.trim() || "New deck", description: "" } })).id;
        await api(`/api/study/decks/${deckId}/cards`, { method: "POST", body: { cards } });
        toast(`Saved ${cards.length} card${cards.length === 1 ? "" : "s"}`, "ok");
        render();
      } }]);
    }
  }

  // ------------------------------------------------------------------ review session
  async function startReview(deck) {
    const { api, showError, toast } = ui();
    let cards;
    try { cards = await api("/api/study/due" + (deck ? `?deck_id=${deck.id}` : "")); } catch (err) { return showError(err); }
    if (!cards.length) return toast("Nothing to review right now.", "ok");
    review = { deck, queue: cards, index: 0, shown: false, done: 0, again: {} };
    document.addEventListener("keydown", onKey);
    renderReview();
  }

  function endReview() {
    review = null;
    document.removeEventListener("keydown", onKey);
    render();
  }

  function onKey(e) {
    if (!review || e.target.matches("input, textarea, select") || document.querySelector(".modal-backdrop")) return;
    if (!review.shown && (e.key === " " || e.key === "Enter")) { e.preventDefault(); review.shown = true; renderReview(); }
    else if (review.shown && ["1", "2", "3", "4"].includes(e.key)) grade(["again", "hard", "good", "easy"][+e.key - 1]);
  }

  function renderReview() {
    const { el, fill } = ui();
    const page = $("#study-page");
    const r = review;
    if (r.index >= r.queue.length) {
      fill(page, el("div", { class: "review" }, el("div", { class: "flashcard done" },
        el("div", { class: "flash-front", text: "🎉 Session complete" }),
        el("p", { class: "muted", text: `You reviewed ${r.done} card${r.done === 1 ? "" : "s"}. The next ones will be ready when they're due.` }),
        el("button", { class: "primary", onclick: endReview }, "Back to decks"))));
      return;
    }
    const card = r.queue[r.index];
    const next = card.next || {};
    const days = (n) => (n === undefined ? "" : n <= 1 ? "1 day" : `${n} days`);
    fill(page, el("div", { class: "review" },
      el("div", { class: "row" }, el("strong", { text: r.deck ? r.deck.name : "All decks" }),
        el("span", { class: "muted small", text: `${r.index + 1} of ${r.queue.length}` }), el("span", { class: "spacer" }),
        el("button", { class: "ghost small", onclick: endReview }, "End session")),
      el("div", { class: "progress" }, el("div", { style: `width:${Math.round((100 * r.index) / r.queue.length)}%` })),
      el("div", { class: "flashcard" },
        el("div", { class: "flash-front", text: card.front }),
        r.shown ? el("div", { class: "flash-back", text: card.back }) : null),
      r.shown
        ? el("div", { class: "grades" },
          el("button", { class: "grade again", onclick: () => grade("again") }, el("strong", { text: "Again" }), el("small", { text: "1 · forgot" })),
          el("button", { class: "grade hard", onclick: () => grade("hard") }, el("strong", { text: "Hard" }), el("small", { text: `2 · ${days(next.hard)}` })),
          el("button", { class: "grade good", onclick: () => grade("good") }, el("strong", { text: "Good" }), el("small", { text: `3 · ${days(next.good)}` })),
          el("button", { class: "grade easy", onclick: () => grade("easy") }, el("strong", { text: "Easy" }), el("small", { text: `4 · ${days(next.easy)}` })))
        : el("button", { class: "primary show-answer", onclick: () => { r.shown = true; renderReview(); } }, "Show answer  (Space)")));
  }

  async function grade(g) {
    const { api, showError } = ui();
    const r = review;
    const card = r.queue[r.index];
    try {
      await api(`/api/study/cards/${card.id}/review`, { method: "POST", body: { grade: g } });
    } catch (err) { return showError(err); }
    r.done += 1;
    if (g === "again" && (r.again[card.id] || 0) < 3) {
      r.again[card.id] = (r.again[card.id] || 0) + 1;
      r.queue.push({ ...card, next: null }); // see it again later in this session
    }
    r.index += 1;
    r.shown = false;
    renderReview();
  }

  window.JarvisStudy = { render };
})();
