"""Internal helpers for query index cache state."""

from __future__ import annotations

from dataclasses import dataclass

from .query import QueryIndex


@dataclass(slots=True)
class QueryIndexCache:
    """Track cached query index freshness across source reloads."""

    enabled: bool = True
    _load_revision: int = 0
    _index: QueryIndex | None = None
    _index_revision: int = -1

    def invalidate(self) -> None:
        """Mark the source as reloaded and clear any stale cached index."""
        self._load_revision += 1
        self._index = None
        self._index_revision = -1

    def get_cached(self) -> QueryIndex | None:
        """Return the cached index when it matches the current load revision."""
        if not self.enabled:
            return None
        if self._index is None or self._index_revision != self._load_revision:
            return None
        return self._index

    def store(self, index: QueryIndex) -> QueryIndex:
        """Store an index for the current load revision and return it."""
        if not self.enabled:
            return index
        self._index = index
        self._index_revision = self._load_revision
        return index
