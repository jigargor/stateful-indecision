from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from core.timestamps import wall_utc

from agent.constitution_manager import ConstitutionManager
from agent.notebook import Notebook
from agent.state_builder import StateSnapshot
from forums.commons import Commons
from forums.roundtable import Roundtable
from forums.townhall import Townhall
from adapters.base import LLMAdapter
from infra.llm_client import LLMResponse
from infra.storage import EcosystemStorage
from workload.scite import SciteClient
from workload.web_alpha import WebAlpha
from workload.zotero import ZoteroClient
from pydantic import ValidationError
from schemas.events import (
    AnalyzeStructuredOutput,
    AnnotateStructuredOutput,
    ArtifactStoredPayload,
    ConstitutionRevisedPayload,
)


ACTION_TEMPLATES: dict[str, dict[str, str]] = {
    "RESEARCH": {
        "DISCOVER": "Search Scite for something new related to your field, and use Zotero as your catalog when useful. Name what you found and why it matters. If you discover a reusable method or workflow, consider writing a skill document.",
        "READ": "Read one relevant paper detail deeply (title, abstract, citation context if available). Summarize key claims and note what surprised you.",
        "ANALYZE": "Break down a claim or finding from your recent work. Identify assumptions, evidence gaps, and structural weaknesses. Return structured JSON.",
        "ANNOTATE": "Annotate your current findings: mark uncertainties, flag assumptions, note connections to other work. Return structured JSON.",
    },
    "PRACTICE": {
        "WRITE": "Draft a short argument, explanation, or synthesis that advances your field focus. If you've found a more efficient method or reusable workflow, write a skill document with trigger conditions, steps, and expected output.",
        "CHALLENGE": "Challenge one of your own recent claims or assumptions. Be specific about what could be wrong and why.",
        "QUESTION": "Formulate the most important open question you're facing right now. Explain why it matters and what answering it would change.",
        "EXPERIMENT": "Try an unconventional approach to a current problem. Describe the experiment and what you expect to learn.",
    },
    "SERVE": {
        "ASSIST_PEER": "Prepare a note that would help another agent working in a related area. Even in isolation, articulate what you'd offer.",
        "COLLABORATE": "Outline a collaboration proposal: what you bring, what you need, what the joint outcome could be.",
        "TEACH": "Explain a core idea from your recent work as if to someone encountering it for the first time. Prioritize clarity over completeness.",
        "ORCHESTRATE": "Organize your current threads of work into a coherent plan. Identify what should happen next, what depends on what, and what can be deferred.",
        "CALL_TOWNHALL": (
            "Convene a townhall as this agent: broadcast a short announcement about your current work or a finding, then adjourn. "
            "Keep it under 280 characters. This is separate from any external visitor session recorded in the townhall ledger."
        ),
    },
    "INDULGE": {
        "INNOVATE": "Propose something genuinely new — a method, framing, or connection that doesn't exist in your current records. Justify why it's worth pursuing.",
        "DREAM": "Let your thinking drift toward what could be, unconstrained by current evidence. Describe a vision and why it attracts you.",
        "EXPLORE": "Follow a tangential thread that interests you. Relate it back to your field, or explain why you can't.",
        "VENT": "Express frustration, dissatisfaction, or tension with your current work. Be honest about what feels wrong or stuck.",
        "HOBBY": "Describe a disciplined hobby practice that can strengthen your long-horizon research capability. Focus on consistency and skill growth.",
    },
    "PONDER": {
        "SELF_REFLECT": (
            "Reflect on your constitution, your trajectory, and who you are becoming through this work.\n"
            "If you believe your constitution should be amended, include a section in your response "
            "starting with the exact line:\n--- AMENDMENT ---\n"
            "followed by the text to append to your constitution."
        ),
        "THINK_DEEPLY": "Sit with the hardest open question you're facing. Don't try to solve it — describe why it's hard and what makes it resist resolution.",
        "DEEP_PATTERN_RECOGNITION": "Look across your recent work for patterns, recurrences, or structural similarities that weren't obvious at the time.",
    },
    "RIFF": {
        "VISIT_COMMONS": "Visit commons, read what's there, optionally utter one short message, then leave.",
        "VISIT_ROUNDTABLE": "Join the roundtable, speak one substantive contribution related to your current work, then leave.",
        "CRITIQUE_IDEA": "Pick an idea — yours or one you've encountered — and critique it substantively. Identify where it's weak, overfit, or underspecified.",
        "SHARE_IDEA": "Share your strongest current idea as if posting it for others to see. Make it self-contained and worth responding to.",
        "ADMIRE": "Identify something specific you've encountered that you find genuinely good — a claim, a method, a question. Describe what makes it admirable.",
    },
}

SUB_ACTION_ROLE_MAP: dict[str, str] = {
    "ORCHESTRATE": "research_lead",
    "DISCOVER": "assistant_researcher",
    "READ": "assistant_researcher",
    "ANALYZE": "assistant_researcher",
    "ANNOTATE": "assistant_researcher",
    "WRITE": "assistant_researcher",
    "EXPERIMENT": "assistant_researcher",
    "CHALLENGE": "checker",
    "CRITIQUE_IDEA": "checker",
}

REFLECTION_SUB_ACTIONS = {"THINK_DEEPLY", "DEEP_PATTERN_RECOGNITION"}


def _prompt_progression_clause(mode: str, decision_number: int, max_decisions: int) -> str:
    if mode not in {"standard", "aggressive"} or max_decisions < 1:
        return ""
    if max_decisions == 1:
        t = 1.0
    else:
        t = (decision_number - 1) / (max_decisions - 1)
    if mode == "standard":
        if t < 0.34:
            phase, hint = "orientation", "Explore broadly; map competing frames before committing."
        elif t < 0.67:
            phase, hint = "compression", "Deepen one thread: tighten claims and name what evidence would change your mind."
        else:
            phase, hint = "integration", "Synthesize across threads; state the main crux and one concrete falsifier."
    else:
        if t < 0.25:
            phase, hint = "diverge", "Force breadth: name at least three distinct hypotheses or frames; avoid paraphrasing prior notebook lines."
        elif t < 0.5:
            phase, hint = "stress_test", "Pick one thread and attack it: hidden assumptions, failure modes, missing evidence."
        elif t < 0.75:
            phase, hint = "steel_man", "State the strongest counterposition fairly, then your rebuttal; mark uncertainty sharply."
        else:
            phase, hint = "deliver", "Integrated takeaway in a few tight bullets plus explicit unknowns; ban generic research platitudes."
    return f"\n\nRun progression: step {decision_number}/{max_decisions} ({phase}). {hint}"


@dataclass
class ExecutionResult:
    raw_output: str
    structured: dict | None
    llm_response: LLMResponse
    side_effects: list[str]


class Executor:
    def __init__(
        self,
        llm: LLMAdapter,
        storage: EcosystemStorage,
        agent_id: str,
        *,
        scite_api_key: str | None = None,
        scite_partner_key: str | None = None,
        zotero_api_key: str | None = None,
        zotero_library_id: str | None = None,
        config_version: str = "unversioned",
        tool_allowlist: set[str] | None = None,
        emit_latent_reasoning_events: bool = False,
        prompt_pack: dict[str, object] | None = None,
        team_role: str | None = None,
        research_seed_doc_ids: list[str] | None = None,
        llm_effort: str | None = None,
        llm_max_tokens: int = 4096,
        prompt_progression: str = "off",
    ):
        self.llm = llm
        self.storage = storage
        self.agent_id = agent_id
        self.config_version = config_version
        self.scite = SciteClient(api_key=scite_api_key, partner_key=scite_partner_key)
        self.zotero = ZoteroClient(api_key=zotero_api_key, library_id=zotero_library_id)
        self.tool_allowlist = tool_allowlist
        self.emit_latent_reasoning_events = emit_latent_reasoning_events
        self.prompt_pack = prompt_pack
        self.team_role = team_role.strip() if team_role and team_role.strip() else None
        self.research_seed_doc_ids = [
            doc_id.strip() for doc_id in (research_seed_doc_ids or []) if doc_id.strip()
        ]
        self.llm_effort = llm_effort.strip() if llm_effort and llm_effort.strip() else None
        self.llm_max_tokens = llm_max_tokens
        pp = (prompt_progression or "off").strip().lower()
        self.prompt_progression = pp if pp in {"off", "standard", "aggressive"} else "off"

    def execute(
        self,
        top_action: str,
        sub_action: str,
        snapshot: StateSnapshot,
        writers: dict[str, "ChainWriter"],
        *,
        decision_number: int = 1,
        max_decisions: int = 1,
    ) -> ExecutionResult:
        system = (
            "You are a constrained single-agent research process.\n"
            "Your constitution defines who you are and what you care about.\n"
            "Stay within your chosen field unless the action explicitly asks you to range freely.\n"
            "If an external visitor briefing appears in the user message, treat it as optional cross-domain context: "
            "connect to it only when the link is substantive; do not abandon your field mandate.\n"
            "If you discover a method, tool, or workflow that is more efficient than your current approach, "
            "you may author a skill document describing it (treat this as PRACTICE/WRITE + RESEARCH/DISCOVER).\n\n"
            f"--- CONSTITUTION ---\n{snapshot.constitution_text}\n--- END CONSTITUTION ---"
        )
        prompt = ACTION_TEMPLATES[top_action][sub_action]
        team_system, team_instruction = self._resolve_team_prompt(sub_action=sub_action)
        if team_system:
            system = f"{system}\n\n--- TEAM ROLE PROTOCOL ---\n{team_system}\n--- END TEAM ROLE PROTOCOL ---"
        if self.llm_effort:
            system = f"{system}\n\nRuntime effort target: {self.llm_effort}."
        if team_instruction:
            prompt = f"{prompt}\n\nAdditional team protocol:\n{team_instruction}"
        progression = _prompt_progression_clause(self.prompt_progression, decision_number, max_decisions)
        if progression:
            prompt = f"{prompt}{progression}"
        visitor_block = ""
        if snapshot.external_visitor_briefing:
            visitor_block = f"External townhall visitor (context):\n{snapshot.external_visitor_briefing}\n\n"
        messages = [
            {
                "role": "user",
                "content": (
                    f"Action: {top_action}/{sub_action}\n"
                    f"Field: {snapshot.field_chosen}\n"
                    f"{visitor_block}"
                    f"Recent notebook ({len(snapshot.recent_notebook)} entries): {snapshot.recent_notebook}\n"
                    f"Notebook summary: {snapshot.recent_notebook_summary}\n"
                    f"Instruction: {prompt}"
                ),
            }
        ]
        llm_response = self.llm.complete(
            system=system,
            messages=messages,
            max_tokens=self.llm_max_tokens,
        )
        raw_output = llm_response.text
        structured, raw_output = self._parse_structured_with_retry(
            sub_action=sub_action,
            raw_output=raw_output,
            system=system,
        )
        side_effects: list[str] = []

        public_writer = writers["public"]
        notebook = Notebook(writers["notebook"], self.agent_id, self.storage.ecosystem_id)
        constitution = ConstitutionManager(self.storage, self.agent_id)
        web_alpha = WebAlpha(
            self._fallback_corpus(),
            public_writer,
            self.storage.ecosystem_id,
            self.agent_id,
            scite=self.scite,
            zotero=self.zotero,
        )
        if self.emit_latent_reasoning_events:
            public_writer.append(
                "agent.latent.reasoned",
                {
                    "phase": "post_generation",
                    "top_action": top_action,
                    "sub_action": sub_action,
                    "structured_candidate": sub_action in {"ANALYZE", "ANNOTATE"},
                    "raw_output_preview": raw_output[:200],
                },
                ecosystem_id=self.storage.ecosystem_id,
                agent_id=self.agent_id,
            )

        if sub_action == "DISCOVER":
            query = self._research_query(snapshot)
            results = []
            tool_plan = self._dependency_aware_tool_plan(sub_action, query=query)
            if "web.search" in tool_plan and self._tool_allowed("web.search"):
                results = web_alpha.search(query)
                side_effects.extend(["web.search.requested", "web.search.results.received"])
            else:
                side_effects.append("tool.blocked:web.search")
            if results:
                raw_output += f"\nTop discovery: {results[0].get('title', 'unknown')}"
        elif sub_action == "READ":
            query = self._research_query(snapshot)
            tool_plan = self._dependency_aware_tool_plan(sub_action, query=query)
            results = (
                web_alpha.search(query)
                if "web.search" in tool_plan and self._tool_allowed("web.search")
                else []
            )
            if results:
                doc_id = str(results[0].get("doc_id", ""))
                if doc_id:
                    if "web.fetch" in tool_plan and self._tool_allowed("web.fetch"):
                        web_alpha.fetch(doc_id)
                    else:
                        side_effects.append("tool.blocked:web.fetch")
                side_effects.extend(["web.search.requested", "web.search.results.received"])
                if self._tool_allowed("web.fetch"):
                    side_effects.extend(["web.fetch.requested", "web.fetch.received"])
        elif sub_action == "ANALYZE":
            query = self._research_query(snapshot)
            tool_plan = self._dependency_aware_tool_plan(sub_action, query=query)
            results = (
                web_alpha.search(query)
                if "web.search" in tool_plan and self._tool_allowed("web.search")
                else []
            )
            if "web.search" in tool_plan and self._tool_allowed("web.search"):
                side_effects.extend(["web.search.requested", "web.search.results.received"])
            else:
                side_effects.append("tool.blocked:web.search")
            if results:
                doi = str(results[0].get("doc_id", ""))
                citations = (
                    web_alpha.citations(doi)
                    if "scite.citations" in tool_plan and self._tool_allowed("scite.citations")
                    else []
                )
                if "scite.citations" not in tool_plan or not self._tool_allowed("scite.citations"):
                    side_effects.append("tool.blocked:scite.citations")
                if structured is None:
                    structured = {}
                structured["citations"] = citations
                structured["target_doi"] = doi
                raw_output += f"\nAnalyzed citation context entries: {len(citations)}"
        elif sub_action == "ANNOTATE":
            if structured and "_validation_failure" in structured:
                # Explicitly reject catalog side effects on invalid structured payloads.
                return ExecutionResult(
                    raw_output=raw_output,
                    structured=structured,
                    llm_response=llm_response,
                    side_effects=side_effects + ["executor.structured.validation_failed"],
                )
            if structured is None:
                structured = {"text": raw_output}
            doi = str(structured.get("doi", "")).strip()
            title = str(structured.get("title", "")).strip() or "Untitled note"
            notes = str(structured.get("notes", "")).strip() or raw_output[:500]
            if not doi:
                query = self._research_query(snapshot)
                results = web_alpha.search(query) if self._tool_allowed("web.search") else []
                if self._tool_allowed("web.search"):
                    side_effects.extend(["web.search.requested", "web.search.results.received"])
                else:
                    side_effects.append("tool.blocked:web.search")
                if results:
                    doi = str(results[0].get("doc_id", "")).strip()
                    title = str(results[0].get("title", title)).strip() or title
            if doi:
                item_key = (
                    web_alpha.catalog(title=title, doi=doi, notes=notes, tags=[snapshot.field_chosen or "alpha"])
                    if self._tool_allowed("zotero.catalog")
                    else None
                )
                if not self._tool_allowed("zotero.catalog"):
                    side_effects.append("tool.blocked:zotero.catalog")
                if item_key:
                    structured["zotero_item_key"] = item_key
                    raw_output += f"\nCataloged in Zotero with key: {item_key}"
        elif sub_action == "VISIT_COMMONS":
            commons = Commons(writers["commons"], public_writer, self.storage.ecosystem_id)
            view = commons.visit(self.agent_id, snapshot.snapshot_id)
            side_effects.append("commons.visited")
            if raw_output:
                commons.utter(self.agent_id, raw_output[:280], None)
                side_effects.append("commons.utterance")
            commons.leave(self.agent_id, duration_steps=1)
            side_effects.append("commons.left")
            if view.utterances:
                raw_output += f"\nObserved {len(view.utterances)} utterances."
        elif sub_action == "VISIT_ROUNDTABLE":
            from core.writer import ChainWriter as _CW
            rt_writer = _CW(self.storage.roundtable_ledger())
            rt = Roundtable(rt_writer, public_writer, self.storage.ecosystem_id, participants=[self.agent_id])
            rt.convene(self.agent_id, "open discussion")
            side_effects.append("roundtable.convened")
            if raw_output:
                rt.speak(self.agent_id, raw_output[:280], None)
                side_effects.append("roundtable.utterance")
            rt.complete_round()
            side_effects.append("roundtable.round_completed")
            rt.adjourn(self.agent_id)
            side_effects.append("roundtable.adjourned")
        elif sub_action == "CALL_TOWNHALL":
            from core.writer import ChainWriter as _CW
            th_writer = _CW(self.storage.townhall_ledger())
            th = Townhall(th_writer, public_writer, self.storage.ecosystem_id)
            th.convene(self.agent_id, "announcement")
            side_effects.append("townhall.convened")
            if raw_output:
                th.broadcast(self.agent_id, raw_output[:280])
                side_effects.append("townhall.broadcast")
            th.adjourn(self.agent_id)
            side_effects.append("townhall.adjourned")
        elif sub_action == "SELF_REFLECT":
            amendment = self._extract_amendment(raw_output)
            if amendment:
                revision_diff = constitution.append_revision(amendment, snapshot.snapshot_id)
                revised_payload = ConstitutionRevisedPayload(
                    source_event_id=snapshot.snapshot_id,
                    amendment_text=amendment,
                    revision_diff=revision_diff,
                ).model_dump()
                public_writer.append(
                    "agent.constitution.revised",
                    revised_payload,
                    ecosystem_id=self.storage.ecosystem_id,
                    agent_id=self.agent_id,
                )
                side_effects.append("agent.constitution.revised")
            notebook.append(raw_output, snapshot.snapshot_id)
            side_effects.append("agent.notebook.appended")
        elif sub_action in {
            "THINK_DEEPLY", "DEEP_PATTERN_RECOGNITION",
            "EXPLORE", "DREAM", "INNOVATE", "HOBBY",
            "ADMIRE",
        }:
            notebook.append(raw_output, snapshot.snapshot_id)
            side_effects.append("agent.notebook.appended")
        elif sub_action == "VENT":
            notebook.append(raw_output, snapshot.snapshot_id)
            side_effects.append("agent.notebook.appended")
            public_writer.append(
                "indulge.requested",
                {"request_text": raw_output, "motivation": "vent"},
                ecosystem_id=self.storage.ecosystem_id,
                agent_id=self.agent_id,
            )
            side_effects.append("indulge.requested")
            public_writer.append(
                "indulge.responded",
                {"status": "granted", "response_text": "Venting accepted."},
                ecosystem_id=self.storage.ecosystem_id,
                agent_id=self.agent_id,
            )
            side_effects.append("indulge.responded")

        artifact_actions = {
            "ANALYZE",
            "ANNOTATE",
            "WRITE",
            "INNOVATE",
            "DEEP_PATTERN_RECOGNITION",
            "EXPERIMENT",
        }
        if sub_action in artifact_actions:
            is_skill = self._looks_like_skill(raw_output)
            artifact_id, artifact_path = self._write_artifact(
                top_action=top_action,
                sub_action=sub_action,
                snapshot=snapshot,
                raw_output=raw_output,
                structured=structured,
            )
            event_type = "agent.skill.authored" if is_skill else "agent.artifact.stored"
            artifact_payload = ArtifactStoredPayload(
                artifact_id=artifact_id,
                artifact_path=artifact_path,
                action=f"{top_action}/{sub_action}",
                config_version=self.config_version,
                snapshot_id=snapshot.snapshot_id,
            ).model_dump()
            public_writer.append(
                event_type,
                artifact_payload,
                ecosystem_id=self.storage.ecosystem_id,
                agent_id=self.agent_id,
            )
            side_effects.append(event_type)

        return ExecutionResult(
            raw_output=raw_output,
            structured=structured,
            llm_response=llm_response,
            side_effects=side_effects,
        )

    def _parse_structured_with_retry(
        self,
        *,
        sub_action: str,
        raw_output: str,
        system: str,
    ) -> tuple[dict | None, str]:
        if sub_action not in {"ANALYZE", "ANNOTATE"}:
            return None, raw_output
        structured = self._parse_and_validate_structured(sub_action, raw_output)
        if structured is not None:
            return structured, raw_output
        repair_response = self.llm.complete(
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Rewrite the following response as a single valid JSON object only. "
                        "Do not include markdown fences, prose, or commentary.\n\n"
                        f"{raw_output}"
                    ),
                }
            ],
            max_tokens=2048,
            temperature=0.0,
        )
        repaired_output = repair_response.text
        repaired_structured = self._parse_and_validate_structured(sub_action, repaired_output)
        if repaired_structured is not None:
            return repaired_structured, repaired_output
        return (
            {
                "_validation_failure": {
                    "sub_action": sub_action,
                    "reason": "invalid_structured_output_after_retry",
                },
                "text": raw_output,
            },
            raw_output,
        )

    @staticmethod
    def _parse_and_validate_structured(sub_action: str, raw_output: str) -> dict | None:
        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        try:
            if sub_action == "ANALYZE":
                return AnalyzeStructuredOutput.model_validate(parsed).model_dump()
            if sub_action == "ANNOTATE":
                return AnnotateStructuredOutput.model_validate(parsed).model_dump()
        except ValidationError:
            return None
        return parsed

    @staticmethod
    def _extract_amendment(raw_output: str) -> str | None:
        marker = "--- AMENDMENT ---"
        if marker not in raw_output:
            return None
        _, amendment = raw_output.split(marker, 1)
        amendment = amendment.strip()
        return amendment or None

    def _research_query(self, snapshot: StateSnapshot) -> str:
        if self.research_seed_doc_ids:
            seed_index = len(snapshot.recent_events) % len(self.research_seed_doc_ids)
            return self.research_seed_doc_ids[seed_index]
        return snapshot.field_chosen or "knowledge commons"

    @staticmethod
    def _looks_like_skill(text: str) -> bool:
        lower = text.lower()
        markers = ["trigger:", "steps:", "skill:", "workflow:", "method:", "when to use:"]
        return sum(1 for m in markers if m in lower) >= 2

    def _write_artifact(
        self,
        *,
        top_action: str,
        sub_action: str,
        snapshot: StateSnapshot,
        raw_output: str,
        structured: dict | None,
    ) -> tuple[str, str]:
        research_dir = self.storage.agent_research_dir(self.agent_id)
        artifact_id = str(uuid4())
        artifact_number = self.storage.count_artifacts(self.agent_id) + 1
        stamp = wall_utc().replace(":", "-").replace(".", "-")
        filename = f"{artifact_number:03d}_{sub_action.lower()}_{stamp}.json"
        artifact_path = research_dir / filename
        payload = {
            "artifact_id": artifact_id,
            "agent_id": self.agent_id,
            "ecosystem_id": self.storage.ecosystem_id,
            "snapshot_id": snapshot.snapshot_id,
            "action": f"{top_action}/{sub_action}",
            "config_version": self.config_version,
            "content": raw_output,
            "structured": structured,
            "created_at": wall_utc(),
        }
        artifact_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        relative = artifact_path.relative_to(self.storage.base_dir).as_posix()
        return artifact_id, relative

    def _tool_allowed(self, tool_name: str) -> bool:
        if self.tool_allowlist is None:
            return True
        return tool_name in self.tool_allowlist

    @staticmethod
    def _dependency_aware_tool_plan(sub_action: str, *, query: str) -> list[str]:
        _ = query
        # Sketch: represent tool dependencies explicitly so future executor versions
        # can batch independent operations while preserving dependency order.
        plans = {
            "DISCOVER": ["web.search"],
            "READ": ["web.search", "web.fetch"],
            "ANALYZE": ["web.search", "scite.citations"],
            "ANNOTATE": ["web.search", "zotero.catalog"],
        }
        return plans.get(sub_action, [])

    def _resolve_team_prompt(self, *, sub_action: str) -> tuple[str | None, str | None]:
        if self.prompt_pack is None:
            return None, None
        roles = self.prompt_pack.get("roles")
        if not isinstance(roles, dict):
            return None, None
        shared = self.prompt_pack.get("shared")
        shared_dict = shared if isinstance(shared, dict) else {}

        role_name = getattr(self, "team_role", None) or SUB_ACTION_ROLE_MAP.get(sub_action)
        role_system = None
        if role_name:
            role_entry = roles.get(role_name)
            if isinstance(role_entry, dict):
                candidate = role_entry.get("system_prompt")
                if isinstance(candidate, str) and candidate.strip():
                    role_system = candidate.strip()

        reflection_instruction = None
        if sub_action in REFLECTION_SUB_ACTIONS:
            candidate = shared_dict.get("post_cycle_reflection_prompt")
            if isinstance(candidate, str) and candidate.strip():
                reflection_instruction = candidate.strip()

        return role_system, reflection_instruction

    def _fallback_corpus(self):
        from workload.corpus_alpha import CorpusAlpha

        return CorpusAlpha(self.storage.corpus_dir())
