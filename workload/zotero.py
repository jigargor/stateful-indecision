from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib import parse, request


ZOTERO_BASE_URL = "https://api.zotero.org"


@dataclass
class ZoteroItem:
    key: str
    title: str
    doi: str
    abstract_note: str
    tags: list[str]
    raw: dict[str, Any]


class ZoteroClient:
    def __init__(
        self,
        api_key: str | None = None,
        library_id: str | None = None,
        library_type: str = "users",
        timeout_s: float = 20.0,
    ):
        self.api_key = api_key or os.getenv("ZOTERO_API_KEY", "")
        self.library_id = library_id or os.getenv("ZOTERO_LIBRARY_ID", "")
        self.library_type = library_type
        self.timeout_s = timeout_s

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.library_id)

    def search_library(self, query: str, limit: int = 5) -> tuple[list[ZoteroItem], int]:
        params = parse.urlencode({"q": query, "limit": max(1, min(limit, 20)), "format": "json"})
        data, latency_ms = self._request_json("GET", f"/{self.library_type}/{self.library_id}/items?{params}")
        return self._parse_items(data), latency_ms

    def get_item(self, item_key: str) -> tuple[ZoteroItem | None, int]:
        data, latency_ms = self._request_json("GET", f"/{self.library_type}/{self.library_id}/items/{item_key}?format=json")
        items = self._parse_items(data)
        if not items:
            return None, latency_ms
        return items[0], latency_ms

    def save_item(self, title: str, doi: str, notes: str = "") -> tuple[str, int]:
        payload = [
            {
                "itemType": "journalArticle",
                "title": title,
                "DOI": doi,
                "abstractNote": notes,
                "tags": [],
            }
        ]
        data, latency_ms = self._request_json("POST", f"/{self.library_type}/{self.library_id}/items", payload=payload)
        key = str(data.get("successful", {}).get("0", {}).get("key", ""))
        return key, latency_ms

    def add_tags(self, item_key: str, tags: list[str]) -> tuple[bool, int]:
        item, latency_ms_get = self.get_item(item_key)
        if item is None:
            return False, latency_ms_get
        updated = dict(item.raw)
        updated["tags"] = [{"tag": tag} for tag in tags]
        _, latency_ms_put = self._request_json(
            "PUT",
            f"/{self.library_type}/{self.library_id}/items/{item_key}",
            payload=updated,
        )
        return True, latency_ms_get + latency_ms_put

    def get_collection(self, name: str, limit: int = 100) -> tuple[list[ZoteroItem], int]:
        params = parse.urlencode({"q": name, "limit": max(1, min(limit, 100)), "format": "json"})
        data, latency_ms = self._request_json("GET", f"/{self.library_type}/{self.library_id}/collections?{params}")
        collection_key = ""
        for item in data if isinstance(data, list) else []:
            if str(item.get("data", {}).get("name", "")).lower() == name.lower():
                collection_key = str(item.get("key", ""))
                break
        if not collection_key:
            return [], latency_ms
        items_data, items_latency_ms = self._request_json(
            "GET",
            f"/{self.library_type}/{self.library_id}/collections/{collection_key}/items?format=json",
        )
        return self._parse_items(items_data), latency_ms + items_latency_ms

    def create_collection(self, name: str) -> tuple[str, int]:
        payload = [{"name": name}]
        data, latency_ms = self._request_json("POST", f"/{self.library_type}/{self.library_id}/collections", payload=payload)
        key = str(data.get("successful", {}).get("0", {}).get("key", ""))
        return key, latency_ms

    def _request_json(self, method: str, path: str, payload: Any | None = None) -> tuple[Any, int]:
        if not self.enabled:
            raise RuntimeError("Zotero is not configured. Set ZOTERO_API_KEY and ZOTERO_LIBRARY_ID.")
        url = f"{ZOTERO_BASE_URL}{path}"
        headers = {"Zotero-API-Key": self.api_key}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        req = request.Request(url=url, method=method, headers=headers, data=body)
        started = time.perf_counter()
        with request.urlopen(req, timeout=self.timeout_s) as resp:
            text = resp.read().decode("utf-8")
        latency_ms = int((time.perf_counter() - started) * 1000)
        if not text:
            return {}, latency_ms
        return json.loads(text), latency_ms

    @staticmethod
    def _parse_items(data: Any) -> list[ZoteroItem]:
        if not isinstance(data, list):
            return []
        items: list[ZoteroItem] = []
        for entry in data:
            meta = entry.get("data", {})
            tags = [str(tag.get("tag", "")) for tag in meta.get("tags", []) if isinstance(tag, dict)]
            items.append(
                ZoteroItem(
                    key=str(entry.get("key", "")),
                    title=str(meta.get("title", "")),
                    doi=str(meta.get("DOI", "")),
                    abstract_note=str(meta.get("abstractNote", "")),
                    tags=tags,
                    raw=meta,
                )
            )
        return items
