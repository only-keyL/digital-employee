"""In-process TTL deduplication for WeCom msg_id."""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock

from app.wecom.constants import DEDUP_MAX_ENTRIES


class WecomDedupStore:
    def __init__(self, *, ttl_seconds: int = 86400, max_entries: int = DEDUP_MAX_ENTRIES) -> None:
        self._ttl_seconds = max(1, ttl_seconds)
        self._max_entries = max(1, max_entries)
        self._entries: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = Lock()

    def _evict_expired(self, now: float) -> None:
        expired_keys = [key for key, (expires_at, _) in self._entries.items() if expires_at <= now]
        for key in expired_keys:
            self._entries.pop(key, None)

    def _trim_size(self) -> None:
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def get_cached_xml(self, msg_id: str) -> str | None:
        now = time.time()
        with self._lock:
            self._evict_expired(now)
            item = self._entries.get(msg_id)
            if item is None:
                return None
            expires_at, xml_body = item
            if expires_at <= now:
                self._entries.pop(msg_id, None)
                return None
            self._entries.move_to_end(msg_id)
            return xml_body

    def save_xml(self, msg_id: str, xml_body: str) -> None:
        now = time.time()
        with self._lock:
            self._evict_expired(now)
            self._entries[msg_id] = (now + self._ttl_seconds, xml_body)
            self._entries.move_to_end(msg_id)
            self._trim_size()
