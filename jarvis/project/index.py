"""Search index over project files.

Keyword search (BM25 ranking) always works and needs no downloads. Files are split
into overlapping chunks of lines; identifiers such as `getUserName` and
`get_user_name` are also split into their words so either spelling matches.

When an embedding model is installed (see embeddings.py), each chunk also gets a
"meaning" vector, and results from both searches are merged with reciprocal rank
fusion: a chunk ranked high by either method rises to the top.
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field

from .embeddings import EmbeddingCancelled, similarity
from .workspace import Workspace

CHUNK_LINES = 60
CHUNK_STEP = 45
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "it", "for", "on", "with", "as",
    "be", "this", "that", "are", "was", "by", "at", "from", "if", "else", "then", "not",
    "do", "does", "how", "what", "where", "why", "when", "which", "who", "can", "i", "my",
    "me", "you", "your", "we", "our", "there", "here", "about", "into", "should", "would",
    "could", "please", "explain", "show", "tell", "file", "code", "project",
}


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for word in _WORD.findall(text):
        lower = word.lower()
        parts = [p.lower() for p in _CAMEL.findall(word.replace("_", " "))] if (
            "_" in word or any(c.isupper() for c in word[1:])) else []
        for tok in [lower, *parts]:
            if len(tok) > 1 and tok not in STOPWORDS:
                tokens.append(tok)
    return tokens


@dataclass
class Chunk:
    path: str
    start: int  # 1-based, inclusive
    end: int
    text: str
    tf: Counter = field(repr=False, default_factory=Counter)
    length: int = 0


@dataclass
class IndexStatus:
    state: str = "idle"  # idle | indexing | ready | cancelled | error
    files_indexed: int = 0
    chunks: int = 0
    skipped: int = 0
    seconds: float = 0.0
    error: str = ""
    limit_reached: bool = False
    semantic: str = "off"  # off | unavailable | building | ready | error
    embedded: int = 0


RRF_K = 60  # standard constant for reciprocal rank fusion


class ProjectIndex:
    def __init__(self):
        self.chunks: list[Chunk] = []
        self.df: Counter = Counter()
        self.avg_len = 1.0
        self.vectors: list | None = None  # meaning vectors, aligned with self.chunks
        self.embedder = None
        self.status = IndexStatus()
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    def cancel(self) -> None:
        self._cancel.set()

    def build(self, workspace: Workspace, max_files: int, embedder=None) -> IndexStatus:
        self._cancel.clear()
        started = time.monotonic()
        status = IndexStatus(state="indexing")
        self.status = status
        chunks: list[Chunk] = []
        df: Counter = Counter()
        try:
            for rel in workspace.iter_files(max_files + 1):
                if self._cancel.is_set():
                    status.state = "cancelled"
                    break
                if status.files_indexed >= max_files:
                    status.limit_reached = True
                    break
                try:
                    text = workspace.read_text(rel)
                except (OSError, PermissionError):
                    status.skipped += 1
                    continue
                if not text.strip():
                    continue  # e.g. an empty __init__.py would only match on its path
                file_chunks = _chunk_file(rel, text)
                for ch in file_chunks:
                    df.update(ch.tf.keys())
                chunks.extend(file_chunks)
                status.files_indexed += 1
                status.chunks = len(chunks)
        except Exception as exc:  # report, never crash the app
            status.state = "error"
            status.error = str(exc)
        if status.state == "indexing":
            status.state = "ready"
        status.seconds = round(time.monotonic() - started, 2)
        if status.state in ("ready", "cancelled"):
            with self._lock:
                self.chunks = chunks
                self.df = df
                self.avg_len = (sum(c.length for c in chunks) / len(chunks)) if chunks else 1.0
                self.vectors = None
        if status.state == "ready" and embedder is not None:
            self._embed(chunks, embedder, status)  # keyword search already works meanwhile
        return status

    def _embed(self, chunks: list[Chunk], embedder, status: IndexStatus) -> None:
        if not embedder.available():
            status.semantic = "unavailable"
            return
        status.semantic = "building"

        def progress(n: int) -> None:
            status.embedded = n

        try:
            vectors = embedder.embed([f"File: {c.path}\n{c.text}" for c in chunks], "document",
                                     cancel=self._cancel, progress=progress)
        except EmbeddingCancelled:
            status.semantic = "off"
            return
        except Exception as exc:  # the model server failed: keyword search still works
            status.semantic = "error"
            status.error = f"Search by meaning unavailable: {exc}"
            return
        with self._lock:
            if self.chunks is chunks:
                self.vectors = vectors
                self.embedder = embedder
        status.semantic = "ready"
        status.embedded = len(vectors)

    def search(self, query: str, k: int = 6, per_file: int = 2) -> list[dict]:
        with self._lock:
            chunks, df, avg_len = self.chunks, self.df, self.avg_len
            vectors, embedder = self.vectors, self.embedder
        if not chunks or not query.strip():
            return []
        keyword = self._keyword_ranking(query, chunks, df, avg_len)
        meaning: list[tuple[float, int]] = []
        if vectors is not None and embedder is not None:
            try:
                qv = embedder.embed([query], "query")[0]
                meaning = sorted(((similarity(qv, v), i) for i, v in enumerate(vectors)), reverse=True)[:50]
            except Exception:
                meaning = []  # model server unavailable right now: keywords only
        fused: dict[int, float] = {}
        for rank, (_, i) in enumerate(keyword[:50]):
            fused[i] = fused.get(i, 0.0) + 1 / (RRF_K + rank)
        for rank, (_, i) in enumerate(meaning):
            fused[i] = fused.get(i, 0.0) + 1 / (RRF_K + rank)
        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
        results, per = [], Counter()
        for i, score in ranked:
            ch = chunks[i]
            if per[ch.path] >= per_file:
                continue
            per[ch.path] += 1
            results.append({"path": ch.path, "start_line": ch.start, "end_line": ch.end,
                            "score": round(score, 4), "text": ch.text})
            if len(results) >= k:
                break
        return results

    @staticmethod
    def _keyword_ranking(query: str, chunks: list[Chunk], df: Counter, avg_len: float) -> list[tuple[float, int]]:
        terms = tokenize(query)
        if not terms:
            return []
        n = len(chunks)
        k1, b = 1.4, 0.75
        q = Counter(terms)
        scored = []
        for i, ch in enumerate(chunks):
            score = 0.0
            for term, qcount in q.items():
                tf = ch.tf.get(term)
                if not tf:
                    continue
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                score += qcount * idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * ch.length / avg_len))
            if score > 0:
                scored.append((score, i))
        scored.sort(reverse=True)
        return scored


def _chunk_file(rel: str, text: str) -> list[Chunk]:
    lines = text.splitlines()
    path_tokens = tokenize(rel.replace("/", " ").replace(".", " "))
    chunks = []
    start = 0
    while True:
        window = lines[start:start + CHUNK_LINES]
        body = "\n".join(window)
        tf = Counter(tokenize(body))
        # The file path counts too, so "where is the login page" finds login.html.
        for tok in path_tokens:
            tf[tok] += 3
        chunks.append(Chunk(rel, start + 1, start + len(window), body, tf, sum(tf.values())))
        if start + CHUNK_LINES >= len(lines):
            break
        start += CHUNK_STEP
    return chunks
