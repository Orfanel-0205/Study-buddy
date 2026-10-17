from __future__ import annotations

import sys
from pathlib import Path
from typing import AsyncIterator

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.llm.base import ChatChunk, ChatOptions, LLMProvider, ModelInfo, ProviderStatus  # noqa: E402


class FakeProvider(LLMProvider):
    """A stand-in model server so tests never need Ollama."""

    name = "fake"

    def __init__(self, reply: str = "Hello from the fake model.", models=("fake-model:1b",),
                 reachable: bool = True, json_reply: str | None = None, delay: float = 0.0):
        self.reply = reply
        self.models = list(models)
        self.reachable = reachable
        self.json_reply = json_reply
        self.delay = delay
        self.calls: list[tuple[list[dict], ChatOptions]] = []

    async def status(self) -> ProviderStatus:
        if not self.reachable:
            return ProviderStatus(reachable=False, error="Could not connect (fake).")
        return ProviderStatus(reachable=True, version="test", models=[ModelInfo(name=m) for m in self.models])

    async def chat_stream(self, messages, options) -> AsyncIterator[ChatChunk]:
        import asyncio
        self.calls.append((messages, options))
        text = self.json_reply if (options.json_schema is not None and self.json_reply is not None) else self.reply
        for word in text.split(" "):
            if self.delay:
                await asyncio.sleep(self.delay)
            yield ChatChunk("content", word + " ")
        yield ChatChunk("done", stats={"seconds": 0.01})


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "jarvis-data"
    (d / "backups").mkdir(parents=True)
    (d / "logs").mkdir()
    return d


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "sample-project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError('b must not be zero')\n    return a / b\n",
        encoding="utf-8")
    (root / "tests" / "test_calculator.py").write_text(
        "from src.calculator import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8")
    (root / "README.md").write_text("# Sample\nA tiny calculator used in tests.\n", encoding="utf-8")
    (root / ".env").write_text("API_KEY=super-secret-value\n", encoding="utf-8")
    (root / "id_rsa").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----\n", encoding="utf-8")
    (root / "config.py").write_text('DATABASE_URL = "postgres://admin:hunter2pass@localhost/db"\npassword = "letmein123"\n', encoding="utf-8")
    (root / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    return root
