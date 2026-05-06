from __future__ import annotations

from pathlib import Path

from agent.executor import _prompt_progression_clause
from agent.state_builder import StateBuilder
from core.writer import ChainWriter
from forums.townhall import Townhall


def test_progression_off_is_empty() -> None:
    assert _prompt_progression_clause("off", 3, 10) == ""


def test_progression_aggressive_increases_with_step() -> None:
    early = _prompt_progression_clause("aggressive", 1, 20)
    late = _prompt_progression_clause("aggressive", 20, 20)
    assert "step 1/20" in early
    assert "diverge" in early
    assert "step 20/20" in late
    assert "deliver" in late


def test_latest_external_visitor_briefing_from_ledger(tmp_path: Path) -> None:
    th_path = tmp_path / "townhall.jsonl"
    pub_path = tmp_path / "public.jsonl"
    th = Townhall(ChainWriter(th_path), ChainWriter(pub_path), "alpha")
    th.convene(
        "expert-urban-systems",
        "Transit topology and rumor propagation",
        session_kind="external_visitor",
        tangential_bridge="Spatial coupling as a metaphor for information bottlenecks.",
    )
    th.broadcast("expert-urban-systems", "Short visitor note for the room.")
    th.adjourn("expert-urban-systems")

    text = StateBuilder._latest_external_visitor_briefing(th_path)
    assert text is not None
    assert "Transit topology" in text
    assert "Tangential bridge" in text
    assert "Short visitor note" in text


def test_visitor_briefing_prefers_latest_external_session(tmp_path: Path) -> None:
    th_path = tmp_path / "townhall.jsonl"
    pub_path = tmp_path / "public.jsonl"
    th = Townhall(ChainWriter(th_path), ChainWriter(pub_path), "alpha")
    th.convene("a1", "older topic", session_kind="external_visitor", tangential_bridge="old")
    th.broadcast("a1", "old brief")
    th.adjourn("a1")
    th.convene("a2", "newer topic", session_kind="external_visitor", tangential_bridge="new")
    th.broadcast("a2", "new brief")
    th.adjourn("a2")

    text = StateBuilder._latest_external_visitor_briefing(th_path)
    assert text is not None
    assert "newer topic" in text
    assert "new brief" in text
    assert "older topic" not in text
