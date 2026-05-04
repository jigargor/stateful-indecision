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


ACTION_TEMPLATES: dict[str, dict[str, str]] = {
    "RESEARCH": {
        "DISCOVER": "Search Scite for something new related to your field, and use Zotero as your catalog when useful. Name what you found and why it matters.",
        "READ": "Read one relevant paper detail deeply (title, abstract, citation context if available). Summarize key claims and note what surprised you.",
        "ANALYZE": "Break down a claim or finding from your recent work. Identify assumptions, evidence gaps, and structural weaknesses. Return structured JSON.",
        "ANNOTATE": "Annotate your current findings: mark uncertainties, flag assumptions, note connections to other work. Return structured JSON.",
    },
    "PRACTICE": {
        "WRITE": "Draft a short argument, explanation, or synthesis that advances your field focus.",
        "CHALLENGE": "Challenge one of your own recent claims or assumptions. Be specific about what could be wrong and why.",
        "QUESTION": "Formulate the most important open question you're facing right now. Explain why it matters and what answering it would change.",
        "EXPERIMENT": "Try an unconventional approach to a current problem. Describe the experiment and what you expect to learn.",
    },
    "SERVE": {
        "ASSIST_PEER": "Prepare a note that would help another agent working in a related area. Even in isolation, articulate what you'd offer.",
        "COLLABORATE": "Outline a collaboration proposal: what you bring, what you need, what the joint outcome could be.",
        "TEACH": "Explain a core idea from your recent work as if to someone encountering it for the first time. Prioritize clarity over completeness.",
        "ORCHESTRATE": "Organize your current threads of work into a coherent plan. Identify what should happen next, what depends on what, and what can be deferred.",
        "CALL_TOWNHALL": "Convene a townhall: broadcast a short announcement about your current work or a finding, then adjourn. Keep it under 280 characters.",
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
    ):
        self.llm = llm
        self.storage = storage
        self.agent_id = agent_id
        self.config_version = config_version
        self.scite = SciteClient(api_key=scite_api_key, partner_key=scite_partner_key)
        self.zotero = ZoteroClient(api_key=zotero_api_key, library_id=zotero_library_id)

    def execute(
        self,
        top_action: str,
        sub_action: str,
        snapshot: StateSnapshot,
        writers: dict[str, "ChainWriter"],
    ) -> ExecutionResult:
        system = "You are a constrained single-agent research process in v1."
        prompt = ACTION_TEMPLATES[top_action][sub_action]
        messages = [
            {
                "role": "user",
                "content": (
                    f"Action: {top_action}/{sub_action}\n"
                    f"Field: {snapshot.field_chosen}\n"
                    f"Recent notebook: {snapshot.recent_notebook}\n"
                    f"Instruction: {prompt}"
                ),
            }
        ]
        llm_response = self.llm.complete(system=system, messages=messages)
        raw_output = llm_response.text
        structured = self._parse_structured(sub_action, raw_output)
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

        if sub_action == "DISCOVER":
            query = self._research_query(snapshot)
            results = web_alpha.search(query)
            side_effects.extend(["web.search.requested", "web.search.results.received"])
            if results:
                raw_output += f"\nTop discovery: {results[0].get('title', 'unknown')}"
        elif sub_action == "READ":
            query = self._research_query(snapshot)
            results = web_alpha.search(query)
            if results:
                doc_id = str(results[0].get("doc_id", ""))
                if doc_id:
                    web_alpha.fetch(doc_id)
                side_effects.extend(["web.search.requested", "web.search.results.received"])
                side_effects.extend(["web.fetch.requested", "web.fetch.received"])
        elif sub_action == "ANALYZE":
            query = self._research_query(snapshot)
            results = web_alpha.search(query)
            side_effects.extend(["web.search.requested", "web.search.results.received"])
            if results:
                doi = str(results[0].get("doc_id", ""))
                citations = web_alpha.citations(doi)
                if structured is None:
                    structured = {}
                structured["citations"] = citations
                structured["target_doi"] = doi
                raw_output += f"\nAnalyzed citation context entries: {len(citations)}"
        elif sub_action == "ANNOTATE":
            if structured is None:
                structured = {"text": raw_output}
            doi = str(structured.get("doi", "")).strip()
            title = str(structured.get("title", "")).strip() or "Untitled note"
            notes = str(structured.get("notes", "")).strip() or raw_output[:500]
            if not doi:
                query = self._research_query(snapshot)
                results = web_alpha.search(query)
                side_effects.extend(["web.search.requested", "web.search.results.received"])
                if results:
                    doi = str(results[0].get("doc_id", "")).strip()
                    title = str(results[0].get("title", title)).strip() or title
            if doi:
                item_key = web_alpha.catalog(title=title, doi=doi, notes=notes, tags=[snapshot.field_chosen or "alpha"])
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
                public_writer.append(
                    "agent.constitution.revised",
                    {
                        "source_event_id": snapshot.snapshot_id,
                        "amendment_text": amendment,
                        "revision_diff": revision_diff,
                    },
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
            artifact_id, artifact_path = self._write_artifact(
                top_action=top_action,
                sub_action=sub_action,
                snapshot=snapshot,
                raw_output=raw_output,
                structured=structured,
            )
            public_writer.append(
                "agent.artifact.stored",
                {
                    "artifact_id": artifact_id,
                    "artifact_path": artifact_path,
                    "action": f"{top_action}/{sub_action}",
                    "config_version": self.config_version,
                    "snapshot_id": snapshot.snapshot_id,
                },
                ecosystem_id=self.storage.ecosystem_id,
                agent_id=self.agent_id,
            )
            side_effects.append("agent.artifact.stored")

        return ExecutionResult(
            raw_output=raw_output,
            structured=structured,
            llm_response=llm_response,
            side_effects=side_effects,
        )

    @staticmethod
    def _parse_structured(sub_action: str, raw_output: str) -> dict | None:
        if sub_action not in {"ANALYZE", "ANNOTATE"}:
            return None
        try:
            return json.loads(raw_output)
        except json.JSONDecodeError:
            return {"text": raw_output}

    @staticmethod
    def _extract_amendment(raw_output: str) -> str | None:
        marker = "--- AMENDMENT ---"
        if marker not in raw_output:
            return None
        _, amendment = raw_output.split(marker, 1)
        amendment = amendment.strip()
        return amendment or None

    @staticmethod
    def _research_query(snapshot: StateSnapshot) -> str:
        return snapshot.field_chosen or "knowledge commons"

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

    def _fallback_corpus(self):
        from workload.corpus_alpha import CorpusAlpha

        return CorpusAlpha(self.storage.corpus_dir())
