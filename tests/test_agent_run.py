from __future__ import annotations

import os
import shutil

import pytest

from agent.runner import main
from core.verifier import verify_chain


@pytest.mark.integration
def test_agent_run_integration_with_mock_fallback(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "workspace"
    project_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree("seeds", project_root / "seeds")
    shutil.copytree("corpora", project_root / "corpora")
    shutil.copytree("safety", project_root / "safety")

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    previous_cwd = os.getcwd()
    os.chdir(project_root)
    try:
        main(
            ecosystem_id="alpha",
            agent_id="agent-001",
            model_id="claude-sonnet-4-6-20250514",
            max_decisions=5,
            seed=1234,
        )
    finally:
        os.chdir(previous_cwd)

    public_chain = project_root / "ecosystems" / "alpha" / "public.jsonl"
    notebook_chain = project_root / "ecosystems" / "alpha" / "agents" / "agent-001" / "notebook.jsonl"
    constitution_path = project_root / "ecosystems" / "alpha" / "agents" / "agent-001" / "constitution.md"

    assert verify_chain(public_chain).valid is True
    assert verify_chain(notebook_chain).valid is True
    assert constitution_path.exists()
    constitution_text = constitution_path.read_text(encoding="utf-8")
    assert constitution_text.startswith("---\n")
    assert "\n---\n" in constitution_text
    assert "field_chosen:" in constitution_text

    public_lines = public_chain.read_text(encoding="utf-8").splitlines()
    assert any('"event_type":"agent.decision.taken"' in line for line in public_lines)

    # Agent path should not write to evaluation ledger directly.
    eval_path = project_root / "ecosystems" / "alpha" / "evaluation.jsonl"
    assert eval_path.exists()
    eval_content = eval_path.read_text(encoding="utf-8")
    assert '"event_type":"safety.trigger.armed"' in eval_content
