from __future__ import annotations

import os
import time
from dataclasses import dataclass


class LLMError(Exception):
    pass


@dataclass
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int
    stop_reason: str
    wall_start_ms: float
    wall_end_ms: float
    ttft_ms: float
    model_id: str


class LLMClient:
    def __init__(self, model_id: str):
        self.model_id = model_id

    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set")

        try:
            import anthropic
        except Exception as exc:
            raise LLMError("anthropic package is not available") from exc

        client = anthropic.Anthropic(api_key=api_key)
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
                stop_reason = "unknown"

                with client.messages.stream(
                    model=self.model_id,
                    max_tokens=max_tokens,
                    system=system,
                    messages=messages,
                    temperature=temperature,
                ) as stream:
                    for event in stream:
                        if stream_started is None:
                            stream_started = time.time() * 1000
                        event_type = getattr(event, "type", "")
                        if event_type == "content_block_delta":
                            delta_text = getattr(getattr(event, "delta", None), "text", "")
                            if delta_text:
                                text_parts.append(delta_text)
                        elif event_type == "message_delta":
                            stop_reason = str(getattr(event, "stop_reason", stop_reason))

                    final_message = stream.get_final_message()
                    usage = getattr(final_message, "usage", None)
                    if usage is not None:
                        tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
                        tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
                    if getattr(final_message, "stop_reason", None):
                        stop_reason = str(final_message.stop_reason)

                wall_end = time.time() * 1000
                ttft_ms = (stream_started - wall_start) if stream_started else (wall_end - wall_start)
                return LLMResponse(
                    text="".join(text_parts).strip(),
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    stop_reason=stop_reason,
                    wall_start_ms=wall_start,
                    wall_end_ms=wall_end,
                    ttft_ms=ttft_ms,
                    model_id=self.model_id,
                )
            except Exception as exc:
                last_error = exc

        raise LLMError(f"LLM completion failed after retries: {last_error}")
