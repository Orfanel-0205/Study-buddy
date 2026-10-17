"""Measure how well local models (and Jarvis's settings) answer, with automatic grading.

    python evals/run_eval.py                                  # installed default models, everything
    python evals/run_eval.py --models gemma3:4b qwen2.5-coder:7b
    python evals/run_eval.py --only retrieval                 # search quality only (fast, no chat model)
    python evals/run_eval.py --repeats 2                      # ask each question twice (less luck)

Questions go through the same prompts and project context Jarvis uses. Code answers are
run against hidden tests in a separate Python process with a time limit (they are
written by a local model, so only run evals on code you're comfortable executing).
Results are printed and saved to evals/results/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

from cases import CODE, GENERAL, PROJECT, RETRIEVAL  # noqa: E402

from jarvis.assistant.context import build_project_context  # noqa: E402
from jarvis.assistant.prompts import system_prompt  # noqa: E402
from jarvis.config import Settings  # noqa: E402
from jarvis.llm import ChatOptions, OllamaProvider  # noqa: E402
from jarvis.project.embeddings import Embedder  # noqa: E402
from jarvis.project.index import ProjectIndex  # noqa: E402
from jarvis.project.workspace import Workspace  # noqa: E402

FIXTURE = ROOT / "evals" / "fixtures" / "calculator"
DEFAULT_MODELS = ["qwen2.5-coder:7b", "gemma3:4b", "llama3.2:latest", "qwen3:1.7b"]
LETTERS = "ABCD"


# ------------------------------------------------------------------ grading
def mc_prompt(case: dict) -> str:
    opts = "\n".join(f"{LETTERS[i]}) {o}" for i, o in enumerate(case["options"]))
    return (f"{case['q']}\n\nOptions:\n{opts}\n\n"
            "Reply with the letter of the correct option first (for example: B), then one short sentence why.")


def grade_choice(reply: str, case: dict) -> str | None:
    text = re.sub(r"[*_`#]", "", reply).strip()
    m = re.search(r"(?i)\banswer\s*(?:is)?\s*[:\-]?\s*\(?([A-D])\b", text)
    if m:
        return m.group(1).upper()
    first = text.splitlines()[0].strip() if text else ""
    # A lone letter, "C)", "C." or "C - ...", but not the word "A" starting a sentence.
    m = re.match(r"^\(?([A-D])(?:\)|\.|:|,|\s*$|\s+[-–—])", first)
    if m:
        return m.group(1)
    m = re.search(r"\b([A-D])\)", text)
    if m:
        return m.group(1)
    mentioned = [LETTERS[i] for i, o in enumerate(case["options"]) if o.lower() in text.lower()]
    return mentioned[0] if len(mentioned) == 1 else None


def extract_code(reply: str, fn: str | None = None) -> str:
    """The code block that defines `fn` (answers often add a separate usage/test block)."""
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", reply, re.S)
    if not blocks:
        return reply
    if fn:
        defining = [b for b in blocks if re.search(rf"^\s*def {re.escape(fn)}\s*\(", b, re.M)]
        if defining:
            return max(defining, key=len)
    return max(blocks, key=len)


def run_hidden_tests(code: str, tests: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "check.py"
        script.write_text(code + "\n\n" + tests + "\nprint('ALL PASSED')\n", encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, "-I", str(script)], cwd=tmp, capture_output=True, text=True,
                               timeout=10, env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})
        except subprocess.TimeoutExpired:
            return False, "timed out"
        ok = r.returncode == 0 and "ALL PASSED" in r.stdout
        return ok, (r.stderr or r.stdout)[-300:]


# ------------------------------------------------------------------ retrieval
def eval_retrieval() -> dict:
    ws = Workspace(ROOT, extra_exclude=["evals"])  # the questions themselves must not be searchable
    out = {}
    for label, embedder in [("keyword", None), ("keyword+meaning", Embedder(Settings()))]:
        if embedder is not None and not embedder.available():
            out[label] = {"skipped": "embedding model not installed"}
            continue
        index = ProjectIndex()
        index.build(ws, 4000, embedder)
        hits, misses = 0, []
        for case in RETRIEVAL:
            top = []
            for r in index.search(case["q"], k=10, per_file=1):
                if r["path"] not in top:
                    top.append(r["path"])
            if any(f in top[:3] for f in case["files"]):
                hits += 1
            else:
                misses.append({"q": case["q"], "expected": case["files"], "got": top[:3]})
        out[label] = {"hit@3": f"{hits}/{len(RETRIEVAL)}", "score": hits / len(RETRIEVAL), "misses": misses}
    return out


# ------------------------------------------------------------------ model questions
async def ask(provider, model: str, think: bool, system: str, user: str) -> tuple[str, float]:
    t0 = time.time()
    text = await provider.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                               ChatOptions(model=model, temperature=0.3, context_window=8192, think=think))
    return text, time.time() - t0


def fixture_context(question: str, evidence: str) -> str:
    ws = Workspace(FIXTURE)
    index = ProjectIndex()
    index.build(ws, 100)
    ctx, _, _ = build_project_context(ws, index, question, [], 12000, True, ws.overview())
    if evidence:
        ctx += f"\n\n{evidence}"
    return f"{ctx}\n\n---\nUsing the project context above where relevant, respond to:\n"


def real_test_output() -> str:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=FIXTURE,
                       capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    out = "\n".join((r.stdout + r.stderr).strip().splitlines()[-30:])
    return (f"## Real result of running `python -m pytest -q` in the project (just now)\n"
            f"Exit code {r.returncode}. This is actual output, not a guess; base your answer on it.\n```text\n{out}\n```")


async def eval_model(provider, model: str, think: bool, repeats: int, evidence_text: str, log) -> dict:
    sections = {"project": [], "project+evidence": [], "general": [], "code": []}
    seconds = []
    answers = []
    for _ in range(repeats):
        for variant, evidence in [("project", ""), ("project+evidence", evidence_text)]:
            sys_text = system_prompt("test", "concise", model)
            for case in PROJECT:
                reply, dt = await ask(provider, model, think, sys_text, fixture_context(case["q"], evidence) + mc_prompt(case))
                got = grade_choice(reply, case)
                sections[variant].append(got == case["answer"])
                seconds.append(dt)
                answers.append({"section": variant, "id": case["id"], "ok": got == case["answer"], "reply": reply})
                log(f"  {variant:<17} {case['id']:<16} {'ok ' if got == case['answer'] else 'BAD'} got={got} want={case['answer']} {dt:4.1f}s")
        sys_text = system_prompt("general", "concise", model)
        for case in GENERAL:
            reply, dt = await ask(provider, model, think, sys_text, mc_prompt(case))
            got = grade_choice(reply, case)
            sections["general"].append(got == case["answer"])
            seconds.append(dt)
            answers.append({"section": "general", "id": case["id"], "ok": got == case["answer"], "reply": reply})
            log(f"  {'general':<17} {case['id']:<16} {'ok ' if got == case['answer'] else 'BAD'} got={got} want={case['answer']} {dt:4.1f}s")
        sys_text = system_prompt("implement", "concise", model)
        for case in CODE:
            reply, dt = await ask(provider, model, think, sys_text,
                                  case["prompt"] + "\nReply with one ```python code block containing the function.")
            ok, detail = await asyncio.to_thread(run_hidden_tests, extract_code(reply, case.get("fn")), case["tests"])
            sections["code"].append(ok)
            seconds.append(dt)
            answers.append({"section": "code", "id": case["id"], "ok": ok, "reply": reply})
            log(f"  {'code':<17} {case['id']:<16} {'ok ' if ok else 'BAD'} {dt:4.1f}s {'' if ok else detail.strip().splitlines()[-1][:80] if detail.strip() else ''}")
    summary = {k: f"{sum(v)}/{len(v)}" for k, v in sections.items()}
    total = [x for v in sections.values() for x in v]
    summary["overall"] = f"{sum(total)}/{len(total)}"
    summary["score"] = round(sum(total) / len(total), 3)
    summary["avg_seconds"] = round(sum(seconds) / len(seconds), 1)
    summary["answers"] = answers  # saved to the results file so grading can be checked by a human
    return summary


def regrade(path: Path) -> None:
    """Grade saved answers again (for example after fixing the grader) without asking the models."""
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in PROJECT + GENERAL + CODE}
    print(f"  {'model':<26}{'project':>9}{'+evidence':>11}{'general':>9}{'code':>7}{'overall':>9}")
    for label, summary in data["models"].items():
        sections: dict[str, list[bool]] = {"project": [], "project+evidence": [], "general": [], "code": []}
        for a in summary["answers"]:
            case = cases[a["id"]]
            if a["section"] == "code":
                a["ok"] = run_hidden_tests(extract_code(a["reply"], case.get("fn")), case["tests"])[0]
            else:
                a["ok"] = grade_choice(a["reply"], case) == case["answer"]
            sections[a["section"]].append(a["ok"])
        for k, v in sections.items():
            summary[k] = f"{sum(v)}/{len(v)}"
        total = [x for v in sections.values() for x in v]
        summary["overall"] = f"{sum(total)}/{len(total)}"
        summary["score"] = round(sum(total) / len(total), 3)
        print(f"  {label:<26}{summary['project']:>9}{summary['project+evidence']:>11}{summary['general']:>9}"
              f"{summary['code']:>7}{summary['overall']:>9}")
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="*", help="models to compare (default: common installed ones)")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--only", choices=["retrieval", "models"])
    parser.add_argument("--no-think", action="store_true", help="don't add a 'thinking' run for models that support it")
    parser.add_argument("--regrade", metavar="RESULTS_JSON", help="re-grade saved answers (after fixing the grader)")
    args = parser.parse_args()
    if args.regrade:
        return regrade(Path(args.regrade))

    results: dict = {"started": time.strftime("%Y-%m-%d %H:%M:%S")}
    if args.only != "models":
        print("Search quality (does the right file appear in the top 3?)")
        results["retrieval"] = eval_retrieval()
        for label, r in results["retrieval"].items():
            print(f"  {label:<16} {r.get('hit@3', r.get('skipped'))}")
            for miss in r.get("misses", []):
                print(f"      missed: {miss['q'][:60]!r} -> {miss['got']}")
    if args.only != "retrieval":
        provider = OllamaProvider(Settings().endpoint, timeout=900)
        installed = [m.name for m in (await provider.status()).models]
        models = args.models or [m for m in DEFAULT_MODELS if m in installed]
        evidence_text = real_test_output()
        results["models"] = {}
        for model in models:
            configs = [(model, False)]
            if not args.no_think and await provider.model_supports_thinking(model):
                configs.append((model, True))
            for name, think in configs:
                label = name + (" +thinking" if think else "")
                print(f"\n{label}")
                results["models"][label] = await eval_model(provider, name, think, args.repeats, evidence_text, print)
                print("  ->", {k: v for k, v in results["models"][label].items() if k != "answers"})
        await provider.aclose()
        print("\nSummary (higher is better)")
        print(f"  {'model':<26}{'project':>9}{'+evidence':>11}{'general':>9}{'code':>7}{'overall':>9}{'sec/ans':>9}")
        for label, s in results["models"].items():
            print(f"  {label:<26}{s['project']:>9}{s['project+evidence']:>11}{s['general']:>9}{s['code']:>7}"
                  f"{s['overall']:>9}{s['avg_seconds']:>9}")
    out_dir = ROOT / "evals" / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"eval-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    asyncio.run(main())
