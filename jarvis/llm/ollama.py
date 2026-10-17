"""Ollama provider (https://ollama.com). Talks to the local Ollama HTTP API."""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from .base import ChatChunk, ChatOptions, LLMProvider, ModelInfo, ProviderError, ProviderStatus

NOT_RUNNING_HINT = (
    "Start Ollama (Windows: open 'Ollama' from the Start menu; macOS: open the Ollama app; "
    "Linux: run 'ollama serve'). If it isn't installed yet, download it once from "
    "https://ollama.com/download while you have internet."
)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, endpoint: str, timeout: float = 600, transport: httpx.AsyncBaseTransport | None = None):
        self.endpoint = endpoint.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=httpx.Timeout(timeout, connect=5.0),
            transport=transport,
            trust_env=False,  # never route local traffic through a system proxy
        )
        self._caps: dict[str, list[str]] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def status(self) -> ProviderStatus:
        try:
            version = (await self._client.get("/api/version", timeout=5)).json().get("version", "")
            resp = await self._client.get("/api/tags", timeout=10)
            resp.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            return ProviderStatus(reachable=False, error=_describe(exc, self.endpoint))
        models = [
            ModelInfo(
                name=m.get("name", ""),
                size_bytes=int(m.get("size") or 0),
                parameter_size=(m.get("details") or {}).get("parameter_size", ""),
                capabilities=list(m.get("capabilities") or []),
            )
            for m in resp.json().get("models", [])
        ]
        for m in models:
            if m.capabilities:
                self._caps[m.name] = m.capabilities
        return ProviderStatus(reachable=True, version=version, models=models)

    async def _capabilities(self, model: str) -> list[str]:
        if model not in self._caps:
            try:
                resp = await self._client.post("/api/show", json={"model": model}, timeout=15)
                self._caps[model] = list(resp.json().get("capabilities") or []) if resp.is_success else []
            except (httpx.HTTPError, ValueError):
                return []
        return self._caps[model]

    async def model_supports_thinking(self, model: str) -> bool:
        return "thinking" in await self._capabilities(model)

    async def chat_stream(self, messages: list[dict], options: ChatOptions) -> AsyncIterator[ChatChunk]:
        body: dict = {
            "model": options.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": options.temperature, "num_ctx": options.context_window},
        }
        # Only thinking-capable models accept the flag; others reject think=true.
        if await self.model_supports_thinking(options.model):
            body["think"] = bool(options.think) and options.json_schema is None
        if options.json_schema is not None:
            body["format"] = options.json_schema
        try:
            async with self._client.stream("POST", "/api/chat", json=body) as resp:
                if resp.status_code != 200:
                    await resp.aread()
                    raise _http_error(resp, options.model)
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("error"):
                        raise ProviderError(f"The model reported an error: {data['error']}")
                    msg = data.get("message") or {}
                    if msg.get("thinking"):
                        yield ChatChunk("thinking", msg["thinking"])
                    if msg.get("content"):
                        yield ChatChunk("content", msg["content"])
                    if data.get("done"):
                        yield ChatChunk("done", stats={
                            "prompt_tokens": data.get("prompt_eval_count"),
                            "output_tokens": data.get("eval_count"),
                            "seconds": round((data.get("total_duration") or 0) / 1e9, 2),
                            "done_reason": data.get("done_reason", ""),
                        })
                        return
        except httpx.HTTPError as exc:
            raise ProviderError(_describe(exc, self.endpoint), NOT_RUNNING_HINT, "not_reachable") from exc


def _http_error(resp: httpx.Response, model: str) -> ProviderError:
    try:
        detail = resp.json().get("error", resp.text)
    except ValueError:
        detail = resp.text
    if resp.status_code == 404 and "not found" in str(detail).lower():
        return ProviderError(
            f"The model '{model}' is not installed in Ollama.",
            f"Run 'ollama pull {model}' once while online, or choose an installed model in Settings.",
            "model_missing",
        )
    return ProviderError(f"Ollama returned HTTP {resp.status_code}: {detail}")


def _describe(exc: Exception, endpoint: str) -> str:
    if isinstance(exc, httpx.ConnectError):
        return f"Could not connect to Ollama at {endpoint}. It is probably not running."
    if isinstance(exc, httpx.TimeoutException):
        return (f"Ollama at {endpoint} took too long to respond. Large models can be slow "
                "on the first request while they load into memory.")
    return f"Problem talking to Ollama at {endpoint}: {exc}"
