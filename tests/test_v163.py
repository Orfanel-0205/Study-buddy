"""v1.6.3: faster answers on slow devices (a short prompt), thinking that can't eat the answer, long code
gets room, and Continue for an answer cut at the length limit."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from jarvis.assistant.prompts import BASE_PROMPT, LEAN_BASE_PROMPT
from jarvis.assistant.service import CONTINUE_PROMPT, LENGTH_NOTE, THINK_BUDGET_TOKENS, THINK_NOTE, WRITES_CODE
from jarvis.config import ConfigStore
from jarvis.llm.base import ChatChunk, ChatOptions
from jarvis.llm.ollama import OllamaProvider
from tests.conftest import FakeProvider
from tests.test_v16 import H, app_for


def chat(c, **body) -> list[dict]:
    lines = c.post("/api/chat", headers=H, json=body).text.splitlines()
    return [json.loads(x) for x in lines if x.strip()]


def said(events) -> str:
    return "".join(e["text"] for e in events if e["type"] == "content")


class Thinker(FakeProvider):
    """Thinks forever when allowed to think; answers when not."""

    def __init__(self, **kw):
        super().__init__(**kw)

    async def chat_stream(self, messages, options):
        self.calls.append((messages, options))
        if options.think:
            for _ in range(THINK_BUDGET_TOKENS * 3):
                yield ChatChunk("thinking", "hmm ")
            yield ChatChunk("done", stats={"done_reason": "length"})
            return
        yield ChatChunk("content", "The answer.")
        yield ChatChunk("done", stats={})


class CutOff(FakeProvider):
    """The first answer reaches the length limit; later ones finish."""

    async def chat_stream(self, messages, options):
        self.calls.append((messages, options))
        if len(self.calls) == 1:
            yield ChatChunk("content", "def todo():\n" + "    step()\n" * 400)
            yield ChatChunk("done", stats={"done_reason": "length"})
        else:
            yield ChatChunk("content", "    finish()\n```")
            yield ChatChunk("done", stats={})


def test_the_phone_sends_a_short_prompt(data_dir):
    ConfigStore(data_dir).update({"lean_prompt": True, "context_window": 4096, "max_answer_tokens": 1024})
    provider = FakeProvider(reply="Fine. " * 300)  # long earlier answers
    with TestClient(app_for(data_dir, provider)) as c:
        conv = None
        for q in ("What is a list?", "What is a tuple?", "What is a set?"):
            ev = chat(c, message=q, mode="explain", conversation_id=conv, use_guides=True)
            conv = ev[0]["conversation_id"]
        chat(c, message="How do I read a JSON file in Python?", mode="explain", conversation_id=conv, use_guides=True)
    messages, options = provider.calls[-1]
    assert messages[0]["content"].startswith(LEAN_BASE_PROMPT.split("{model}")[0])
    total = sum(len(m["content"]) for m in messages)
    assert total < 4500, total  # was up to ~8,300 characters on the phone
    history = messages[1:-1]
    assert history and history[0]["role"] == "user" and history[-1]["role"] == "assistant"
    assert all(len(m["content"]) <= 760 for m in history)  # each earlier message shortened


def test_the_laptop_keeps_the_full_prompt(data_dir):
    provider = FakeProvider(reply="Fine.")
    with TestClient(app_for(data_dir, provider)) as c:
        chat(c, message="What is a list?", mode="explain")
    assert provider.calls[0][0][0]["content"].startswith(BASE_PROMPT.split("{model}")[0])


def test_thinking_that_runs_too_long_is_stopped_and_answered_directly(data_dir):
    ConfigStore(data_dir).update({"think": True})
    provider = Thinker()
    with TestClient(app_for(data_dir, provider)) as c:
        events = chat(c, message="Why is the sky blue?", mode="explain")
    assert [o.think for _, o in provider.calls] == [True, False]
    assert provider.calls[0][1].max_tokens == 2048 + THINK_BUDGET_TOKENS  # thinking has its own room
    assert any(e["type"] == "status" and e["text"] == THINK_NOTE for e in events)
    thinking = sum(1 for e in events if e["type"] == "thinking")
    assert THINK_BUDGET_TOKENS < thinking <= THINK_BUDGET_TOKENS + 1  # stopped right at the budget
    assert said(events) == "The answer." and events[-1]["type"] == "done"


def test_asking_for_code_skips_thinking_and_gets_twice_the_room(data_dir):
    ConfigStore(data_dir).update({"think": True})
    provider = FakeProvider(reply="```python\nprint(1)\n```")
    with TestClient(app_for(data_dir, provider)) as c:
        chat(c, message="Write a complete Python command-line to-do app with tests", mode="general")
        chat(c, message="What is recursion?", mode="general")
    (_, code), (_, other) = provider.calls
    assert (code.think, code.max_tokens) == (False, 4096)
    assert (other.think, other.max_tokens) == (True, 2048 + THINK_BUDGET_TOKENS)


def test_code_requests_are_recognised():
    for q in ("Write a complete Python command-line to-do app", "Can you create a login page in PHP?",
              "make a function that sorts a list", "build me a REST API with Flask",
              "Pythonでスクレイピングのコードを書いて"):
        assert WRITES_CODE.search(q), q
    for q in ("What is a list comprehension?", "Explain how a function works", "Why does my test fail?"):
        assert not WRITES_CODE.search(q), q


def test_continue_carries_on_a_cut_answer(data_dir):
    provider = CutOff()
    with TestClient(app_for(data_dir, provider)) as c:
        first = chat(c, message="Write a to-do app in Python", mode="implement")
        conv = first[0]["conversation_id"]
        assert first[-1]["type"] == "done" and first[-1]["cut"] is True
        assert said(first).endswith(LENGTH_NOTE)
        # the page sends "Continue" in Auto mode: it keeps the cut answer's mode (and so its model)
        again = chat(c, message="Continue", mode="auto", conversation_id=conv)
    assert again[0]["mode"] == "implement" and again[-1]["cut"] is False
    messages, options = provider.calls[1]
    assert messages[-1]["content"] == CONTINUE_PROMPT
    earlier = messages[-2]
    assert earlier["role"] == "assistant" and "length limit" not in earlier["content"]  # Jarvis's note is left out
    assert earlier["content"].rstrip().endswith("step()")  # a long cut answer keeps its end, to continue from


def test_continue_on_the_phone_keeps_enough_of_the_answer(data_dir):
    ConfigStore(data_dir).update({"lean_prompt": True, "context_window": 4096, "max_answer_tokens": 1024})
    provider = CutOff()
    with TestClient(app_for(data_dir, provider)) as c:
        conv = chat(c, message="Write a to-do app in Python", mode="implement")[0]["conversation_id"]
        chat(c, message="continue", mode="implement", conversation_id=conv)
    messages = provider.calls[1][0]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert 1000 < len(messages[2]["content"]) <= 1600 and messages[2]["content"].rstrip().endswith("step()")


def test_the_phone_sets_its_cpu_threads():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        seen.append(json.loads(request.content))
        return httpx.Response(200, text=json.dumps({"message": {"content": "ok"}, "done": True, "done_reason": "stop"}) + "\n")

    import asyncio

    async def run(p):
        return [c async for c in p.chat_stream([{"role": "user", "content": "hi"}], ChatOptions(model="m"))]

    asyncio.run(run(OllamaProvider("http://127.0.0.1:11434", transport=httpx.MockTransport(handler), num_thread=4)))
    asyncio.run(run(OllamaProvider("http://127.0.0.1:11434", transport=httpx.MockTransport(handler))))
    assert seen[0]["options"]["num_thread"] == 4 and "num_thread" not in seen[1]["options"]
