"""Auto mode: pick the best mode for a message from its wording (no model needed, instant).

Each mode has trigger phrases with weights; the highest score wins, and "general" is the
fallback. The chosen mode is shown to the user ("Auto: answering as ...") so it's never hidden.
"""

from __future__ import annotations

import re

# (mode, weight, patterns). Patterns are matched as whole words/phrases, case-insensitive.
RULES: list[tuple[str, float, list[str]]] = [
    ("business", 3.0, [r"start ?up", r"business", r"customers?", r"clients?", r"sell(ing)?", r"sales", r"revenue", r"profit",
                       r"pric(e|es|ing)", r"market(ing)?", r"pitch(ing)? (to|for) (restaurants?|clients?|customers?|owners?)",
                       r"cold ?call(s|ing)?", r"leads?", r"(what|how) (should|do) (i|we) say", r"script(s)? (for|to) (call|sell|offer)",
                       r"budget", r"\$ ?\d+", r"₱ ?\d+", r"\d+ ?(pesos|php|dollars|usd)", r"how much (will|would|does) (it|this) cost",
                       r"restaurants?", r"offer (them|a|an)", r"freelanc(e|ing|er)", r"side hustle", r"monetiz(e|ation)",
                       r"business (idea|plan|model)", r"validate (my|the|an|this) idea", r"go to market"]),
    ("hackathon", 4.0, [r"hackathons?", r"hack ?day", r"demo day", r"judg(es|ing) criteria", r"pitch deck"]),
    ("stack", 3.0, [r"tech ?stack", r"(which|what) (framework|language|database|stack|technolog(y|ies)|tools?) (should|to|do)",
                    r"file structure", r"folder structure", r"project structure", r"third[- ]party api", r"apis? (should|to) use",
                    r"how (do|should) (i|we) build", r"architecture for", r"(build|make|create) (an?|the|my) (app|website|system|platform|cms|chatbot)",
                    r"cms", r"admin (panel|dashboard)", r"hosting", r"deploy(ment)? (on|to)"]),
    ("test", 3.0, [r"[a-z]*error", r"traceback", r"[a-z]*exception", r"cannot read propert(y|ies)", r"stack ?trace", r"bug", r"doesn'?t work", r"not working", r"fail(s|ed|ing)?",
                   r"undefined is not", r"null pointer", r"segfault", r"crash(es|ed)?", r"debug", r"why (does|is) (my|this) (code|function)"]),
    ("implement", 2.0, [r"write (a|an|the|me) (function|class|script|program|code|endpoint|query)", r"implement", r"code (for|that|to)",
                        r"refactor", r"convert (this|my) code"]),
    ("requirements", 2.5, [r"requirements?", r"user stor(y|ies)", r"acceptance criteria", r"use cases?", r"srs"]),
    ("rules", 3.0, [r"business rules?", r"decision table", r"polic(y|ies)", r"eligib(le|ility)", r"approval rules?"]),
    ("design", 2.0, [r"system design", r"database (schema|design)", r"erd", r"data model", r"api design", r"microservices?",
                     r"scal(e|ing|ability)"]),
    ("release", 2.0, [r"release notes?", r"changelog", r"readme", r"migration", r"rollback", r"security review"]),
    ("coach", 2.5, [r"stress(ed)?", r"overwhelm(ed|ing)?", r"burn(ed)? ?out", r"tired", r"anxious|anxiety", r"motivat(e|ion)",
                    r"career", r"internship", r"interview", r"(apply|applying) for (a )?(job|internship)s?", r"resume|cv",
                    r"work ?load", r"procrastinat(e|ing|ion)", r"time management", r"what should i focus on"]),
    ("study", 2.5, [r"quiz me", r"flashcards?", r"exam", r"reviewer", r"study (plan|guide|tips?)", r"help me (study|memoriz)", r"devnet"]),
    ("explain", 2.0, [r"explain", r"what (is|are|does)", r"difference between", r"how does .* work", r"define", r"meaning of", r"concept"]),
    ("tasks", 2.0, [r"plan my (day|week)", r"break (this|it) (down|into)", r"to-?do list", r"prioriti[sz]e"]),
]

_COMPILED = [(mode, weight, [re.compile(r"(?<![a-z])(?:" + p + r")(?![a-z])", re.I) for p in pats]) for mode, weight, pats in RULES]


def route(message: str) -> tuple[str, dict[str, float]]:
    """Return (mode, scores). Scores are kept for tests and debugging."""
    text = message[:4000]
    scores: dict[str, float] = {}
    for mode, weight, patterns in _COMPILED:
        hits = sum(1 for p in patterns if p.search(text))
        if hits:
            scores[mode] = scores.get(mode, 0.0) + weight * (1 + 0.35 * (hits - 1))
    if not scores:
        return "general", scores
    best = max(scores.items(), key=lambda kv: kv[1])
    # A traceback or error message is about debugging, even if it mentions a business or an app.
    if scores.get("test", 0) >= 3 and re.search(r"traceback|exception|error|stack ?trace", text, re.I):
        return "test", scores
    return (best[0] if best[1] >= 2.0 else "general"), scores
