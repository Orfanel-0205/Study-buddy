"""Search by meaning ("semantic search") with a local embedding model.

An embedding model turns a piece of text into a list of numbers so that texts with
similar meaning get similar numbers. Jarvis uses it next to keyword search, so a
question like "where do we hide passwords?" can find code that says "redact secrets".

It runs in your local model server (Ollama: `ollama pull nomic-embed-text`, ~270 MB).
Nothing leaves your computer. Results are cached in jarvis.db so unchanged files are
not processed again.
"""

from __future__ import annotations

import array
import hashlib
import math
import threading

import httpx

from ..config import Settings, ensure_local_endpoint
from ..db import Database

BATCH = 32
MAX_CHARS = 4000


class EmbeddingCancelled(Exception):
    pass


def _normalized(values) -> array.array:
    vec = array.array("f", values)
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return array.array("f", (x / norm for x in vec))


try:
    from math import sumprod as _dot  # Python 3.12+: fast, written in C
except ImportError:  # pragma: no cover - older Pythons
    import operator

    def _dot(a, b):
        return sum(map(operator.mul, a, b))


def similarity(a: array.array, b: array.array) -> float:
    """Cosine similarity of two normalized vectors."""
    return _dot(a, b)


class Embedder:
    def __init__(self, settings: Settings, db: Database | None = None, transport: httpx.BaseTransport | None = None):
        ensure_local_endpoint(settings)  # same privacy rule as the chat model
        self.provider = settings.provider
        self.endpoint = settings.endpoint.rstrip("/")
        self.model = settings.embedding_model
        self.db = db
        self._client = httpx.Client(timeout=httpx.Timeout(120, connect=5), trust_env=False, transport=transport)
        self._lock = threading.Lock()

    def close(self) -> None:
        self._client.close()

    def available(self) -> bool:
        try:
            if self.provider == "ollama":
                names = [m.get("name", "") for m in self._client.get(self.endpoint + "/api/tags", timeout=5)
                         .json().get("models", [])]
                return self.model in names or f"{self.model}:latest" in names
            data = self._client.get(self.endpoint + "/models", timeout=5).json().get("data", [])
            return any(m.get("id") == self.model for m in data)
        except (httpx.HTTPError, ValueError):
            return False

    def _prefix(self, kind: str) -> str:
        # nomic-embed models were trained with these task prefixes.
        if self.model.startswith("nomic-embed"):
            return "search_query: " if kind == "query" else "search_document: "
        return ""

    def _request(self, texts: list[str]) -> list[list[float]]:
        if self.provider == "ollama":
            r = self._client.post(self.endpoint + "/api/embed", json={"model": self.model, "input": texts, "truncate": True})
            r.raise_for_status()
            return r.json()["embeddings"]
        r = self._client.post(self.endpoint + "/embeddings", json={"model": self.model, "input": texts})
        r.raise_for_status()
        return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]

    def embed(self, texts: list[str], kind: str = "document", cancel: threading.Event | None = None,
              progress=None) -> list[array.array]:
        prepared = [self._prefix(kind) + t[:MAX_CHARS] for t in texts]
        keys = [hashlib.sha1(f"{self.model}\0{t}".encode("utf-8", "replace")).hexdigest() for t in prepared]
        use_cache = self.db is not None and kind == "document"
        found = self._cache_get(keys) if use_cache else {}
        result: list[array.array | None] = [found.get(k) for k in keys]
        todo = [i for i, v in enumerate(result) if v is None]
        done = len(texts) - len(todo)
        for start in range(0, len(todo), BATCH):
            if cancel is not None and cancel.is_set():
                raise EmbeddingCancelled()
            batch = todo[start:start + BATCH]
            vectors = self._request([prepared[i] for i in batch])
            fresh = {}
            for i, values in zip(batch, vectors):
                result[i] = _normalized(values)
                fresh[keys[i]] = result[i]
            if use_cache:
                self._cache_put(fresh)
            done += len(batch)
            if progress:
                progress(done)
        return result  # type: ignore[return-value]

    def _cache_get(self, keys: list[str]) -> dict[str, array.array]:
        out: dict[str, array.array] = {}
        with self.db.connect() as conn:
            for start in range(0, len(keys), 500):
                part = keys[start:start + 500]
                rows = conn.execute(f"SELECT key, vec FROM embeddings WHERE key IN ({','.join('?' * len(part))})",
                                    part).fetchall()
                for row in rows:
                    vec = array.array("f")
                    vec.frombytes(row["vec"])
                    out[row["key"]] = vec
        return out

    def _cache_put(self, items: dict[str, array.array]) -> None:
        with self._lock, self.db.connect() as conn:
            conn.executemany("INSERT OR REPLACE INTO embeddings (key, vec) VALUES (?, ?)",
                             [(k, v.tobytes()) for k, v in items.items()])
