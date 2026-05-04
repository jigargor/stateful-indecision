from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib import parse, request


SCITE_BASE_URL = "https://api.scite.ai"


@dataclass
class SciteResult:
    doi: str
    title: str
    snippet: str
    supporting: int
    contrasting: int
    mentioning: int


@dataclass
class CitationStatement:
    citing_doi: str
    text: str
    classification: str  # "supporting" | "contrasting" | "mentioning"


@dataclass
class PaperTally:
    doi: str
    supporting: int
    contrasting: int
    mentioning: int
    total: int


@dataclass
class PaperDetail:
    doi: str
    title: str
    abstract: str
    tally: PaperTally | None
    raw: dict[str, Any]


class SciteClient:
    def __init__(
        self,
        api_key: str | None = None,
        partner_key: str | None = None,
        timeout_s: float = 20.0,
    ):
        self.api_key = api_key or os.getenv("SCITE_API_KEY", "")
        self.partner_key = partner_key or os.getenv("SCITE_PARTNER_KEY", "")
        self.timeout_s = timeout_s

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def search_enabled(self) -> bool:
        return bool(self.partner_key)

    def search(self, query: str, limit: int = 5) -> tuple[list[SciteResult], int]:
        """Full-text paper search via /api_partner/search (requires partner key).
        Falls back to DOI-direct lookup if query looks like a DOI."""
        if self.search_enabled:
            params = parse.urlencode({
                "term": query,
                "limit": max(1, min(limit, 20)),
                "mode": "id_search",
            })
            try:
                payload, latency_ms = self._request_json(
                    f"/api_partner/search?{params}", key=self.partner_key
                )
                items = payload.get("hits", [])
                results: list[SciteResult] = []
                for item in items:
                    doi = str(item.get("doi", "")).strip()
                    if not doi:
                        continue
                    tally = item.get("tally") or {}
                    results.append(SciteResult(
                        doi=doi,
                        title=str(item.get("title", doi)),
                        snippet=str(item.get("abstract", ""))[:300],
                        supporting=int(tally.get("supporting", 0)),
                        contrasting=int(tally.get("contradicting", 0)),
                        mentioning=int(tally.get("mentioning", 0)),
                    ))
                return results, latency_ms
            except Exception:
                pass

        # Fallback: DOI-direct lookup
        if query.strip().startswith("10."):
            paper, ms = self.get_paper(query.strip())
            if paper:
                return [SciteResult(
                    doi=paper.doi,
                    title=paper.title,
                    snippet=paper.abstract[:300],
                    supporting=paper.tally.supporting if paper.tally else 0,
                    contrasting=paper.tally.contrasting if paper.tally else 0,
                    mentioning=paper.tally.mentioning if paper.tally else 0,
                )], ms
        return [], 0

    def get_citations(self, doi: str, limit: int = 5) -> tuple[list[CitationStatement], int]:
        """Get papers that cite this DOI via /papers/sources/{doi}.
        Returns empty if endpoint is not available on current API tier."""
        encoded = parse.quote(doi, safe="")
        try:
            payload, latency_ms = self._request_json(f"/papers/sources/{encoded}")
        except Exception:
            return [], 0
        items = payload.get("papers", [])[:limit]
        citations: list[CitationStatement] = []
        for item in items:
            citations.append(
                CitationStatement(
                    citing_doi=str(item.get("doi", "")),
                    text=str(item.get("title", "")),
                    classification="mentioning",
                )
            )
        return citations, latency_ms

    def get_tally(self, doi: str) -> tuple[PaperTally | None, int]:
        """Get supporting/contrasting/mentioning counts for a DOI via /tallies/{doi}."""
        encoded = parse.quote(doi, safe="")
        payload, latency_ms = self._request_json(f"/tallies/{encoded}")
        if not payload:
            return None, latency_ms
        tally = PaperTally(
            doi=doi,
            supporting=int(payload.get("supporting", 0)),
            contrasting=int(payload.get("contradicting", 0)),
            mentioning=int(payload.get("mentioning", 0)),
            total=int(payload.get("total", 0)),
        )
        return tally, latency_ms

    def get_paper(self, doi: str) -> tuple[PaperDetail | None, int]:
        """Fetch paper metadata from /papers/{doi}. Also attempts tally."""
        encoded = parse.quote(doi, safe="")
        payload, latency_ms = self._request_json(f"/papers/{encoded}")
        if not payload:
            return None, latency_ms
        tally_data = payload.get("tally")
        tally = None
        if tally_data:
            tally = PaperTally(
                doi=doi,
                supporting=int(tally_data.get("supporting", 0)),
                contrasting=int(tally_data.get("contradicting", 0)),
                mentioning=int(tally_data.get("mentioning", 0)),
                total=int(tally_data.get("total", 0)),
            )
        paper = PaperDetail(
            doi=str(payload.get("doi", doi)),
            title=str(payload.get("title", doi)),
            abstract=str(payload.get("abstract", "")),
            tally=tally,
            raw=payload,
        )
        return paper, latency_ms

    def _request_json(self, path: str, key: str | None = None) -> tuple[dict[str, Any], int]:
        active_key = key or self.api_key
        if not active_key:
            raise RuntimeError("Scite is not configured. Set SCITE_API_KEY.")
        url = f"{SCITE_BASE_URL}{path}"
        req = request.Request(url, headers={"Authorization": f"Bearer {active_key}"})
        started = time.perf_counter()
        with request.urlopen(req, timeout=self.timeout_s) as resp:
            body = resp.read().decode("utf-8")
        latency_ms = int((time.perf_counter() - started) * 1000)
        data = json.loads(body) if body else {}
        if isinstance(data, dict):
            return data, latency_ms
        return {"hits": data}, latency_ms
