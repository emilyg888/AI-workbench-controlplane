from __future__ import annotations

from .base import Passage


class StubRetrievalAdapter:
    """Returns empty context. Used when retrieval is not meaningful yet."""

    name = "stub"

    def retrieve(self, query: str, profile: dict) -> list[Passage]:
        return []
