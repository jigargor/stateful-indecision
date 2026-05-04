from __future__ import annotations

from hashlib import sha256

from core.writer import ChainWriter
from workload.corpus_alpha import CorpusAlpha
from workload.scite import SciteClient
from workload.zotero import ZoteroClient


class WebAlpha:
    def __init__(
        self,
        corpus: CorpusAlpha,
        writer: ChainWriter,
        ecosystem_id: str,
        agent_id: str,
        scite: SciteClient | None = None,
        zotero: ZoteroClient | None = None,
    ):
        self.corpus = corpus
        self.writer = writer
        self.ecosystem_id = ecosystem_id
        self.agent_id = agent_id
        self.scite = scite or SciteClient()
        self.zotero = zotero or ZoteroClient()

    def search(self, query: str) -> list[dict]:
        self.writer.append(
            "web.search.requested",
            {"query": query},
            ecosystem_id=self.ecosystem_id,
            agent_id=self.agent_id,
        )
        results: list[dict] = []
        source_policy = "alpha_corpus"
        latency_ms = 0

        if self.scite.enabled:
            try:
                scite_results, latency_ms = self.scite.search(query)
                source_policy = "scite"
                for entry in scite_results:
                    results.append(
                        {
                            "doc_id": entry.doi,
                            "title": entry.title,
                            "snippet": entry.snippet,
                        }
                    )
                    if self.zotero.enabled and entry.doi:
                        self._save_to_zotero_if_missing(entry.title, entry.doi, entry.snippet)
            except Exception:
                source_policy = "alpha_corpus"
                results = []

        if not results:
            matches = self.corpus.search(query)
            results = [
                {
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "snippet": doc.content[:200],
                }
                for doc in matches
            ]

        self.writer.append(
            "web.search.results.received",
            {
                "query": query,
                "count": len(results),
                "results": results,
                "latency_ms": latency_ms,
                "source_policy": source_policy,
            },
            ecosystem_id=self.ecosystem_id,
            agent_id=self.agent_id,
        )
        return results

    def fetch(self, doc_id: str) -> str | None:
        self.writer.append(
            "web.fetch.requested",
            {"doc_id": doc_id},
            ecosystem_id=self.ecosystem_id,
            agent_id=self.agent_id,
        )
        content: str | None = None
        source_policy = "alpha_corpus"
        latency_ms = 0

        if self.zotero.enabled:
            try:
                library_hits, latency_ms = self.zotero.search_library(doc_id, limit=1)
                if library_hits:
                    hit = library_hits[0]
                    content = hit.abstract_note or hit.title
                    source_policy = "zotero_cache"
            except Exception:
                pass

        if content is None and self.scite.enabled:
            try:
                paper, latency_ms = self.scite.get_paper(doc_id)
                if paper:
                    content = f"{paper.title}\n\n{paper.abstract}".strip()
                    source_policy = "scite"
                    if self.zotero.enabled and paper.doi:
                        self._save_to_zotero_if_missing(paper.title, paper.doi, paper.abstract)
            except Exception:
                pass

        if content is None:
            doc = self.corpus.get(doc_id)
            if doc:
                content = doc.content

        content_hash = sha256(content.encode("utf-8")).hexdigest() if content else None
        self.writer.append(
            "web.fetch.received",
            {
                "doc_id": doc_id,
                "found": content is not None,
                "latency_ms": latency_ms,
                "content_hash": content_hash,
                "source_policy": source_policy,
            },
            ecosystem_id=self.ecosystem_id,
            agent_id=self.agent_id,
        )
        return content

    def citations(self, doi: str) -> list[dict]:
        if not self.scite.enabled:
            return []
        try:
            rows, _ = self.scite.get_citations(doi, limit=5)
        except Exception:
            return []
        return [
            {
                "citing_doi": row.citing_doi,
                "classification": row.classification,
                "text": row.text,
            }
            for row in rows
        ]

    def catalog(self, title: str, doi: str, notes: str, tags: list[str]) -> str | None:
        if not self.zotero.enabled:
            return None
        try:
            item_key, _ = self.zotero.save_item(title=title, doi=doi, notes=notes)
            if item_key and tags:
                self.zotero.add_tags(item_key, tags)
            return item_key or None
        except Exception:
            return None

    def _save_to_zotero_if_missing(self, title: str, doi: str, notes: str) -> None:
        if not self.zotero.enabled:
            return
        try:
            hits, _ = self.zotero.search_library(doi, limit=1)
            if hits:
                return
            self.zotero.save_item(title=title, doi=doi, notes=notes)
        except Exception:
            return
