from __future__ import annotations

from typing import Protocol, runtime_checkable

from infra.llm_client import LLMResponse


@runtime_checkable
class LLMAdapter(Protocol):
    provider: str
    model_id: str

    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse: ...
