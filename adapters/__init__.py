from __future__ import annotations

import os

from adapters.anthropic import AnthropicAdapter
from adapters.base import LLMAdapter
from adapters.mock import MockAdapter
from adapters.openai_adapter import OpenAIAdapter

PROVIDER_MAP: dict[str, type] = {
    "anthropic": AnthropicAdapter,
    "openai": OpenAIAdapter,
    "mock": MockAdapter,
}


def create_adapter(
    provider: str,
    model_id: str,
    **kwargs,
) -> LLMAdapter:
    """Create an LLM adapter for the given provider and model.

    Raises ValueError for unknown providers. Does NOT fall back to mock;
    use create_adapter_auto() for automatic mock fallback on missing keys."""
    cls = PROVIDER_MAP.get(provider)
    if cls is None:
        raise ValueError(f"unknown provider: {provider}. Available: {list(PROVIDER_MAP.keys())}")
    return cls(model_id=model_id, **kwargs)


def create_adapter_auto(model_spec: str | None = None) -> LLMAdapter:
    """Create an adapter from a 'provider:model_id' string, or fall back to
    env defaults, or fall back to mock."""
    if model_spec and ":" in model_spec:
        provider, model_id = model_spec.split(":", 1)
        return create_adapter(provider, model_id)

    provider = os.getenv("DEFAULT_PROVIDER", "anthropic")
    model_id = model_spec or os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6-20250514")

    key_map = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
    required_key = key_map.get(provider, "")
    if required_key and not os.getenv(required_key):
        return MockAdapter(model_id=f"mock-fallback-{model_id}")

    return create_adapter(provider, model_id)


__all__ = [
    "AnthropicAdapter",
    "LLMAdapter",
    "MockAdapter",
    "OpenAIAdapter",
    "create_adapter",
    "create_adapter_auto",
]
