from __future__ import annotations

import json
from pathlib import Path

from agent.executor import (
    REFLECTION_SUB_ACTIONS,
    SUB_ACTION_ROLE_MAP,
    Executor,
)


def _load_prompt_pack() -> dict:
    pack_path = Path(__file__).resolve().parent.parent / "prompts" / "sage_team_prompts.json"
    return json.loads(pack_path.read_text(encoding="utf-8"))


def test_prompt_pack_loads_and_has_required_roles() -> None:
    pack = _load_prompt_pack()
    assert "roles" in pack
    roles = pack["roles"]
    assert isinstance(roles, dict)
    for role_name in {"research_lead", "assistant_researcher", "checker"}:
        assert role_name in roles, f"missing role: {role_name}"
        assert "system_prompt" in roles[role_name]
        assert isinstance(roles[role_name]["system_prompt"], str)
        assert len(roles[role_name]["system_prompt"].strip()) > 0


def test_prompt_pack_has_shared_reflection() -> None:
    pack = _load_prompt_pack()
    shared = pack.get("shared")
    assert isinstance(shared, dict)
    assert "post_cycle_reflection_prompt" in shared
    assert isinstance(shared["post_cycle_reflection_prompt"], str)
    assert len(shared["post_cycle_reflection_prompt"].strip()) > 0


def test_sub_action_role_map_references_valid_roles() -> None:
    pack = _load_prompt_pack()
    valid_roles = set(pack["roles"].keys())
    for sub_action, role_name in SUB_ACTION_ROLE_MAP.items():
        assert role_name in valid_roles, (
            f"SUB_ACTION_ROLE_MAP[{sub_action!r}] = {role_name!r} "
            f"not found in prompt pack roles: {valid_roles}"
        )


def test_resolve_team_prompt_returns_role_system_for_mapped_actions() -> None:
    pack = _load_prompt_pack()
    executor = _make_executor_with_pack(pack)
    for sub_action, role_name in SUB_ACTION_ROLE_MAP.items():
        role_system, _ = executor._resolve_team_prompt(sub_action=sub_action)
        expected = pack["roles"][role_name]["system_prompt"].strip()
        assert role_system == expected, (
            f"_resolve_team_prompt({sub_action!r}) returned wrong system prompt"
        )


def test_resolve_team_prompt_returns_none_for_unmapped_actions() -> None:
    pack = _load_prompt_pack()
    executor = _make_executor_with_pack(pack)
    unmapped = {"VENT", "HOBBY", "VISIT_COMMONS", "VISIT_ROUNDTABLE", "CALL_TOWNHALL"}
    for sub_action in unmapped:
        role_system, _ = executor._resolve_team_prompt(sub_action=sub_action)
        assert role_system is None, (
            f"expected None for unmapped {sub_action!r}, got system prompt"
        )


def test_resolve_team_prompt_prefers_configured_team_role() -> None:
    pack = _load_prompt_pack()
    executor = _make_executor_with_pack(pack)
    executor.team_role = "checker"

    role_system, _ = executor._resolve_team_prompt(sub_action="DISCOVER")

    assert role_system == pack["roles"]["checker"]["system_prompt"].strip()


def test_resolve_team_prompt_returns_reflection_for_reflection_actions() -> None:
    pack = _load_prompt_pack()
    executor = _make_executor_with_pack(pack)
    expected_reflection = pack["shared"]["post_cycle_reflection_prompt"].strip()
    for sub_action in REFLECTION_SUB_ACTIONS:
        _, reflection = executor._resolve_team_prompt(sub_action=sub_action)
        assert reflection == expected_reflection, (
            f"_resolve_team_prompt({sub_action!r}) missing reflection instruction"
        )


def test_resolve_team_prompt_no_reflection_for_non_reflection_actions() -> None:
    pack = _load_prompt_pack()
    executor = _make_executor_with_pack(pack)
    non_reflection = {"DISCOVER", "READ", "WRITE", "CHALLENGE", "VENT"}
    for sub_action in non_reflection:
        _, reflection = executor._resolve_team_prompt(sub_action=sub_action)
        assert reflection is None, (
            f"unexpected reflection for {sub_action!r}"
        )


def test_resolve_team_prompt_returns_none_without_pack() -> None:
    executor = _make_executor_with_pack(None)
    role_system, reflection = executor._resolve_team_prompt(sub_action="DISCOVER")
    assert role_system is None
    assert reflection is None


def _make_executor_with_pack(pack: dict | None) -> Executor:
    """Build a minimal Executor with only prompt_pack set (no LLM or storage)."""
    executor = object.__new__(Executor)
    executor.prompt_pack = pack
    return executor
