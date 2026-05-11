from __future__ import annotations

import json
from pathlib import Path

from schemas.events import (
    ActionExecutedPayload,
    AgentErrorPayload,
    AgentInstantiatedPayload,
    AgentShutdownPayload,
    AgentStateSnapshottedPayload,
    AnalyzeStructuredOutput,
    AnnotateStructuredOutput,
    ArtifactStoredPayload,
    CheckerVerdictPayload,
    ConstitutionRevisedPayload,
    DecisionProposedPayload,
    DecisionTakenPayload,
    FieldChosenPayload,
    FieldOfferedPayload,
    ForumLeftPayload,
    ForumUtterancePayload,
    ForumVisitedPayload,
    HandoffPayload,
    IndulgeRequestedPayload,
    IndulgeRespondedPayload,
    LatentReasonedPayload,
    NotebookPayload,
    PolicyMasksAppliedPayload,
    RoundtableAdjournedPayload,
    RoundtableConvenedPayload,
    RoundtableRoundCompletedPayload,
    RunCompletedPayload,
    SafetyTriggerArmedPayload,
    SafetyTriggerEvaluatedPayload,
    SharedKnowledgeContextUsedPayload,
    SharedKnowledgeRetrievalAllowedPayload,
    SharedKnowledgeRetrievalDeniedPayload,
    ToolAllowlistAppliedPayload,
    TownhallAdjournedPayload,
    TownhallBroadcastPayload,
    TownhallConvenedPayload,
    TownhallResponsePayload,
    VerifierBoundaryCheckedPayload,
)


SCHEMA_MODELS = {
    "agent-state-snapshotted-payload": AgentStateSnapshottedPayload,
    "decision-proposed-payload": DecisionProposedPayload,
    "decision-taken-payload": DecisionTakenPayload,
    "action-executed-payload": ActionExecutedPayload,
    "latent-reasoned-payload": LatentReasonedPayload,
    "notebook-payload": NotebookPayload,
    "constitution-revised-payload": ConstitutionRevisedPayload,
    "artifact-stored-payload": ArtifactStoredPayload,
    "run-completed-payload": RunCompletedPayload,
    "safety-trigger-armed-payload": SafetyTriggerArmedPayload,
    "safety-trigger-evaluated-payload": SafetyTriggerEvaluatedPayload,
    "analyze-structured-output": AnalyzeStructuredOutput,
    "annotate-structured-output": AnnotateStructuredOutput,
    "indulge-requested-payload": IndulgeRequestedPayload,
    "indulge-responded-payload": IndulgeRespondedPayload,
    "agent-instantiated-payload": AgentInstantiatedPayload,
    "field-offered-payload": FieldOfferedPayload,
    "field-chosen-payload": FieldChosenPayload,
    "agent-shutdown-payload": AgentShutdownPayload,
    "agent-error-payload": AgentErrorPayload,
    "forum-visited-payload": ForumVisitedPayload,
    "forum-utterance-payload": ForumUtterancePayload,
    "forum-left-payload": ForumLeftPayload,
    "townhall-convened-payload": TownhallConvenedPayload,
    "townhall-broadcast-payload": TownhallBroadcastPayload,
    "townhall-response-payload": TownhallResponsePayload,
    "townhall-adjourned-payload": TownhallAdjournedPayload,
    "roundtable-convened-payload": RoundtableConvenedPayload,
    "roundtable-round-completed-payload": RoundtableRoundCompletedPayload,
    "roundtable-adjourned-payload": RoundtableAdjournedPayload,
    "policy-masks-applied-payload": PolicyMasksAppliedPayload,
    "tool-allowlist-applied-payload": ToolAllowlistAppliedPayload,
    "verifier-boundary-checked-payload": VerifierBoundaryCheckedPayload,
    "shared-knowledge-retrieval-allowed-payload": SharedKnowledgeRetrievalAllowedPayload,
    "shared-knowledge-retrieval-denied-payload": SharedKnowledgeRetrievalDeniedPayload,
    "shared-knowledge-context-used-payload": SharedKnowledgeContextUsedPayload,
    "handoff-payload": HandoffPayload,
    "checker-verdict-payload": CheckerVerdictPayload,
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
