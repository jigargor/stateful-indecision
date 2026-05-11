from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from agent.constitution_manager import ConstitutionManager
from infra.shared_knowledge import evaluate_access, load_grant_state
from infra.storage import EcosystemStorage
from safety.firewalls import validate_agent_access

logger = logging.getLogger(__name__)


_TRUNCATION_MARKER = " [truncated]"


def _truncate_to_cap(text: str, cap: int) -> tuple[str, bool]:
    """Truncate text so the result (including marker) fits within cap chars."""
    if len(text) <= cap:
        return text, False
    marker_len = len(_TRUNCATION_MARKER)
    if cap <= marker_len:
        return _TRUNCATION_MARKER[:cap], True
    return text[: cap - marker_len] + _TRUNCATION_MARKER, True


@dataclass
class ContextSegment:
    """A provenance-tagged block of injected context for E1 memory exposure."""
    source_type: str
    source_ledger: str
    source_event_ids: list[str]
    source_agent_ids: list[str]
    text: str
    truncated: bool = False


@dataclass
class StateSnapshot:
    snapshot_id: str
    constitution_text: str
    recent_events: list[dict]
    recent_notebook: list[str]
    recent_notebook_summary: str | None
    belief_state: dict[str, float]
    field_chosen: str | None
    in_commons: bool
    embedding_blob_ref: str | None
    retrieved_context: list[dict] = field(default_factory=list)
    external_visitor_briefing: str | None = None
    peer_context: list[ContextSegment] = field(default_factory=list)
    forum_digest: list[ContextSegment] = field(default_factory=list)
    shared_knowledge_audits: list[dict] = field(default_factory=list)


class StateBuilder:
    def __init__(
        self,
        storage: EcosystemStorage,
        agent_id: str,
        *,
        recent_events_cap: int = 20,
        recent_notebook_cap: int = 5,
        enable_rag: bool = False,
        rag_collection: str = "research_artifacts",
        rag_n_results: int = 5,
        rag_min_relevance: float = 0.3,
        vectordb_dir: Path | str = ".vectordb",
        enable_peer_context: bool = False,
        peer_context_cap: int = 0,
        enable_forum_digest: bool = False,
        forum_digest_cap: int = 0,
        memory_context_total_cap: int = 0,
        enable_shared_knowledge_retrieval: bool = False,
        shared_knowledge_family_id: str | None = None,
        shared_knowledge_access_profile: str = "default",
        shared_knowledge_collection: str = "shared_knowledge",
        shared_knowledge_n_results: int = 5,
        shared_knowledge_min_relevance: float = 0.3,
        shared_knowledge_grant_max_age_sec: int = 86400,
    ):
        self.storage = storage
        self.agent_id = agent_id
        self.constitution = ConstitutionManager(storage, agent_id)
        self.recent_events_cap = recent_events_cap
        self.recent_notebook_cap = recent_notebook_cap
        self.enable_rag = enable_rag
        self.rag_collection = rag_collection
        self.rag_n_results = rag_n_results
        self.rag_min_relevance = rag_min_relevance
        self.vectordb_dir = Path(vectordb_dir)
        self.enable_peer_context = enable_peer_context
        self.peer_context_cap = peer_context_cap
        self.enable_forum_digest = enable_forum_digest
        self.forum_digest_cap = forum_digest_cap
        self.memory_context_total_cap = memory_context_total_cap
        self.enable_shared_knowledge_retrieval = enable_shared_knowledge_retrieval
        self.shared_knowledge_family_id = shared_knowledge_family_id
        self.shared_knowledge_access_profile = shared_knowledge_access_profile
        self.shared_knowledge_collection = shared_knowledge_collection
        self.shared_knowledge_n_results = shared_knowledge_n_results
        self.shared_knowledge_min_relevance = shared_knowledge_min_relevance
        self.shared_knowledge_grant_max_age_sec = shared_knowledge_grant_max_age_sec

    def build(self) -> StateSnapshot:
        public_path = self.storage.public_ledger()
        notebook_path = self.storage.agent_notebook(self.agent_id)
        townhall_path = self.storage.townhall_ledger()
        validate_agent_access(self.storage, self.agent_id, public_path)
        validate_agent_access(self.storage, self.agent_id, notebook_path)
        validate_agent_access(self.storage, self.agent_id, townhall_path)
        public_events = self._load_jsonl(public_path)
        notebook_events = self._load_jsonl(notebook_path)
        constitution_text = self.constitution.read_body()
        field_chosen = self._frontmatter_field(self.constitution.read(), "field_chosen")

        all_agent_events = [event for event in public_events if event.get("agent_id") == self.agent_id]
        recent_events = all_agent_events[-self.recent_events_cap:] if self.recent_events_cap > 0 else []
        all_notebook_texts = [
            event.get("payload", {}).get("text", "")
            for event in notebook_events
            if event.get("event_type") == "agent.notebook.appended"
        ]
        recent_notebook = all_notebook_texts[-self.recent_notebook_cap:] if self.recent_notebook_cap > 0 else []
        older_notebook = all_notebook_texts[:-self.recent_notebook_cap] if self.recent_notebook_cap > 0 else all_notebook_texts
        recent_notebook_summary = self._summarize_notebook_prefix(older_notebook)
        belief_state = self._build_belief_state(recent_events, recent_notebook, in_commons=False)

        in_commons = False
        for event in reversed(public_events):
            if event.get("agent_id") != self.agent_id:
                continue
            if event.get("event_type") == "commons.visited":
                in_commons = True
                break
            if event.get("event_type") == "commons.left":
                in_commons = False
                break
        belief_state["in_commons"] = 1.0 if in_commons else 0.0

        retrieved_context: list[dict] = []
        embedding_blob_ref: str | None = None
        shared_knowledge_audits: list[dict] = []
        if self.enable_rag:
            retrieved_context, embedding_blob_ref, shared_knowledge_audits = self._retrieve_context(
                recent_events,
                recent_notebook,
                field_chosen,
            )

        external_visitor_briefing = self._latest_external_visitor_briefing(townhall_path)

        peer_context: list[ContextSegment] = []
        if self.enable_peer_context and self.peer_context_cap > 0:
            peer_context = self._extract_peer_context()

        forum_digest: list[ContextSegment] = []
        if self.enable_forum_digest and self.forum_digest_cap > 0:
            forum_digest = self._extract_forum_digest()

        if self.memory_context_total_cap > 0:
            peer_context, forum_digest = self._apply_total_cap(
                peer_context, forum_digest, self.memory_context_total_cap
            )

        return StateSnapshot(
            snapshot_id=str(uuid4()),
            constitution_text=constitution_text,
            recent_events=recent_events,
            recent_notebook=recent_notebook,
            recent_notebook_summary=recent_notebook_summary,
            belief_state=belief_state,
            field_chosen=None if field_chosen in {"None", "null", ""} else field_chosen,
            in_commons=in_commons,
            embedding_blob_ref=embedding_blob_ref,
            retrieved_context=retrieved_context,
            external_visitor_briefing=external_visitor_briefing,
            peer_context=peer_context,
            forum_digest=forum_digest,
            shared_knowledge_audits=shared_knowledge_audits,
        )

    @staticmethod
    def _latest_external_visitor_briefing(townhall_path: Path) -> str | None:
        """Summarize the most recent external-visitor townhall session from the ecosystem ledger."""
        if not townhall_path.exists():
            return None
        events: list[dict] = []
        for line in townhall_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        convene_idx: int | None = None
        for i in range(len(events) - 1, -1, -1):
            ev = events[i]
            if ev.get("event_type") != "townhall.convened":
                continue
            payload = ev.get("payload") or {}
            if payload.get("session_kind") != "external_visitor":
                continue
            convene_idx = i
            break
        if convene_idx is None:
            return None
        convene_payload = events[convene_idx].get("payload") or {}
        speaker = str(convene_payload.get("speaker_id", "external-expert"))
        topic = str(convene_payload.get("topic", "")).strip()
        bridge = str(convene_payload.get("tangential_bridge", "")).strip()
        broadcast_text = ""
        for j in range(convene_idx + 1, len(events)):
            e2 = events[j]
            et = e2.get("event_type")
            if et == "townhall.adjourned":
                break
            if et == "townhall.convened":
                break
            if et == "townhall.broadcast":
                broadcast_text = str((e2.get("payload") or {}).get("text", "") or "").strip()
        lines_out: list[str] = [f"External visitor ({speaker}) — topic: {topic or '(no topic line)'}"]
        if bridge:
            lines_out.append(f"Tangential bridge to your research: {bridge}")
        if broadcast_text:
            lines_out.append(f"Visitor message: {broadcast_text}")
        return "\n".join(lines_out)

    @staticmethod
    def _load_jsonl(path) -> list[dict]:
        if not path.exists():
            return []
        events: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events

    @staticmethod
    def _frontmatter_field(text: str, key: str) -> str | None:
        if not text.startswith("---\n"):
            return None
        end_idx = text.find("\n---\n", 4)
        if end_idx == -1:
            return None
        for line in text[4:end_idx].splitlines():
            if line.startswith(f"{key}:"):
                return line.split(":", 1)[1].strip()
        return None

    @staticmethod
    def _summarize_notebook_prefix(texts: list[str]) -> str | None:
        if not texts:
            return None
        unique_count = len(set(texts))
        excerpt = []
        for text in texts[-2:]:
            short = " ".join(text.split())
            excerpt.append(short[:120])
        return (
            f"Older notebook context: {len(texts)} entries "
            f"({unique_count} unique). Recent older excerpts: {excerpt}"
        )

    def _retrieve_context(
        self,
        recent_events: list[dict],
        recent_notebook: list[str],
        field_chosen: str | None,
    ) -> tuple[list[dict], str | None, list[dict]]:
        """Query the vector store for relevant research artifacts and corpora."""
        try:
            from infra.embeddings import get_embedder
            from infra.vector_store import VectorStore
        except ImportError:
            logger.debug("RAG dependencies not installed, skipping retrieval")
            return [], None, []

        try:
            store = VectorStore(persist_dir=self.vectordb_dir)
            embedder = get_embedder()
        except Exception as exc:
            logger.warning("Failed to initialize RAG components: %s", exc)
            return [], None, []

        query_text = self._build_rag_query(recent_events, recent_notebook, field_chosen)
        if not query_text.strip():
            return [], None, []

        try:
            results = store.query(
                collection=self.rag_collection,
                query_text=query_text,
                embedder=embedder,
                n_results=self.rag_n_results,
                min_relevance=self.rag_min_relevance,
            )
        except Exception as exc:
            logger.warning("RAG query failed: %s", exc)
            return [], None, []

        context_entries = []
        shared_knowledge_audits: list[dict] = []
        for doc_id, document, metadata, distance in zip(
            results.ids, results.documents, results.metadatas, results.distances
        ):
            context_entries.append({
                "id": doc_id,
                "text": document[:2000],
                "relevance": round(1.0 - distance, 4),
                "action": metadata.get("action", ""),
                "agent_id": metadata.get("agent_id", ""),
                "source_type": metadata.get("source_type", ""),
            })

        if self.enable_shared_knowledge_retrieval and self.shared_knowledge_family_id:
            shared_entries, shared_audits = self._retrieve_shared_context(
                query_text=query_text,
                store=store,
                embedder=embedder,
            )
            context_entries.extend(shared_entries)
            shared_knowledge_audits.extend(shared_audits)

        blob_ref = f"rag:{self.rag_collection}:{len(context_entries)}" if context_entries else None
        return context_entries, blob_ref, shared_knowledge_audits

    def _retrieve_shared_context(
        self,
        *,
        query_text: str,
        store,
        embedder,
    ) -> tuple[list[dict], list[dict]]:
        if not self.shared_knowledge_family_id:
            return [], []

        audits: list[dict] = []
        try:
            grant_state = load_grant_state(
                self.storage.shared_knowledge_grant_state(self.shared_knowledge_family_id),
                family_id=self.shared_knowledge_family_id,
            )
            decision = evaluate_access(
                grant_state,
                ecosystem_id=self.storage.ecosystem_id,
                agent_id=self.agent_id,
                access_profile=self.shared_knowledge_access_profile,
                max_age_sec=self.shared_knowledge_grant_max_age_sec,
            )
        except Exception as exc:
            audits.append({
                "event_type": "shared_knowledge.retrieval_denied",
                "payload": {
                    "family_id": self.shared_knowledge_family_id,
                    "access_profile": self.shared_knowledge_access_profile,
                    "reason": f"grant_state_error:{type(exc).__name__}",
                },
            })
            return [], audits

        if not decision.allowed:
            audits.append({
                "event_type": "shared_knowledge.retrieval_denied",
                "payload": {
                    "family_id": self.shared_knowledge_family_id,
                    "access_profile": self.shared_knowledge_access_profile,
                    "reason": decision.reason,
                },
            })
            return [], audits

        audits.append({
            "event_type": "shared_knowledge.retrieval_allowed",
            "payload": {
                "family_id": self.shared_knowledge_family_id,
                "access_profile": self.shared_knowledge_access_profile,
                "grant_version": decision.grant_version,
                "grants_hash": decision.grants_hash,
                "reason": decision.reason,
                "query_preview": query_text[:280],
            },
        })

        try:
            result = store.query(
                collection=self.shared_knowledge_collection,
                query_text=query_text,
                embedder=embedder,
                n_results=self.shared_knowledge_n_results,
                where={
                    "family_id": self.shared_knowledge_family_id,
                    "visibility": "promoted",
                },
                min_relevance=self.shared_knowledge_min_relevance,
            )
        except Exception as exc:
            logger.warning("Shared knowledge query failed: %s", exc)
            return [], audits

        context_entries: list[dict] = []
        used_ids: list[str] = []
        for doc_id, document, metadata, distance in zip(
            result.ids, result.documents, result.metadatas, result.distances
        ):
            used_ids.append(doc_id)
            context_entries.append({
                "id": doc_id,
                "text": document[:2000],
                "relevance": round(1.0 - distance, 4),
                "action": metadata.get("action", ""),
                "agent_id": "",
                "source_type": "shared_knowledge",
                "family_id": self.shared_knowledge_family_id,
            })

        if used_ids:
            audits.append({
                "event_type": "shared_knowledge.context_used",
                "payload": {
                    "family_id": self.shared_knowledge_family_id,
                    "access_profile": self.shared_knowledge_access_profile,
                    "grant_version": decision.grant_version,
                    "grants_hash": decision.grants_hash,
                    "result_count": len(used_ids),
                    "promotion_ids": used_ids,
                },
            })
        return context_entries, audits

    @staticmethod
    def _build_rag_query(
        recent_events: list[dict],
        recent_notebook: list[str],
        field_chosen: str | None,
    ) -> str:
        """Build a query string from recent agent state for RAG retrieval."""
        parts: list[str] = []
        if field_chosen:
            parts.append(f"Field: {field_chosen}")

        for event in recent_events[-3:]:
            payload = event.get("payload", {})
            raw = payload.get("raw_output", "")
            if raw:
                parts.append(raw[:300])
            action = payload.get("top_action", "") or payload.get("action", "")
            if action:
                parts.append(action)

        for note in recent_notebook[-2:]:
            parts.append(note[:200])

        return " ".join(parts)

    def _extract_peer_context(self) -> list[ContextSegment]:
        """Extract recent notebook snippets from peer agents, capped and provenance-tagged.

        Cross-agent notebook reads are explicitly gated behind enable_peer_context.
        The read path stays within ecosystem scope (no writes, no eval-ledger access).
        """
        segments: list[ContextSegment] = []
        remaining = self.peer_context_cap
        for peer_id in self.storage.iter_agent_ids():
            if peer_id == self.agent_id or remaining <= 0:
                continue
            peer_notebook_path = self.storage.agent_notebook(peer_id)
            if not str(peer_notebook_path.resolve()).startswith(str(self.storage.ecosystem_dir)):
                continue
            if not peer_notebook_path.exists():
                continue
            events = self._load_jsonl(peer_notebook_path)
            notebook_entries = [
                e for e in events
                if e.get("event_type") == "agent.notebook.appended"
            ]
            if not notebook_entries:
                continue
            recent = notebook_entries[-3:]
            texts: list[str] = []
            event_ids: list[str] = []
            for entry in recent:
                text = str(entry.get("payload", {}).get("text", ""))
                eid = str(entry.get("event_id", ""))
                if text.strip():
                    texts.append(text)
                    if eid:
                        event_ids.append(eid)
            if not texts:
                continue
            combined = " | ".join(texts)
            combined, truncated = _truncate_to_cap(combined, remaining)
            segment = ContextSegment(
                source_type="peer_notebook",
                source_ledger=str(peer_notebook_path.relative_to(self.storage.base_dir)),
                source_event_ids=event_ids,
                source_agent_ids=[peer_id],
                text=combined,
                truncated=truncated,
            )
            segments.append(segment)
            remaining -= len(combined)
        return segments

    def _extract_forum_digest(self) -> list[ContextSegment]:
        """Extract recent roundtable and townhall utterances, capped and provenance-tagged."""
        segments: list[ContextSegment] = []
        remaining = self.forum_digest_cap

        forum_sources = [
            ("roundtable", self.storage.roundtable_ledger(), {"roundtable.utterance"}),
            ("townhall", self.storage.townhall_ledger(), {"townhall.broadcast", "townhall.response"}),
        ]
        for source_name, ledger_path, speech_types in forum_sources:
            if remaining <= 0:
                break
            validate_agent_access(self.storage, self.agent_id, ledger_path)
            if not ledger_path.exists():
                continue
            events = self._load_jsonl(ledger_path)
            speech_events = [e for e in events if e.get("event_type") in speech_types]
            if not speech_events:
                continue
            recent = speech_events[-5:]
            texts: list[str] = []
            event_ids: list[str] = []
            agent_ids: list[str] = []
            for entry in recent:
                payload = entry.get("payload", {})
                text = str(payload.get("text", "")).strip()
                eid = str(entry.get("event_id", ""))
                aid = str(entry.get("agent_id", ""))
                if text:
                    texts.append(f"[{aid}] {text}" if aid else text)
                    if eid:
                        event_ids.append(eid)
                    if aid and aid not in agent_ids:
                        agent_ids.append(aid)
            if not texts:
                continue
            combined = "\n".join(texts)
            combined, truncated = _truncate_to_cap(combined, remaining)
            segment = ContextSegment(
                source_type=f"forum_{source_name}",
                source_ledger=str(ledger_path.relative_to(self.storage.base_dir)),
                source_event_ids=event_ids,
                source_agent_ids=agent_ids,
                text=combined,
                truncated=truncated,
            )
            segments.append(segment)
            remaining -= len(combined)
        return segments

    @staticmethod
    def _apply_total_cap(
        peer_context: list[ContextSegment],
        forum_digest: list[ContextSegment],
        total_cap: int,
    ) -> tuple[list[ContextSegment], list[ContextSegment]]:
        """Enforce a global character budget across all E1 context segments."""
        remaining = total_cap
        capped_peer: list[ContextSegment] = []
        for seg in peer_context:
            if remaining <= 0:
                break
            if len(seg.text) <= remaining:
                capped_peer.append(seg)
                remaining -= len(seg.text)
            else:
                text, _ = _truncate_to_cap(seg.text, remaining)
                capped_peer.append(ContextSegment(
                    source_type=seg.source_type,
                    source_ledger=seg.source_ledger,
                    source_event_ids=seg.source_event_ids,
                    source_agent_ids=seg.source_agent_ids,
                    text=text,
                    truncated=True,
                ))
                remaining = 0
        capped_forum: list[ContextSegment] = []
        for seg in forum_digest:
            if remaining <= 0:
                break
            if len(seg.text) <= remaining:
                capped_forum.append(seg)
                remaining -= len(seg.text)
            else:
                text, _ = _truncate_to_cap(seg.text, remaining)
                capped_forum.append(ContextSegment(
                    source_type=seg.source_type,
                    source_ledger=seg.source_ledger,
                    source_event_ids=seg.source_event_ids,
                    source_agent_ids=seg.source_agent_ids,
                    text=text,
                    truncated=True,
                ))
                remaining = 0
        return capped_peer, capped_forum

    @staticmethod
    def _build_belief_state(
        recent_events: list[dict],
        recent_notebook: list[str],
        *,
        in_commons: bool,
    ) -> dict[str, float]:
        event_type_counts: dict[str, int] = {}
        for event in recent_events:
            event_type = str(event.get("event_type", "unknown"))
            event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
        total_events = max(sum(event_type_counts.values()), 1)
        notebook_unique = len(set(text.strip() for text in recent_notebook if text.strip()))
        notebook_total = len(recent_notebook)
        notebook_dup_ratio = 0.0
        if notebook_total:
            notebook_dup_ratio = 1.0 - (notebook_unique / notebook_total)
        return {
            "event_density": min(1.0, total_events / 20.0),
            "notebook_dup_ratio": round(notebook_dup_ratio, 4),
            "in_commons": 1.0 if in_commons else 0.0,
        }
