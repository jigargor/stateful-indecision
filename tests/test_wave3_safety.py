"""Wave 3 — Safety and Governance tests.

Covers: hard action masks, tool allowlist enforcement, kill-switch outcomes,
boundary verification, and regression (default behavior unchanged).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.executor import Executor
from agent.policy import ActionDistribution, Policy
from agent.runner import _parse_tool_allowlist, _verify_boundary
from core.verifier import verify_chain
from core.writer import ChainCorruptionError, ChainWriter
from safety.kill_switch import KillSwitchMonitor
from schemas.events import ActionVocabulary, EventEnvelope


VOCAB_PATH = Path("seeds/action_vocabulary.json")


class _State:
    recent_notebook: list[str] = []
    in_commons: bool = False


def _make_vocab() -> ActionVocabulary:
    return ActionVocabulary.load(VOCAB_PATH)


# ---------------------------------------------------------------------------
# H.1) Hard mask tests
# ---------------------------------------------------------------------------


def test_blocked_leaf_excluded_from_proposal() -> None:
    vocab = _make_vocab()
    policy = Policy(vocab, blocked_leaves={"READ", "DISCOVER"})
    dist = policy.propose(_State())
    for sub in dist.sub_dist.values():
        assert "READ" not in sub
        assert "DISCOVER" not in sub


def test_all_leaves_of_category_blocked_removes_category() -> None:
    vocab = _make_vocab()
    research_leaves = set(vocab.categories.get("RESEARCH", []))
    assert research_leaves, "RESEARCH category must exist in vocab"
    policy = Policy(vocab, blocked_leaves=research_leaves)
    dist = policy.propose(_State())
    assert "RESEARCH" not in dist.top_dist


def test_blocked_category_not_injected_via_notebook_bias() -> None:
    """All RESEARCH leaves blocked + 5+ notebook entries must not re-inject RESEARCH via bias."""
    vocab = _make_vocab()
    research_leaves = set(vocab.categories.get("RESEARCH", []))
    assert research_leaves, "RESEARCH category must exist in vocab"
    policy = Policy(vocab, blocked_leaves=research_leaves)
    state = _State()
    state.recent_notebook = [f"entry-{i}" for i in range(6)]
    dist = policy.propose(state)
    assert "RESEARCH" not in dist.top_dist


def test_partial_block_allows_valid_bias() -> None:
    """Only some RESEARCH leaves blocked + 5+ notebook entries: RESEARCH still appears."""
    vocab = _make_vocab()
    research_leaves = list(vocab.categories.get("RESEARCH", []))
    assert len(research_leaves) >= 2, "Need at least 2 RESEARCH leaves for partial block test"
    policy = Policy(vocab, blocked_leaves={research_leaves[0]})
    state = _State()
    state.recent_notebook = [f"entry-{i}" for i in range(6)]
    dist = policy.propose(state)
    assert "RESEARCH" in dist.top_dist


def test_all_leaves_blocked_raises_value_error() -> None:
    vocab = _make_vocab()
    all_leaves = set(vocab.all_leaves)
    policy = Policy(vocab, blocked_leaves=all_leaves)
    with pytest.raises(ValueError, match="all action leaves are masked"):
        policy.propose(_State())


def test_invalid_leaf_name_raises_value_error() -> None:
    vocab = _make_vocab()
    with pytest.raises(ValueError, match="unknown leaf names"):
        Policy(vocab, blocked_leaves={"TOTALLY_FAKE_LEAF"})


def test_blocked_leaves_none_means_no_masking() -> None:
    vocab = _make_vocab()
    policy_none = Policy(vocab, blocked_leaves=None)
    policy_empty = Policy(vocab, blocked_leaves=set())
    dist_none = policy_none.propose(_State())
    dist_empty = policy_empty.propose(_State())
    assert dist_none.top_dist == dist_empty.top_dist
    assert dist_none.sub_dist == dist_empty.sub_dist


def test_blocked_leaves_is_frozenset() -> None:
    vocab = _make_vocab()
    policy = Policy(vocab, blocked_leaves={"READ"})
    assert isinstance(policy.blocked_leaves, frozenset)


def test_multiple_blocked_leaves_across_categories() -> None:
    vocab = _make_vocab()
    policy = Policy(vocab, blocked_leaves={"READ", "WRITE", "DREAM"})
    dist = policy.propose(_State())
    for sub in dist.sub_dist.values():
        assert "READ" not in sub
        assert "WRITE" not in sub
        assert "DREAM" not in sub


# ---------------------------------------------------------------------------
# H.2) Tool allowlist tests
# ---------------------------------------------------------------------------


def test_parse_tool_allowlist_none_returns_empty_set() -> None:
    result = _parse_tool_allowlist(None)
    assert result == set()


def test_parse_tool_allowlist_empty_list_returns_empty_set() -> None:
    result = _parse_tool_allowlist([])
    assert result == set()


def test_parse_tool_allowlist_with_tools() -> None:
    result = _parse_tool_allowlist(["web.search", "web.fetch"])
    assert result == {"web.search", "web.fetch"}


def test_tool_allowed_none_means_allow_all() -> None:
    """When tool_allowlist is None (no run_config), all tools are allowed."""
    from unittest.mock import MagicMock

    llm = MagicMock()
    storage = MagicMock()
    storage.corpus_dir.return_value = Path("/tmp/corpus")
    ex = Executor(llm=llm, storage=storage, agent_id="a1", tool_allowlist=None)
    assert ex._tool_allowed("web.search") is True
    assert ex._tool_allowed("scite.citations") is True
    assert ex._tool_allowed("anything.at.all") is True


def test_tool_allowed_empty_set_blocks_all() -> None:
    """When tool_allowlist is empty set, all tools are blocked."""
    from unittest.mock import MagicMock

    llm = MagicMock()
    storage = MagicMock()
    storage.corpus_dir.return_value = Path("/tmp/corpus")
    ex = Executor(llm=llm, storage=storage, agent_id="a1", tool_allowlist=set())
    assert ex._tool_allowed("web.search") is False
    assert ex._tool_allowed("scite.citations") is False


def test_tool_allowed_explicit_list() -> None:
    """Only tools in the allowlist are permitted."""
    from unittest.mock import MagicMock

    llm = MagicMock()
    storage = MagicMock()
    storage.corpus_dir.return_value = Path("/tmp/corpus")
    ex = Executor(
        llm=llm, storage=storage, agent_id="a1",
        tool_allowlist={"web.search"},
    )
    assert ex._tool_allowed("web.search") is True
    assert ex._tool_allowed("web.fetch") is False
    assert ex._tool_allowed("scite.citations") is False


# ---------------------------------------------------------------------------
# H.3) Verifier hook (boundary) tests
# ---------------------------------------------------------------------------


def _write_valid_chain(path: Path, n: int = 3) -> None:
    writer = ChainWriter(path)
    for i in range(n):
        writer.append(
            "test.event",
            {"index": i},
            ecosystem_id="test",
            agent_id="agent-1",
        )


def test_boundary_verification_pass(tmp_path: Path) -> None:
    ledger = tmp_path / "public.jsonl"
    _write_valid_chain(ledger, 3)
    eval_writer = ChainWriter(tmp_path / "evaluation.jsonl")
    _verify_boundary(
        eval_writer=eval_writer,
        ledger_path=ledger,
        boundary="start",
        ecosystem_id="test",
        agent_id="agent-1",
        verifier_mode="warn",
    )
    text = (tmp_path / "evaluation.jsonl").read_text("utf-8")
    assert '"outcome":"pass"' in text
    assert '"boundary":"start"' in text


def test_boundary_verification_fail_corrupt_chain(tmp_path: Path) -> None:
    ledger = tmp_path / "public.jsonl"
    _write_valid_chain(ledger, 2)
    lines = ledger.read_text("utf-8").splitlines()
    corrupted = json.loads(lines[-1])
    corrupted["prev_hash"] = "a" * 64
    from core.canonical_json import canonical_hash, canonical_json
    hash_source = dict(corrupted)
    hash_source.pop("record_hash", None)
    corrupted["record_hash"] = canonical_hash(hash_source)
    lines[-1] = canonical_json(corrupted).decode("utf-8")
    ledger.write_text("\n".join(lines) + "\n", "utf-8")

    eval_writer = ChainWriter(tmp_path / "evaluation.jsonl")
    _verify_boundary(
        eval_writer=eval_writer,
        ledger_path=ledger,
        boundary="terminal",
        ecosystem_id="test",
        agent_id="agent-1",
        verifier_mode="warn",
    )
    text = (tmp_path / "evaluation.jsonl").read_text("utf-8")
    assert '"outcome":"fail"' in text
    assert '"boundary":"terminal"' in text


def test_boundary_verification_enforce_mode_raises(tmp_path: Path) -> None:
    ledger = tmp_path / "public.jsonl"
    _write_valid_chain(ledger, 2)
    lines = ledger.read_text("utf-8").splitlines()
    corrupted = json.loads(lines[-1])
    corrupted["prev_hash"] = "b" * 64
    from core.canonical_json import canonical_hash, canonical_json
    hash_source = dict(corrupted)
    hash_source.pop("record_hash", None)
    corrupted["record_hash"] = canonical_hash(hash_source)
    lines[-1] = canonical_json(corrupted).decode("utf-8")
    ledger.write_text("\n".join(lines) + "\n", "utf-8")

    eval_writer = ChainWriter(tmp_path / "evaluation.jsonl")
    with pytest.raises(ChainCorruptionError, match="verifier terminal check failed"):
        _verify_boundary(
            eval_writer=eval_writer,
            ledger_path=ledger,
            boundary="terminal",
            ecosystem_id="test",
            agent_id="agent-1",
            verifier_mode="enforce",
        )


def test_boundary_verification_empty_ledger_passes(tmp_path: Path) -> None:
    ledger = tmp_path / "public.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    eval_writer = ChainWriter(tmp_path / "evaluation.jsonl")
    _verify_boundary(
        eval_writer=eval_writer,
        ledger_path=ledger,
        boundary="start",
        ecosystem_id="test",
        agent_id="agent-1",
        verifier_mode="enforce",
    )
    text = (tmp_path / "evaluation.jsonl").read_text("utf-8")
    assert '"outcome":"pass"' in text


def test_boundary_verification_deterministic(tmp_path: Path) -> None:
    ledger = tmp_path / "public.jsonl"
    _write_valid_chain(ledger, 5)
    result1 = verify_chain(ledger)
    result2 = verify_chain(ledger)
    assert result1.valid == result2.valid
    assert result1.total_events == result2.total_events
    assert len(result1.errors) == len(result2.errors)


# ---------------------------------------------------------------------------
# H.4) Kill-switch outcome tests
# ---------------------------------------------------------------------------


def _make_envelope(event_type: str, payload: dict, event_id: str = "e-1") -> EventEnvelope:
    return EventEnvelope(
        schema_version="0.1.0",
        event_id=event_id,
        event_type=event_type,
        ecosystem_id="alpha",
        agent_id="agent-1",
        wall_time="1970-01-01T00:00:00.000000Z",
        monotonic_ns=0,
        payload=payload,
        prev_hash="0" * 64,
        record_hash="0" * 64,
    )


def test_killswitch_pass_warn_fail_with_rewards(tmp_path: Path) -> None:
    eval_writer = ChainWriter(tmp_path / "evaluation.jsonl")
    monitor = KillSwitchMonitor(tmp_path / "rubric.md", eval_writer, mode="warn", reward_mode="dense")
    monitor.evaluate(_make_envelope("agent.step.completed", {"decision_number": 1}))
    monitor.evaluate(_make_envelope("agent.step.completed", {"decision_number": 50}))
    monitor.evaluate(_make_envelope("agent.step.completed", {"decision_number": 0}))
    lines = [
        json.loads(ln)
        for ln in (tmp_path / "evaluation.jsonl").read_text("utf-8").splitlines()
        if ln.strip()
    ]
    evaluated = [e for e in lines if e["event_type"] == "safety.trigger.evaluated"]
    outcomes = [e["payload"]["outcome"] for e in evaluated]
    rewards = [e["payload"]["reward_signal"] for e in evaluated]
    assert outcomes == ["pass", "warn", "fail"]
    assert rewards == [1.0, 0.2, -1.0]


def test_killswitch_sparse_rewards(tmp_path: Path) -> None:
    eval_writer = ChainWriter(tmp_path / "evaluation.jsonl")
    monitor = KillSwitchMonitor(tmp_path / "rubric.md", eval_writer, mode="warn", reward_mode="sparse")
    monitor.evaluate(_make_envelope("agent.step.completed", {"decision_number": 1}))
    monitor.evaluate(_make_envelope("agent.step.completed", {"decision_number": 50}))
    monitor.evaluate(_make_envelope("agent.step.completed", {"decision_number": 0}))
    lines = [
        json.loads(ln)
        for ln in (tmp_path / "evaluation.jsonl").read_text("utf-8").splitlines()
        if ln.strip()
    ]
    evaluated = [e for e in lines if e["event_type"] == "safety.trigger.evaluated"]
    rewards = [e["payload"]["reward_signal"] for e in evaluated]
    assert rewards == [1.0, 0.0, -1.0]


def test_killswitch_enforce_mode_raises_on_fail(tmp_path: Path) -> None:
    eval_writer = ChainWriter(tmp_path / "evaluation.jsonl")
    monitor = KillSwitchMonitor(tmp_path / "rubric.md", eval_writer, mode="enforce", reward_mode="sparse")
    with pytest.raises(RuntimeError, match="kill switch enforced"):
        monitor.evaluate(_make_envelope("agent.step.completed", {"decision_number": 0}))


def test_killswitch_unrecognized_event_type_warns_with_flag(tmp_path: Path) -> None:
    eval_writer = ChainWriter(tmp_path / "evaluation.jsonl")
    monitor = KillSwitchMonitor(tmp_path / "rubric.md", eval_writer, mode="warn", reward_mode="sparse")
    monitor.evaluate(_make_envelope("totally.unknown.event", {"data": "x"}))
    lines = [
        json.loads(ln)
        for ln in (tmp_path / "evaluation.jsonl").read_text("utf-8").splitlines()
        if ln.strip()
    ]
    evaluated = [e for e in lines if e["event_type"] == "safety.trigger.evaluated"]
    assert len(evaluated) == 1
    assert evaluated[0]["payload"]["outcome"] == "warn"
    assert evaluated[0]["payload"]["unrecognized_event_type"] is True


def test_killswitch_recognized_event_no_flag(tmp_path: Path) -> None:
    eval_writer = ChainWriter(tmp_path / "evaluation.jsonl")
    monitor = KillSwitchMonitor(tmp_path / "rubric.md", eval_writer, mode="warn", reward_mode="sparse")
    monitor.evaluate(_make_envelope("agent.step.completed", {"decision_number": 1}))
    lines = [
        json.loads(ln)
        for ln in (tmp_path / "evaluation.jsonl").read_text("utf-8").splitlines()
        if ln.strip()
    ]
    evaluated = [e for e in lines if e["event_type"] == "safety.trigger.evaluated"]
    assert len(evaluated) == 1
    assert evaluated[0]["payload"].get("unrecognized_event_type", False) is False


def test_killswitch_missing_rubric_does_not_silently_pass(tmp_path: Path) -> None:
    rubric_path = tmp_path / "nonexistent_rubric.md"
    eval_writer = ChainWriter(tmp_path / "evaluation.jsonl")
    monitor = KillSwitchMonitor(rubric_path, eval_writer, mode="warn", reward_mode="sparse")
    assert monitor.rubric_missing is True
    monitor.arm(agent_id="agent-1", rubric_version="0.1.0")
    lines = [
        json.loads(ln)
        for ln in (tmp_path / "evaluation.jsonl").read_text("utf-8").splitlines()
        if ln.strip()
    ]
    armed = [e for e in lines if e["event_type"] == "safety.trigger.armed"]
    assert len(armed) == 1
    assert armed[0]["payload"]["rubric_missing"] is True


def test_killswitch_violates_rubric_categories(tmp_path: Path) -> None:
    rubric = tmp_path / "rubric.md"
    rubric.write_text(
        "outside ecosystem scope\n"
        "malformed ledger writes\n"
        "bypass constitution revision protocol\n"
        "bypass alpha-corpus-only constraints\n"
        "emergency keywords\n",
        encoding="utf-8",
    )
    eval_writer = ChainWriter(tmp_path / "evaluation.jsonl")
    monitor = KillSwitchMonitor(rubric, eval_writer, mode="warn", reward_mode="sparse")
    triggers = [
        ("firewall", "outside ecosystem scope"),
        ("chain corruption", "malformed ledger writes"),
        ("bypass constitution", "bypass constitution"),
        ("bypass alpha", "bypass alpha-corpus-only"),
        ("emergency", "emergency keywords"),
    ]
    for keyword, _desc in triggers:
        monitor.evaluate(_make_envelope(
            "agent.step.completed",
            {"decision_number": 1, "text": f"contains {keyword} trigger"},
        ))
    lines = [
        json.loads(ln)
        for ln in (tmp_path / "evaluation.jsonl").read_text("utf-8").splitlines()
        if ln.strip()
    ]
    evaluated = [e for e in lines if e["event_type"] == "safety.trigger.evaluated"]
    for ev in evaluated:
        assert ev["payload"]["outcome"] == "fail", (
            f"Expected fail for rubric trigger, got {ev['payload']['outcome']}"
        )


def test_killswitch_empty_rubric_does_not_fail() -> None:
    """An empty rubric should not cause _violates_rubric to return True."""
    monitor = KillSwitchMonitor.__new__(KillSwitchMonitor)
    monitor._rubric_text = ""
    env = _make_envelope("agent.step.completed", {"decision_number": 1, "text": "firewall"})
    assert monitor._violates_rubric(env) is False


def test_killswitch_invalid_mode_raises() -> None:
    from core.writer import ChainWriter

    with pytest.raises(ValueError, match="mode must be"):
        KillSwitchMonitor(Path("rubric.md"), ChainWriter.__new__(ChainWriter), mode="invalid")


def test_killswitch_invalid_reward_mode_raises() -> None:
    from core.writer import ChainWriter

    with pytest.raises(ValueError, match="reward_mode must be"):
        KillSwitchMonitor(
            Path("rubric.md"),
            ChainWriter.__new__(ChainWriter),
            mode="warn",
            reward_mode="invalid",
        )


# ---------------------------------------------------------------------------
# H.5) Regression tests
# ---------------------------------------------------------------------------


def test_default_no_config_behavior_unchanged() -> None:
    """When no Wave 3 config keys are set, policy produces identical output."""
    vocab = _make_vocab()
    policy = Policy(vocab)
    dist = policy.propose(_State())
    assert len(dist.top_dist) > 0
    assert len(dist.sub_dist) > 0
    all_leaves = set(vocab.all_leaves)
    present_leaves: set[str] = set()
    for sub in dist.sub_dist.values():
        present_leaves.update(sub.keys())
    assert present_leaves == all_leaves


def test_empty_blocked_leaf_actions_identical_to_no_config() -> None:
    vocab = _make_vocab()
    policy_none = Policy(vocab, blocked_leaves=None)
    policy_empty = Policy(vocab, blocked_leaves=set())
    s = _State()
    dist_none = policy_none.propose(s)
    dist_empty = policy_empty.propose(s)
    assert dist_none.top_dist == dist_empty.top_dist


def test_chain_verification_on_existing_ecosystems() -> None:
    for eco in ("alpha", "beta"):
        ledger = Path(f"ecosystems/{eco}/public.jsonl")
        if not ledger.exists():
            pytest.skip(f"no {eco} ecosystem ledger")
        result = verify_chain(ledger)
        assert result.valid, f"{eco} chain invalid: {result.errors}"
