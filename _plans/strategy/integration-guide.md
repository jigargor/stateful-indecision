# Integration Guide — Adapters, Failure Modes, and MCP Boundary

**Wave:** 5 — Formalism and Integration Layer  
**Audience:** Contributors adding new model providers, tool integrations, or external system boundaries.

All statements in this document are verifiable against source code. Code paths are referenced
by file and function name so readers can audit directly.

---

## 1. LLMAdapter Protocol

Defined in `adapters/base.py` as a `@runtime_checkable` Protocol.

### Required attributes

| Attribute   | Type  | Description                               |
|-------------|-------|-------------------------------------------|
| `provider`  | `str` | Short provider name (e.g. `"anthropic"`). |
| `model_id`  | `str` | Model identifier passed to the API.       |

### Required method

```python
def complete(
    self,
    system: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> LLMResponse: ...
```

`LLMResponse` (defined in `infra/llm_client.py`) is a dataclass with fields:
`text`, `tokens_in`, `tokens_out`, `stop_reason`, `wall_start_ms`, `wall_end_ms`,
`ttft_ms`, `model_id`.

### Adapter registration

`adapters/__init__.py` exposes two factory functions:

- **`create_adapter(provider, model_id, **kwargs)`** — direct construction from `PROVIDER_MAP`.
  Raises `ValueError` for unknown providers. No mock fallback — missing API keys propagate
  to the adapter and may cause runtime errors.
- **`create_adapter_auto(model_spec)`** — when given an explicit `"provider:model_id"` string,
  delegates to `create_adapter()` directly (no mock fallback). Mock fallback only engages
  when no explicit spec is provided: the function reads env vars `DEFAULT_PROVIDER` /
  `DEFAULT_MODEL`, then checks for the required API key and substitutes `MockAdapter` if
  the key is missing.

`PROVIDER_MAP` currently contains `"anthropic"`, `"openai"`, and `"mock"`.

### Adding a new adapter

1. Create `adapters/my_provider.py` with a class satisfying `LLMAdapter`.
2. Set `provider` as a class attribute and implement `complete(...)`.
3. Add an entry to `PROVIDER_MAP` in `adapters/__init__.py`.
4. If the provider needs an API key, add the env var name to `key_map` in
   `create_adapter_auto` for automatic mock fallback.

---

## 2. Model-Output Failure Modes

### 2.1 Structured output retry flow

`Executor._parse_structured_with_retry` (`agent/executor.py`) implements the three-outcome
contract from Wave 1:

1. **First parse attempt** — `_parse_and_validate_structured(sub_action, raw_output)`:
   - Attempts `json.loads`, rejects non-dict results.
   - Validates against `AnalyzeStructuredOutput` (for ANALYZE) or `AnnotateStructuredOutput`
     (for ANNOTATE) via Pydantic `model_validate`.
   - **Outcome A (success):** returns validated dict; no retry needed.

2. **Repair LLM call** — on first-parse failure:
   - Calls `self.llm.complete(...)` with `temperature=0.0`, `max_tokens=2048`.
   - Prompt instructs the model to rewrite the output as valid JSON only.
   - **Outcome B (repair success):** returns validated dict from repaired output.

3. **Double failure sentinel** — if repair also fails:
   - Returns `{"_validation_failure": {"sub_action": ..., "reason": "invalid_structured_output_after_retry"}, "text": raw_output}`.
   - **Outcome C (sentinel):** the executor checks for `_validation_failure` and blocks
     catalog side effects for ANNOTATE (no Zotero write on bad data). The side effect
     `executor.structured.validation_failed` is appended.

### 2.2 LLMError propagation

```
Adapter raises LLMError
  → Executor.execute() propagates (no catch)
  → decision.step() propagates
  → runner._run_inner() catches LLMError
  → runner appends agent.error event to public ledger
  → raises SystemExit(1)
```

The `agent.error` event payload includes `error_type`, `message`, and `decision_number`.

### 2.3 Adapter-level retry

Both `AnthropicAdapter` and `OpenAIAdapter` implement identical retry logic:
- 3 attempts with delays `[0, 1, 4]` seconds.
- On all-attempts failure: raises `LLMError` with the last exception message.

### 2.4 Other runtime errors

| Error type             | Exit code | Source                                 |
|------------------------|-----------|----------------------------------------|
| `LLMError`             | 1         | Adapter completion failure             |
| `ChainCorruptionError` | 2         | Verifier boundary check (enforce mode) |
| `FirewallError`        | 3         | Storage path escapes ecosystem bounds  |
| `KeyboardInterrupt`    | —         | Graceful shutdown, `agent.shutdown` event |

---

## 3. Tool Governance

Tool dispatch in `Executor._tool_allowed` (`agent/executor.py`) follows a three-tier model:

| `tool_allowlist` value | Behavior                                  | When                              |
|------------------------|-------------------------------------------|-----------------------------------|
| `None`                 | Allow all tools                           | No `run_config` provided          |
| `set()` (empty)        | Block all tools                           | `run_config` present, no list     |
| `{"web.search", ...}`  | Allow only named tools                    | Explicit list in `run_config`     |

The runner emits an `agent.tool.allowlist_applied` event at startup recording the policy.
Side effects log `tool.blocked:<tool_name>` when a tool call is rejected in most code paths
(e.g. DISCOVER, ANALYZE, ANNOTATE). However, not all paths emit the blocked event — the
READ handler checks the allowlist for `web.search` but silently returns an empty result set
without appending a `tool.blocked:web.search` side effect. Consumers should not assume
blocked-tool events are emitted universally.

---

## 4. MCP Boundary (Future Adapter Seam)

MCP (Model Context Protocol) integration is not implemented in v1 but the architecture
has a clear attachment point: the `adapters/` directory.

### Where MCP would attach

- **Tool provider boundary:** `adapters/` already abstracts model interaction behind
  `LLMAdapter`. An MCP adapter would implement the same Protocol, translating MCP tool
  calls into the `complete()` interface or extending it with tool-use capabilities.
- **Tool dispatch:** `Executor._tool_allowed` + `_dependency_aware_tool_plan` already
  model which tools are available per step. MCP tool descriptors would map into this
  existing allowlist mechanism.
- **Registration:** A new adapter entry in `PROVIDER_MAP` (e.g. `"mcp"`) pointing to
  an `McpAdapter` class that wraps an MCP server connection.

### What exists today

- Tool governance model (allowlist, block-all, allow-all) — fully operational.
- Dependency-aware tool planning skeleton (`_dependency_aware_tool_plan`).
- Side-effect tracking for all tool interactions.
- No MCP protocol implementation — this is a documented seam, not a running feature.

---

## 5. Cross-References

- Decision loop phases: `agent/decision.py` `DECISION_PHASES` constant.
- Latent reasoning events: `agent/executor.py` (`emit_latent_reasoning_events` flag),
  `agent/decision.py` (`enable_pi_reason_then_action` flag).
- Sequence and layering diagrams: `_plans/auton_and_agent_layers.md` §4 and §9.
- Event payload schemas: `schemas/events.py`, generated JSON schemas in `schemas/generated/`.
- Safety and governance: `safety/kill_switch.py`, `safety/firewalls.py`.
