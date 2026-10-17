"""Built-in study guides (Markdown files in ./guides), searchable offline.

Each guide is split into sections at its `## ` and `### ` headings. Search uses the
same keyword ranking (BM25) as project search, so answers in Study / Explain / Coach
modes can quote the relevant section instead of relying on the model's memory.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..project.index import tokenize

GUIDES_DIR = Path(__file__).parent / "guides"
_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def stem(token: str) -> str:
    """Very light English stemming so "indexes", "indexing" and "index" match."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith(("ches", "shes", "sses", "xes", "zes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    return token


# Everyday words that say nothing about a topic (on top of the project search's stopwords).
FILLER = {"like", "want", "need", "get", "got", "make", "made", "use", "using", "used", "know", "good", "best", "new", "one",
          "really", "thing", "things", "way", "just", "also", "very", "much", "many", "lot", "now", "going", "gonna", "let",
          "help", "tell", "give", "some", "any", "every", "only", "still", "well", "would", "will", "can", "think"}


def terms(text: str) -> list[str]:
    return [stem(t) for t in tokenize(text) if t not in FILLER]


@dataclass
class Section:
    guide: str  # guide id
    title: str
    anchor: str
    text: str


@dataclass
class Guide:
    id: str
    title: str
    summary: str
    tags: list[str]
    order: int
    body: str
    sections: list[Section] = field(default_factory=list)

    def meta(self) -> dict:
        return {"id": self.id, "title": self.title, "summary": self.summary, "tags": self.tags,
                "sections": [{"title": s.title, "anchor": s.anchor} for s in self.sections]}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_guide(guide_id: str, raw: str) -> Guide:
    meta: dict[str, str] = {}
    m = _FRONT.match(raw)
    if m:
        for line in m.group(1).splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
        raw = raw[m.end():]
    body = raw.strip() + "\n"
    guide = Guide(id=guide_id, title=meta.get("title", guide_id), summary=meta.get("summary", ""),
                  tags=[t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
                  order=int(meta.get("order", "99")), body=body)
    # Sections: the intro, then one per "## " and "### " heading ("Topic › Subtopic"), so search can return
    # a focused piece. Headings inside code blocks (e.g. "## comment" lines) are ignored. A very short piece
    # (like a one-line intro under a "## " heading) is merged into the next one.
    h2 = ""
    current_title = guide.title
    current: list[str] = []
    carry: list[str] = []
    in_fence = False

    def flush():
        nonlocal carry
        lines = carry + current
        text = "\n".join(lines).strip()
        if not text:
            return
        if len(text) < 200:
            carry = lines  # too small to stand alone: becomes the start of the next section
            return
        carry = []
        guide.sections.append(Section(guide_id, current_title, slug(current_title), text))

    for line in body.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and (line.startswith("## ") or line.startswith("### ")):
            flush()
            if line.startswith("## "):
                h2 = line[3:].strip()
                current_title = h2
            else:
                current_title = f"{h2} › {line[4:].strip()}" if h2 else line[4:].strip()
            current = [line]
        else:
            current.append(line)
    if carry and not current:
        current = []
    flush()
    if carry:  # a short last piece: attach to the previous section
        if guide.sections:
            last = guide.sections[-1]
            last.text += "\n\n" + "\n".join(carry).strip()
        else:
            guide.sections.append(Section(guide_id, current_title, slug(current_title), "\n".join(carry).strip()))
    return guide


class GuideLibrary:
    def __init__(self, directory: Path = GUIDES_DIR):
        self.guides: dict[str, Guide] = {}
        for path in sorted(directory.glob("*.md")):
            guide = parse_guide(path.stem, path.read_text(encoding="utf-8"))
            self.guides[guide.id] = guide
        self._tfs: list[Counter] = []
        self._sections: list[Section] = []
        df: Counter = Counter()
        for guide in self.guides.values():
            title_terms = terms(guide.title + " " + " ".join(guide.tags))
            for sec in guide.sections:
                tf = Counter(terms(sec.title + "\n" + sec.text))
                for tok in title_terms + terms(sec.title):
                    tf[tok] += 2  # words in the guide/section title and tags count extra
                self._tfs.append(tf)
                self._sections.append(sec)
                df.update(tf.keys())
        self._df = df
        self._lengths = [sum(tf.values()) for tf in self._tfs]
        self._avg = (sum(self._lengths) / len(self._lengths)) if self._lengths else 1.0

    def _rank(self, query: str) -> list[tuple[float, int]]:
        """BM25, the same ranking formula as project search."""
        q = Counter(terms(query))
        n, k1, b = len(self._tfs), 1.4, 0.75
        scored = []
        for i, tf in enumerate(self._tfs):
            score = 0.0
            for term, qcount in q.items():
                f = tf.get(term)
                if f:
                    idf = math.log(1 + (n - self._df[term] + 0.5) / (self._df[term] + 0.5))
                    score += qcount * idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * self._lengths[i] / self._avg))
            if score > 0:
                scored.append((score, i))
        scored.sort(reverse=True)
        return scored

    def list(self) -> list[dict]:
        return [g.meta() for g in sorted(self.guides.values(), key=lambda g: (g.order, g.title))]

    def get(self, guide_id: str) -> dict:
        guide = self.guides.get(guide_id)
        if not guide:
            raise FileNotFoundError(f"There is no guide called '{guide_id}'.")
        return {**guide.meta(), "markdown": guide.body}

    def search(self, query: str, k: int = 5) -> list[dict]:
        ranked = self._rank(query)
        results = []
        for score, i in ranked[:k]:
            sec = self._sections[i]
            guide = self.guides[sec.guide]
            snippet = re.sub(r"\s+", " ", re.sub(r"[#*`|>_-]+", " ", sec.text)).strip()
            results.append({"guide": guide.id, "guide_title": guide.title, "section": sec.title,
                            "anchor": sec.anchor, "score": round(score, 3), "snippet": snippet[:220],
                            "text": sec.text})
        return results

    def context_for(self, query: str, budget_chars: int, max_sections: int = 2) -> tuple[str, list[dict]]:
        """Relevant guide sections for the model, and sources for the interface. Weak matches are left out
        so unrelated questions don't get padded with guide text."""
        hits = self.search(query, k=max_sections * 2)
        if not hits or hits[0]["score"] < 4.0:
            return "", []
        # Keyword overlap alone isn't enough: a section must cover a good part of the question's words,
        # otherwise a question about a startup gets notes about database pooling.
        # Only words the guides use at all count (in a long message, "smartphone" or "pocket" say nothing).
        words = set(terms(query))
        asked = {t for t in words if self._df.get(t)}
        if not words or len(asked) / len(words) < 0.4:  # mostly words no guide uses: an off-topic question
            return "", []
        # Short questions: most of their words; long ones: about a quarter; never a single shared word by chance.
        needed = max(min(2, len(asked)), min(0.4 * len(asked), max(3, 0.25 * len(asked))))
        hits = [h for h in hits if asked and len(asked & set(terms(h["section"] + " " + h["text"]))) >= needed]
        if not hits:
            return "", []
        parts, sources, used = [], [], 0
        for hit in hits:
            if len(sources) >= max_sections or hit["score"] < hits[0]["score"] * 0.45:
                break
            text = hit["text"]
            room = budget_chars - used
            if room < 400:
                break
            if len(text) > room:
                text = text[:room].rsplit("\n", 1)[0] + "\n...(section shortened)"
            parts.append(f"### From the Jarvis guide \"{hit['guide_title']}\", section \"{hit['section']}\"\n{text}\n")
            used += len(text) + 80
            sources.append({"path": f"guide:{hit['guide']}#{hit['anchor']}", "title": f"{hit['guide_title']} › {hit['section']}",
                            "start_line": 0, "end_line": 0, "kind": "guide"})
        if not parts:
            return "", []
        header = ("## Reference notes from Jarvis's built-in study guides\n"
                  "Found by keyword search, so they may be unrelated: use them only if they answer the question "
                  "(then prefer them over memory and name the guide), otherwise ignore them.\n")
        return header + "\n".join(parts), sources
