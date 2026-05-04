from __future__ import annotations

import json
from pathlib import Path

from schemas.events import (
    ActionExecutedPayload,
    AgentStateSnapshottedPayload,
    AnalyzeStructuredOutput,
    AnnotateStructuredOutput,
    ArtifactStoredPayload,
    ConstitutionRevisedPayload,
    DecisionProposedPayload,
    DecisionTakenPayload,
    NotebookPayload,
)


SCHEMA_MODELS = {
    "agent-state-snapshotted-payload": AgentStateSnapshottedPayload,
    "decision-proposed-payload": DecisionProposedPayload,
    "decision-taken-payload": DecisionTakenPayload,
    "action-executed-payload": ActionExecutedPayload,
    "notebook-payload": NotebookPayload,
    "constitution-revised-payload": ConstitutionRevisedPayload,
    "artifact-stored-payload": ArtifactStoredPayload,
    "analyze-structured-output": AnalyzeStructuredOutput,
    "annotate-structured-output": AnnotateStructuredOutput,
}


def export_schemas(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for schema_name, model in SCHEMA_MODELS.items():
        path = output_dir / f"{schema_name}.schema.json"
        schema = model.model_json_schema()
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main() -> None:
    output_dir = Path("schemas/generated")
    written = export_schemas(output_dir)
    print(f"Exported {len(written)} schema files to {output_dir.resolve()}")
    for path in written:
        print(f"  - {path.as_posix()}")


if __name__ == "__main__":
    main()
