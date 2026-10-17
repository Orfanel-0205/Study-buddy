"""Local language model providers."""

from __future__ import annotations

from ..config import Settings, ensure_local_endpoint
from .base import ChatChunk, ChatOptions, LLMProvider, ModelInfo, ProviderError, ProviderStatus
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatibleProvider

# Preferred models, best first, used when no model is chosen in Settings.
# Only models already installed are ever picked; Jarvis never downloads anything itself.
PREFERRED_MODELS = [
    "qwen2.5-coder:14b", "qwen3:14b", "qwen2.5-coder:7b", "qwen3:8b", "llama3.1:8b",
    "gemma3:4b", "qwen3:4b", "llama3.2:3b", "llama3.2:latest", "qwen3:1.7b",
    "llama3.2:1b", "gemma3:1b",
]


def create_provider(settings: Settings) -> LLMProvider:
    ensure_local_endpoint(settings)
    if settings.provider == "openai_compatible":
        return OpenAICompatibleProvider(settings.endpoint, timeout=settings.request_timeout)
    return OllamaProvider(settings.endpoint, timeout=settings.request_timeout)


def pick_model(configured: str, installed: list[str]) -> str:
    """Return the model to use: the configured one, else the best installed one."""
    if configured:
        return configured
    for name in PREFERRED_MODELS:
        if name in installed:
            return name
    # Skip embedding-only models when guessing.
    usable = [m for m in installed if "embed" not in m.lower()]
    return usable[0] if usable else ""


__all__ = [
    "ChatChunk", "ChatOptions", "LLMProvider", "ModelInfo", "ProviderError", "ProviderStatus",
    "OllamaProvider", "OpenAICompatibleProvider", "create_provider", "pick_model",
    "PREFERRED_MODELS",
]
