from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from urllib.parse import urlsplit

from faultweaver.assessments.urls import canonicalize_url


@dataclass(slots=True)
class FrontierItem:
    url: str
    canonical_url: str
    depth: int
    kind: str
    parent_exchange_id: str | None = None
    state: str = "discovered"
    reason: str | None = None


class CrawlFrontier:
    def __init__(self, *, max_depth: int, max_query_variants_per_path: int) -> None:
        self.max_depth = max_depth
        self.max_query_variants_per_path = max_query_variants_per_path
        self.items: list[FrontierItem] = []
        self._queue: deque[FrontierItem] = deque()
        self._known: set[str] = set()
        self._query_variants: dict[tuple[str, str, int | None, str], set[str]] = {}

    def discover(
        self,
        url: str,
        *,
        depth: int,
        kind: str,
        parent_exchange_id: str | None = None,
    ) -> FrontierItem | None:
        canonical = canonicalize_url(url)
        if canonical in self._known:
            return None
        self._known.add(canonical)
        item = FrontierItem(
            url=url,
            canonical_url=canonical,
            depth=depth,
            kind=kind,
            parent_exchange_id=parent_exchange_id,
        )
        self.items.append(item)
        if depth > self.max_depth:
            item.state = "skipped"
            item.reason = "depth limit"
            return item

        parsed = urlsplit(canonical)
        key = (parsed.scheme, parsed.hostname or "", parsed.port, parsed.path)
        variants = self._query_variants.setdefault(key, set())
        if parsed.query not in variants and len(variants) >= self.max_query_variants_per_path:
            item.state = "skipped"
            item.reason = "query variation limit"
            return item
        variants.add(parsed.query)
        self._queue.append(item)
        return item

    def pop(self) -> FrontierItem | None:
        if not self._queue:
            return None
        item = self._queue.popleft()
        item.state = "queued"
        return item

    def mark_requested(self, item: FrontierItem) -> None:
        item.state = "requested"

    def mark_failed(self, item: FrontierItem, reason: str) -> None:
        item.state = "failed"
        item.reason = reason

    def __bool__(self) -> bool:
        return bool(self._queue)

    @property
    def queued_count(self) -> int:
        return len(self._queue)
