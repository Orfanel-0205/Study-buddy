"""Provider protocol tests (mocked HTTP) plus optional live tests against a running Ollama."""

from __future__ import annotations

import asyncio
import json
import os

import httpx
import pytest

from jarvis.llm import ChatOptions, OllamaProvider, OpenAICompatibleProvider, ProviderError


def run(coro):
    return asyncio.run(coro)


async def collect(provider, options, messages=None):
    out = []
    async for chunk in provider.chat_stream(messages or [{"role": "user", "content": "hi"}], options):
        out.append(chunk)
    await provider.aclose()
    return out


# ------------------------------------------------------------------ Ollama (mocked)
def ollama_transport(capabilities, seen):
    def handler(request: httpx.Request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": capabilities})
        if request.url.path == "/api/chat":
            body = json.loads(request.content)
            seen.append(body)
            if body["model"] == "missing":
                return httpx.Response(404, json={"error": "model 'missing' not found"})
            lines = [
                {"message": {"role": "assistant", "content": "", "thinking": "hmm"}, "done": False},
                {"message": {"role": "assistant", "content": "Hel"}, "done": False},
                {"message": {"role": "assistant", "content": "lo"}, "done": False},
                {"message": {"role": "assistant", "content": ""}, "done": True, "eval_count": 2,
                 "prompt_eval_count": 5, "total_duration": 1_500_000_000, "done_reason": "stop"},
            ]
            return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines).encode())
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.0.test"})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "m:1b", "size": 10, "details": {"parameter_size": "1B"},
                                                         "capabilities": capabilities}]})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_ollama_stream_and_think_flag_only_for_thinking_models():
    seen: list = []
    p = OllamaProvider("http://127.0.0.1:11434", transport=ollama_transport(["completion", "thinking"], seen))
    chunks = run(collect(p, ChatOptions(model="m:1b", think=True, context_window=4096)))
    assert "".join(c.text for c in chunks if c.kind == "content") == "Hello"
    assert [c.text for c in chunks if c.kind == "thinking"] == ["hmm"]
    assert chunks[-1].kind == "done" and chunks[-1].stats["seconds"] == 1.5
    assert seen[0]["think"] is True and seen[0]["options"]["num_ctx"] == 4096

    seen.clear()
    p = OllamaProvider("http://127.0.0.1:11434", transport=ollama_transport(["completion"], seen))
    run(collect(p, ChatOptions(model="m:1b", think=True)))
    assert "think" not in seen[0]  # gemma-style models reject the flag


def test_ollama_json_schema_and_missing_model():
    seen: list = []
    p = OllamaProvider("http://127.0.0.1:11434", transport=ollama_transport([], seen))
    run(collect(p, ChatOptions(model="m:1b", json_schema={"type": "object"})))
    assert seen[0]["format"] == {"type": "object"}
    p = OllamaProvider("http://127.0.0.1:11434", transport=ollama_transport([], seen))
    with pytest.raises(ProviderError) as exc:
        run(collect(p, ChatOptions(model="missing")))
    assert exc.value.code == "model_missing" and "ollama pull missing" in exc.value.hint


def test_ollama_status_and_connection_error():
    p = OllamaProvider("http://127.0.0.1:11434", transport=ollama_transport(["completion"], []))
    st = run(p.status())
    assert st.reachable and st.version == "0.0.test" and st.models[0].parameter_size == "1B"

    def refuse(request):
        raise httpx.ConnectError("refused")
    p = OllamaProvider("http://127.0.0.1:1", transport=httpx.MockTransport(refuse))
    st = run(p.status())
    assert not st.reachable and "not running" in st.error
    with pytest.raises(ProviderError) as exc:
        run(collect(p, ChatOptions(model="x")))
    assert exc.value.code == "not_reachable"


# ------------------------------------------------------------------ OpenAI-compatible (mocked)
def test_openai_compatible_stream():
    seen = []

    def handler(request: httpx.Request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "local-model"}]})
        seen.append(json.loads(request.content))
        events = [
            {"choices": [{"delta": {"role": "assistant", "reasoning_content": "think"}}]},
            {"choices": [{"delta": {"content": "Hi"}}]},
            {"choices": [{"delta": {"content": " there"}}]},
        ]
        body = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
        return httpx.Response(200, content=body.encode())

    p = OpenAICompatibleProvider("http://127.0.0.1:8080/v1", transport=httpx.MockTransport(handler))
    assert [m.name for m in run(p.status()).models] == ["local-model"]
    p = OpenAICompatibleProvider("http://127.0.0.1:8080/v1", transport=httpx.MockTransport(handler))
    chunks = run(collect(p, ChatOptions(model="local-model", json_schema={"type": "object"})))
    assert "".join(c.text for c in chunks if c.kind == "content") == "Hi there"
    assert any(c.kind == "thinking" for c in chunks)
    assert seen[0]["response_format"]["type"] == "json_schema"


# ------------------------------------------------------------------ live (skipped if Ollama isn't running)
def _ollama_models():
    try:
        r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=2, trust_env=False)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


LIVE_MODELS = _ollama_models()
LIVE_MODEL = os.environ.get("JARVIS_TEST_MODEL") or next(
    (m for m in ("gemma3:1b", "qwen3:1.7b", "llama3.2:latest") if m in LIVE_MODELS), "")
live = pytest.mark.skipif(not LIVE_MODEL, reason="Ollama with a small model is not available")


@live
def test_live_ollama_chat():
    p = OllamaProvider("http://127.0.0.1:11434", timeout=300)
    text = run(p.chat([{"role": "user", "content": "Reply with exactly the word: pong"}],
                      ChatOptions(model=LIVE_MODEL, temperature=0, context_window=2048)))
    asyncio.run(p.aclose())
    assert "pong" in text.lower()


@live
def test_live_ollama_json_schema():
    from jarvis.assistant.prompts import BREAKDOWN_SCHEMA
    from jarvis.assistant.service import parse_json_reply
    p = OllamaProvider("http://127.0.0.1:11434", timeout=300)
    text = run(p.chat([{"role": "user", "content": "Break 'bake a cake' into 3 steps. JSON only."}],
                      ChatOptions(model=LIVE_MODEL, temperature=0, context_window=2048, json_schema=BREAKDOWN_SCHEMA)))
    asyncio.run(p.aclose())
    data = parse_json_reply(text)
    assert isinstance(data["steps"], list) and data["steps"]


@live
def test_live_openai_compatible_endpoint_of_ollama():
    p = OpenAICompatibleProvider("http://127.0.0.1:11434/v1", timeout=300)
    text = run(p.chat([{"role": "user", "content": "Reply with exactly the word: pong"}],
                      ChatOptions(model=LIVE_MODEL, temperature=0)))
    asyncio.run(p.aclose())
    assert "pong" in text.lower()
