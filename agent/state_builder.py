from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from agent.constitution_manager import ConstitutionManager
from infra.storage import EcosystemStorage

logger = logging.getLogger(__name__)


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

    def build(self) -> StateSnapshot:
        public_events = self._load_jsonl(self.storage.public_ledger())
        notebook_events = self._load_jsonl(self.storage.agent_notebook(self.agent_id))
        constitution_text = self.constitution.read_body()
        field_chosen = self._frontmatter_field(self.constitution.read(), "field_chosen")

        recent_events = [event for event in public_events if event.get("agent_id") == self.agent_id][-self.recent_events_cap :]
        all_notebook_texts = [
            event.get("payload", {}).get("text", "")
            for event in notebook_events
            if event.get("event_type") == "agent.notebook.appended"
        ]
        recent_notebook = all_notebook_texts[-self.recent_notebook_cap :]
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
        if self.enable_rag:
            retrieved_context, embedding_blob_ref = self._retrieve_context(
                recent_events, recent_notebook, field_chosen
            )

        external_visitor_briefing = self._latest_external_visitor_briefing(self.storage.townhall_ledger())

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
    ) -> tuple[list[dict], str | None]:
        """Query the vector store for relevant research artifacts and corpora."""
        try:
            from infra.embeddings import get_embedder
            from infra.vector_store import VectorStore
        except ImportError:
            logger.debug("RAG dependencies not installed, skipping retrieval")
            return [], None

        try:
            store = VectorStore(persist_dir=self.vectordb_dir)
            embedder = get_embedder()
        except Exception as exc:
            logger.warning("Failed to initialize RAG components: %s", exc)
            return [], None

        query_text = self._build_rag_query(recent_events, recent_notebook, field_chosen)
        if not query_text.strip():
            return [], None

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
            return [], None

        context_entries = []
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

        blob_ref = f"rag:{self.rag_collection}:{len(context_entries)}" if context_entries else None
        return context_entries, blob_ref

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
