"""Provider for local servers that speak the OpenAI-style chat API.

Works with llama.cpp's `llama-server`, LM Studio, LocalAI, vLLM and Ollama's
own /v1 endpoint. The endpoint should include the /v1 suffix, for example
http://127.0.0.1:8080/v1. No API key or account is needed for local servers.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from .base import ChatChunk, ChatOptions, LLMProvider, ModelInfo, ProviderError, ProviderStatus

NOT_RUNNING_HINT = (
    "Start your local server first. For llama.cpp: "
    "'llama-server -m path\\to\\model.gguf --port 8080', then use endpoint "
    "http://127.0.0.1:8080/v1. For LM Studio: start its local server and use "
    "http://127.0.0.1:1234/v1."
)


def _with_images(message: dict) -> dict:
    """OpenAI-style servers take images as content parts with data: URLs."""
    images = message.get("images")
    if not images:
        return message
    parts = [{"type": "text", "text": message.get("content", "")}]
    for b64 in images:
        mime = "image/png" if b64.startswith("iVBOR") else "image/jpeg"
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    return {"role": message["role"], "content": parts}


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(self, endpoint: str, timeout: float = 600, transport: httpx.AsyncBaseTransport | None = None):
        self.endpoint = endpoint.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=httpx.Timeout(timeout, connect=5.0),
            transport=transport,
            trust_env=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def status(self) -> ProviderStatus:
        try:
            resp = await self._client.get("/models", timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            msg = (f"Could not connect to the model server at {self.endpoint}."
                   if isinstance(exc, httpx.ConnectError) else
                   f"Problem talking to the model server at {self.endpoint}: {exc}")
            return ProviderStatus(reachable=False, error=msg)
        models = [ModelInfo(name=m.get("id", "")) for m in data.get("data", []) if m.get("id")]
        return ProviderStatus(reachable=True, models=models)

    async def chat_stream(self, messages: list[dict], options: ChatOptions) -> AsyncIterator[ChatChunk]:
        body: dict = {
            "model": options.model,
            "messages": [_with_images(m) for m in messages],
            "stream": True,
            "temperature": options.temperature,
        }
        if options.max_tokens:
            body["max_tokens"] = options.max_tokens
        if options.json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": options.json_schema},
            }
        try:
            async with self._client.stream("POST", "/chat/completions", json=body) as resp:
                if resp.status_code != 200:
                    await resp.aread()
                    if resp.status_code == 404:
                        raise ProviderError(
                            f"The server does not have the model '{options.model}'.",
                            "Choose one of the server's models in Settings.", "model_missing")
                    raise ProviderError(f"Model server returned HTTP {resp.status_code}: {resp.text[:500]}")
                done_reason = ""
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if data.get("error"):
                        raise ProviderError(f"The model reported an error: {data['error']}")
                    for choice in data.get("choices", []):
                        delta = choice.get("delta") or {}
                        thinking = delta.get("reasoning_content") or delta.get("reasoning")
                        if thinking:
                            yield ChatChunk("thinking", thinking)
                        if delta.get("content"):
                            yield ChatChunk("content", delta["content"])
                        done_reason = choice.get("finish_reason") or done_reason  # "length" = cut at max_tokens
                yield ChatChunk("done", stats={"done_reason": done_reason})
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Could not reach the model server at {self.endpoint}: {exc}",
                NOT_RUNNING_HINT, "not_reachable",
            ) from exc
