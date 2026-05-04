from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class CorpusDocument:
    doc_id: str
    title: str
    content: str


class CorpusAlpha:
    def __init__(self, corpus_dir: Path):
        self.corpus_dir = corpus_dir

    def list_documents(self) -> list[str]:
        return sorted(path.stem for path in self.corpus_dir.glob("*.md"))

    def get(self, doc_id: str) -> CorpusDocument | None:
        path = self.corpus_dir / f"{doc_id}.md"
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8")
        title = self._extract_title(content, doc_id)
        return CorpusDocument(doc_id=doc_id, title=title, content=content)

    def search(self, query: str) -> list[CorpusDocument]:
        matches: list[CorpusDocument] = []
        needle = query.lower()
        for doc_id in self.list_documents():
            doc = self.get(doc_id)
            if doc is None:
                continue
            haystack = f"{doc.title}\n{doc.content}".lower()
            if needle in haystack:
                matches.append(doc)
        return matches

    @staticmethod
    def _extract_title(content: str, fallback: str) -> str:
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return fallback
