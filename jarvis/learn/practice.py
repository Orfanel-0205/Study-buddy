"""Runs your practice code against an exercise's tests, on this device.

Your code and the tests are written to a temporary folder and run with the language's own
program (python, node, php) with a time limit; the folder is deleted afterwards. This is the
same as running your own script yourself, so it only ever happens when you press "Check".
Results and your latest code are saved so you can continue later.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from ..db import Database, now_iso
from .exercises import EXERCISES, by_id

RESULT_PREFIX = "@@JARVIS "
TIMEOUT_SECONDS = 15
MAX_CODE_CHARS = 50_000
MAX_OUTPUT_CHARS = 8_000

LANGUAGES = {
    "python": {"label": "Python", "solution": "solution.py", "test": "test_runner.py"},
    "javascript": {"label": "JavaScript", "solution": "solution.mjs", "test": "test_runner.mjs"},
    "typescript": {"label": "TypeScript", "solution": "solution.mts", "test": "test_runner.mts"},
    "php": {"label": "PHP", "solution": "solution.php", "test": "test_runner.php"},
}

PY_HARNESS = r'''import importlib.util, json, sys, traceback
def _report(name, ok, detail=None):
    print("@@JARVIS " + json.dumps({"name": name, "ok": ok, "detail": detail}), flush=True)
spec = importlib.util.spec_from_file_location("solution", "solution.py")
solution = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(solution)
except BaseException as exc:
    _report("Your code loads", False, "".join(traceback.format_exception_only(type(exc), exc)).strip())
    sys.exit(0)
def eq(actual, expected):
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")
def raises(exc_type, fn, *args):
    try:
        fn(*args)
    except exc_type:
        return
    except Exception as exc:
        raise AssertionError(f"expected {exc_type.__name__}, got {type(exc).__name__}: {exc}")
    raise AssertionError(f"expected {exc_type.__name__} to be raised, but nothing was raised")
def check(name, fn):
    try:
        fn()
        _report(name, True)
    except AssertionError as exc:
        _report(name, False, str(exc) or "assertion failed")
    except NotImplementedError as exc:
        _report(name, False, f"NotImplementedError: {exc}")
    except Exception as exc:
        _report(name, False, f"{type(exc).__name__}: {exc}")
'''

JS_HARNESS = r'''const report = (name, ok, detail) => console.log("@@JARVIS " + JSON.stringify({ name, ok, detail: detail ?? null }));
function canon(v) {
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === "object" && !(v instanceof Date)) return Object.fromEntries(Object.keys(v).sort().map((k) => [k, canon(v[k])]));
  return v;
}
function show(v) { return v === undefined ? "undefined" : JSON.stringify(v); }
function eq(actual, expected) {
  if (JSON.stringify(canon(actual)) !== JSON.stringify(canon(expected)) || (actual === undefined) !== (expected === undefined)) {
    throw new Error(`expected ${show(expected)}, got ${show(actual)}`);
  }
}
async function check(name, fn) {
  try { await fn(); report(name, true); }
  catch (err) { report(name, false, (err && err.message) || String(err)); }
}
let solution;
try { solution = await import("./SOLUTION_FILE"); }
catch (err) { report("Your code loads", false, String((err && err.stack) || err).split("\n").filter((l) => !l.includes("node:internal")).slice(0, 6).join("\n")); process.exit(0); }
'''

PHP_HARNESS = r'''<?php
function jarvis_report(string $name, bool $ok, ?string $detail = null): void {
    echo "@@JARVIS " . json_encode(['name' => $name, 'ok' => $ok, 'detail' => $detail]) . "\n";
}
set_error_handler(function ($no, $str, $file, $line) { throw new ErrorException($str, 0, $no, $file, $line); });
try { require __DIR__ . '/solution.php'; }
catch (Throwable $e) { jarvis_report('Your code loads', false, get_class($e) . ': ' . $e->getMessage() . ' (line ' . $e->getLine() . ')'); exit(0); }
function jarvis_canon($v) {
    if (!is_array($v)) return $v;
    $isList = $v === [] || array_keys($v) === range(0, count($v) - 1);
    if (!$isList) ksort($v);
    return array_map('jarvis_canon', $v);
}
function eq($actual, $expected): void {
    if (jarvis_canon($actual) !== jarvis_canon($expected)) {
        throw new Exception('expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}
function throws(string $class, callable $fn): void {
    try { $fn(); } catch (Throwable $e) {
        if ($e instanceof $class) return;
        throw new Exception("expected $class, got " . get_class($e) . ': ' . $e->getMessage());
    }
    throw new Exception("expected $class to be thrown, but nothing was thrown");
}
function check(string $name, callable $fn): void {
    try { $fn(); jarvis_report($name, true); }
    catch (Throwable $e) { jarvis_report($name, false, get_class($e) === 'Exception' ? $e->getMessage() : get_class($e) . ': ' . $e->getMessage()); }
}
'''


def _python_cmd() -> list[str] | None:
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":  # Jarvis started without a window: use the console twin
        twin = exe.with_name("python.exe")
        if twin.exists():
            exe = twin
    return [str(exe), "-I"] if exe.exists() else None


def _version(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, **_hidden_window())
        return (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr).strip() else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _hidden_window() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


class Runtimes:
    """Finds the programs that run each language (checked once, then remembered)."""

    def __init__(self):
        self._cache: dict | None = None
        self._lock = threading.Lock()

    def refresh(self) -> dict:
        with self._lock:
            self._cache = None
        return self.get()

    def get(self) -> dict:
        with self._lock:
            if self._cache is not None:
                return self._cache
            found: dict[str, dict] = {}
            py = _python_cmd()
            found["python"] = {"available": bool(py), "cmd": py or [], "version": sys.version.split()[0] if py else "",
                               "install": ""}
            node = shutil.which("node")
            node_version = _version([node, "--version"]) if node else ""
            found["javascript"] = {"available": bool(node_version), "cmd": [node] if node else [], "version": node_version,
                                   "install": "Install Node.js LTS from nodejs.org (on the phone: pkg install nodejs-lts)."}
            ts_flags = _ts_flags(node_version)
            found["typescript"] = {
                "available": ts_flags is not None, "cmd": ([node, *ts_flags] if node and ts_flags is not None else []),
                "version": f"{node_version} (type stripping)" if ts_flags is not None else node_version,
                "install": "Needs Node.js 22.6 or newer, which runs TypeScript by removing the types."}
            php = shutil.which("php")
            php_version = _version([php, "-r", "echo PHP_VERSION;"]) if php else ""
            found["php"] = {"available": bool(php_version), "cmd": [php, "-d", "display_errors=stderr"] if php else [],
                            "version": php_version,
                            "install": "Install PHP 8 (Windows: Laragon or windows.php.net; on the phone: pkg install php) and add it to PATH."}
            self._cache = found
            return found

    def summary(self) -> dict:
        return {lang: {"available": info["available"], "version": info["version"], "install": info["install"],
                       "label": LANGUAGES[lang]["label"]} for lang, info in self.get().items()}


def _ts_flags(node_version: str) -> list[str] | None:
    """Node 23.6+ (and 22.18+) strip TypeScript types by default; 22.6+ needs a flag; older can't."""
    m = re.match(r"v(\d+)\.(\d+)", node_version or "")
    if not m:
        return None
    major, minor = int(m.group(1)), int(m.group(2))
    if major > 23 or (major == 23 and minor >= 6) or (major == 22 and minor >= 18):
        return ["--disable-warning=ExperimentalWarning"]
    if major == 23 or (major == 22 and minor >= 6):
        return ["--experimental-strip-types", "--disable-warning=ExperimentalWarning"]
    return None


def build_files(exercise: dict, code: str) -> dict[str, str]:
    lang = LANGUAGES[exercise["language"]]
    if exercise["language"] == "python":
        test = PY_HARNESS + exercise["tests"]
    elif exercise["language"] in ("javascript", "typescript"):
        test = JS_HARNESS.replace("SOLUTION_FILE", lang["solution"]) + exercise["tests"]
    else:
        test = PHP_HARNESS + exercise["tests"]
    return {lang["solution"]: code, lang["test"]: test}


def parse_results(stdout: str) -> tuple[list[dict], str]:
    results, other = [], []
    for line in stdout.splitlines():
        if line.startswith(RESULT_PREFIX):
            try:
                item = json.loads(line[len(RESULT_PREFIX):])
                results.append({"name": str(item.get("name", "")), "ok": bool(item.get("ok")),
                                "detail": (str(item["detail"])[:1500] if item.get("detail") else None)})
                continue
            except (ValueError, AttributeError):
                pass
        other.append(line)
    return results, "\n".join(other).strip()


def run_code(exercise: dict, code: str, runtimes: Runtimes, timeout: int = TIMEOUT_SECONDS) -> dict:
    info = runtimes.get()[exercise["language"]]
    label = LANGUAGES[exercise["language"]]["label"]
    if not info["available"]:
        return {"ok": False, "passed": 0, "total": 0, "results": [], "output": "", "errors": "",
                "timed_out": False, "seconds": 0.0, "runtime": "", "unavailable": True,
                "problem": f"{label} isn't available on this device. {info['install']}"}
    code = code[:MAX_CODE_CHARS]
    files = build_files(exercise, code)
    test_file = LANGUAGES[exercise["language"]]["test"]
    env = {k: v for k, v in os.environ.items()
           if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG",
                            "PREFIX", "LD_LIBRARY_PATH", "LD_PRELOAD", "TMPDIR", "ANDROID_ROOT", "ANDROID_DATA"}}
    env["PYTHONIOENCODING"] = "utf-8"
    env["NODE_NO_WARNINGS"] = "1"
    started = time.monotonic()
    timed_out = False
    with tempfile.TemporaryDirectory(prefix="jarvis-practice-") as tmp:
        for name, text in files.items():
            Path(tmp, name).write_text(text, encoding="utf-8")
        try:
            proc = subprocess.run([*info["cmd"], test_file], cwd=tmp, env=env, capture_output=True, timeout=timeout,
                                  stdin=subprocess.DEVNULL, **_hidden_window())
            stdout = proc.stdout.decode("utf-8", "replace")
            stderr = proc.stderr.decode("utf-8", "replace")
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = (exc.stdout or b"").decode("utf-8", "replace")
            stderr = (exc.stderr or b"").decode("utf-8", "replace")
    seconds = round(time.monotonic() - started, 2)
    results, output = parse_results(stdout)
    for r in results:
        if r["detail"]:
            r["detail"] = _clean(r["detail"], tmp)
    if (exercise["language"] == "typescript" and results and not results[0]["ok"]
            and results[0]["name"] == "Your code loads"):
        results[0]["detail"] += ("\n\nNote: Node runs TypeScript by removing the types, so features that need a compiler "
                                 "(enum, namespace, constructor parameter properties) aren't supported here. "
                                 "Use a union type or a plain object instead.")
    expected = _count_checks(exercise)
    passed = sum(1 for r in results if r["ok"])
    total = max(expected, len(results))
    problem = ""
    if timed_out:
        problem = f"Your code took longer than {timeout} seconds and was stopped. Is there an endless loop?"
    elif not results:
        problem = "The tests didn't run. Read the error output below."
    return {"ok": passed == total and total > 0 and not timed_out, "passed": passed, "total": total,
            "results": results, "output": output[-MAX_OUTPUT_CHARS:], "errors": _clean(stderr, tmp)[-MAX_OUTPUT_CHARS:],
            "timed_out": timed_out, "seconds": seconds, "runtime": f"{label} {info['version']}".strip(),
            "problem": problem}


def _count_checks(exercise: dict) -> int:
    return len(re.findall(r"^\s*(?:await\s+)?check\(", exercise["tests"], re.M))


def _clean(text: str, tmp: str) -> str:
    """Hide the temporary folder's path in error messages, so they point at solution.* clearly."""
    text = text.replace(tmp + os.sep, "").replace(tmp.replace("\\", "/") + "/", "")
    text = re.sub(r"file:///?\S*?[/\\](solution\.\w+|test_runner\.\w+)", r"\1", text)
    text = re.sub(r"[A-Za-z]:\\\S*?\\jarvis-practice-\w+\\|/\S*?/jarvis-practice-\w+/", "", text)
    return text.strip()


class PracticeStore:
    def __init__(self, db: Database):
        self.db = db

    def all(self) -> dict[str, dict]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM practice").fetchall()
        return {r["exercise_id"]: dict(r) for r in rows}

    def get(self, exercise_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM practice WHERE exercise_id = ?", (exercise_id,)).fetchone()
        return dict(row) if row else None

    def save_code(self, exercise_id: str, code: str) -> None:
        now = now_iso()
        with self.db.connect() as conn:
            conn.execute("INSERT INTO practice (exercise_id, code, updated_at) VALUES (?, ?, ?) "
                         "ON CONFLICT(exercise_id) DO UPDATE SET code = excluded.code, updated_at = excluded.updated_at",
                         (exercise_id, code[:MAX_CODE_CHARS], now))

    def record(self, exercise_id: str, code: str, result: dict) -> dict:
        self.save_code(exercise_id, code)
        now = now_iso()
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE practice SET attempts = attempts + 1, best = MAX(best, ?), total = ?, "
                "solved_at = CASE WHEN ? AND solved_at IS NULL THEN ? ELSE solved_at END, updated_at = ? "
                "WHERE exercise_id = ?",
                (result["passed"], result["total"], 1 if result["ok"] else 0, now, now, exercise_id))
        return self.get(exercise_id) or {}


def exercise_list(store: PracticeStore, runtimes: Runtimes) -> dict:
    progress = store.all()
    langs = runtimes.summary()
    items = []
    for ex in EXERCISES:
        p = progress.get(ex["id"]) or {}
        items.append({"id": ex["id"], "title": ex["title"], "language": ex["language"], "topic": ex["topic"],
                      "level": ex["level"], "guide": ex.get("guide", ""), "attempts": p.get("attempts", 0),
                      "solved": bool(p.get("solved_at")), "best": p.get("best", 0), "total": p.get("total", 0)})
    return {"exercises": items, "runtimes": langs}


def reflow(markdown: str) -> str:
    """Join lines that were only wrapped in the source, so paragraphs flow on any screen width.
    Lists, code blocks and blank-line paragraph breaks are kept."""
    blocks = re.split(r"\n\s*\n", markdown.strip())
    out = []
    for block in blocks:
        lines = block.splitlines()
        if "```" in block or any(re.match(r"\s*([-*]|\d+\.)\s", line) for line in lines):
            out.append(block)
        else:
            out.append(" ".join(line.strip() for line in lines))
    return "\n\n".join(out)


def exercise_detail(exercise_id: str, store: PracticeStore) -> dict:
    ex = by_id(exercise_id)
    p = store.get(exercise_id) or {}
    return {"id": ex["id"], "title": ex["title"], "language": ex["language"], "topic": ex["topic"], "level": ex["level"],
            "guide": ex.get("guide", ""), "task": reflow(ex["task"]), "starter": ex["starter"], "hints": ex.get("hints", []),
            "code": p.get("code") or ex["starter"], "attempts": p.get("attempts", 0), "solved": bool(p.get("solved_at")),
            "checks": _count_checks(ex)}
