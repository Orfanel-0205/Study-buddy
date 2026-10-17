// Run with:  node --test tests/js/markdown.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { renderMarkdown, pathFromLine, toSpeech } = require(path.join(__dirname, "..", "..", "jarvis", "static", "markdown.js"));

test("escapes raw HTML so model output cannot inject markup", () => {
  const html = renderMarkdown('<script>alert(1)</script> <img src=x onerror="alert(1)">');
  assert.ok(!html.includes("<script>"));
  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("&lt;script&gt;"));
});

test("only safe link protocols become links", () => {
  assert.ok(renderMarkdown("[docs](https://example.com/a?b=1&c=2)").includes('<a href="https://example.com/a?b=1&amp;c=2"'));
  const js = renderMarkdown("[click](javascript:alert(1))");
  assert.ok(!js.includes("<a"));
  assert.ok(!js.includes('href="javascript'));
  const quoted = renderMarkdown('[x](https://e.com/"onmouseover="alert(1))');
  assert.ok(!/href="[^"]*"onmouseover/.test(quoted));
});

test("code blocks are escaped and keep their language and file path", () => {
  const md = "File: src/app.py\n```python\nif a < b:\n    print('<b>')\n```";
  const html = renderMarkdown(md);
  assert.ok(html.includes('data-lang="python"'));
  assert.ok(html.includes('data-path="src/app.py"'));
  assert.ok(html.includes("if a &lt; b:"));
  assert.ok(!html.includes("<b>"));
});

test("path hints from fence info and bold headings", () => {
  assert.ok(renderMarkdown("```js src/index.js\nx\n```").includes('data-path="src/index.js"'));
  assert.ok(renderMarkdown('```python title="pkg/mod.py"\nx\n```').includes('data-path="pkg/mod.py"'));
  assert.equal(pathFromLine("**`tests/test_app.py`**"), "tests/test_app.py");
  assert.equal(pathFromLine("### src/main.rs"), "");
  assert.equal(pathFromLine("Here is the updated code:"), "");
  assert.equal(pathFromLine("File: ../../etc/passwd"), "");
  assert.equal(pathFromLine("**File:** `web/app.ts`"), "web/app.ts");
});

test("shell blocks are marked as runnable and unclosed fences stay code while streaming", () => {
  assert.ok(renderMarkdown("```bash\nnpm test\n```").includes('data-shell="1"'));
  const partial = renderMarkdown("Text\n```python\ndef f():\n");
  assert.ok(partial.includes('data-open="1"') && partial.includes("def f():"));
});

test("lists, tables, headings and inline formatting", () => {
  const html = renderMarkdown("## Title\n- one **bold**\n- two `code`\n  - nested\n1. first\n2. second\n\n| A | B |\n|---|---|\n| 1 | 2 |");
  assert.ok(html.includes("<h3>Title</h3>"));
  assert.ok(html.includes("<strong>bold</strong>"));
  assert.ok(html.includes("<code>code</code>"));
  assert.ok((html.match(/<ul>/g) || []).length === 2);
  assert.ok(html.includes("<ol>"));
  assert.ok(html.includes("<th>A</th>") && html.includes("<td>2</td>"));
});

test("snake_case identifiers are not turned into italics", () => {
  const html = renderMarkdown("call get_user_name and my_var_here");
  assert.ok(!html.includes("<em>"));
});

test("speech text drops code", () => {
  assert.equal(toSpeech("Hi **there**\n```js\nsecret()\n```"), "Hi there (code block omitted)");
});
