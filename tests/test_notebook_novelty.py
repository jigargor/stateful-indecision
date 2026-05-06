from __future__ import annotations

import json
from pathlib import Path

from tools.notebook_novelty import analyze_ecosystem, export_bundle, _overlap_fraction, _ngram_set


def test_overlap_high_when_notebook_repeats_source() -> None:
    source = "the quick brown fox jumps over the lazy dog" * 3
    grams = _ngram_set(source, 12)
    notebook = "THE QUICK BROWN FOX"  # overlaps after normalize
    assert _overlap_fraction(notebook, grams, 12) > 0.3


def test_analyze_ecosystem_and_export(tmp_path: Path) -> None:
    base = tmp_path / "proj"
    (base / "corpora" / "alpha").mkdir(parents=True)
    (base / "corpora" / "alpha" / "seed.md").write_text(
        "alpha corpus uniquephraseone two three four five six",
        encoding="utf-8",
    )
    agent = base / "ecosystems" / "alpha" / "agents" / "a1"
    agent.mkdir(parents=True)
    nb = agent / "notebook.jsonl"
    ev = {
        "event_type": "agent.notebook.appended",
        "event_id": "n1",
        "wall_time": "2026-01-01T00:00:00Z",
        "agent_id": "a1",
        "payload": {
            "text": "novelthought xyz123 not in corpus at all",
            "ref_decision_id": "d1",
            "fingerprint": "fp1",
        },
    }
    nb.write_text(json.dumps(ev) + "\n", encoding="utf-8")

    report = analyze_ecosystem(
        ecosystem_id="alpha",
        base_dir=base,
        ngram=10,
        include_executed_raw=False,
        executed_raw_max_chars=1000,
    )
    assert report["corpus_chars"] > 0
    assert report["entries"] and report["entries"][0]["novelty_estimate"] > 0.5

    out = tmp_path / "share"
    export_bundle(report, out)
    assert (out / "metrics.json").exists()
    assert (out / "notebooks.jsonl").exists()
    assert "novelty" in (out / "NARRATIVE_STUB.md").read_text(encoding="utf-8").lower()
