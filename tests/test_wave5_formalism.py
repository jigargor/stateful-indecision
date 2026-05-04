from __future__ import annotations

import random

from agent.decision import _reason_phase, _sample_with_reason_bias


class _Snapshot:
    def __init__(self, *, in_commons: bool, notebook_dup_ratio: float):
        self.in_commons = in_commons
        self.belief_state = {"notebook_dup_ratio": notebook_dup_ratio}


def test_reason_phase_prefers_research_on_high_duplication() -> None:
    snapshot = _Snapshot(in_commons=False, notebook_dup_ratio=0.8)
    suggested, rationale = _reason_phase(snapshot, {"RESEARCH": 0.4, "PRACTICE": 0.6})
    assert suggested == "RESEARCH"
    assert "duplicate ratio" in rationale


def test_sample_with_reason_bias_returns_valid_actions() -> None:
    rng = random.Random(123)
    top_action, sub_action, sample_seed = _sample_with_reason_bias(
        top_dist={"RESEARCH": 0.5, "PRACTICE": 0.5},
        sub_dist={
            "RESEARCH": {"READ": 0.4, "ANALYZE": 0.6},
            "PRACTICE": {"WRITE": 1.0},
        },
        suggested_top_action="RESEARCH",
        rng=rng,
    )
    assert top_action in {"RESEARCH", "PRACTICE"}
    assert sub_action in {"READ", "ANALYZE", "WRITE"}
    assert isinstance(sample_seed, int)
