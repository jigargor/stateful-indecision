"""OpenAI / OpenAI-compatible adapter. Stub for v1 — raises if called without
the openai package installed. Drop-in ready for GPT-4o, o3, etc."""
from __future__ import annotations

import os
import time

from infra.llm_client import LLMError, LLMResponse


class OpenAIAdapter:
    provider = "openai"

    def __init__(self, model_id: str, api_key: str | None = None, base_url: str | None = None):
        self.model_id = model_id
        self.base_url = base_url
        resolved = api_key if api_key else os.getenv("OPENAI_API_KEY", "")
        # Local OpenAI-compatible servers (Ollama, LM Studio, vLLM) often ignore the key.
        if not resolved and base_url:
            resolved = "local-openai-compat"
        self.api_key = resolved

    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY is not set (set the env var or provide openai_base_url for local servers)")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMError("openai package is not installed. Run: uv add openai") from exc

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        delays = [0, 1, 4]
        last_error: Exception | None = None
        for delay in delays:
            if delay:
                time.sleep(delay)
            try:
                wall_start = time.time() * 1000
                stream_started = None
                text_parts: list[str] = []
                tokens_in = 0
                tokens_out = 0

                full_messages = [{"role": "system", "content": system}] + messages
                stream = client.chat.completions.create(
                    model=self.model_id,
                    messages=full_messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                )
                for chunk in stream:
                    if stream_started is None:
                        stream_started = time.time() * 1000
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        text_parts.append(delta.content)

                wall_end = time.time() * 1000
                ttft_ms = (stream_started - wall_start) if stream_started else (wall_end - wall_start)
                return LLMResponse(
                    text="".join(text_parts).strip(),
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    stop_reason="stop",
                    wall_start_ms=wall_start,
                    wall_end_ms=wall_end,
                    ttft_ms=ttft_ms,
                    model_id=self.model_id,
                )
            except Exception as exc:
                last_error = exc

        raise LLMError(f"OpenAI completion failed after retries: {last_error}")
