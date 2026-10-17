"""The provider interface. Any local model server can be plugged in by
implementing LLMProvider (see ollama.py and openai_compat.py for examples)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Literal


@dataclass
class ModelInfo:
    name: str
    size_bytes: int = 0
    parameter_size: str = ""
    capabilities: list[str] = field(default_factory=list)


@dataclass
class ProviderStatus:
    reachable: bool
    version: str = ""
    models: list[ModelInfo] = field(default_factory=list)
    error: str = ""


@dataclass
class ChatChunk:
    kind: Literal["content", "thinking", "done"]
    text: str = ""
    stats: dict = field(default_factory=dict)


@dataclass
class ChatOptions:
    model: str
    temperature: float = 0.3
    context_window: int = 8192
    think: bool = False
    json_schema: dict | None = None  # ask for structured JSON output


class ProviderError(RuntimeError):
    """A problem talking to the local model, with a hint the user can act on."""

    def __init__(self, message: str, hint: str = "", code: str = "provider_error"):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.code = code


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def status(self) -> ProviderStatus:
        """Is the model server running, and which models does it have?"""

    @abstractmethod
    def chat_stream(self, messages: list[dict], options: ChatOptions) -> AsyncIterator[ChatChunk]:
        """Stream a reply. Cancelling the iteration must stop generation."""

    async def model_supports_thinking(self, model: str) -> bool:
        return False

    async def chat(self, messages: list[dict], options: ChatOptions) -> str:
        parts: list[str] = []
        async for chunk in self.chat_stream(messages, options):
            if chunk.kind == "content":
                parts.append(chunk.text)
        return "".join(parts)

    async def aclose(self) -> None:
        pass
