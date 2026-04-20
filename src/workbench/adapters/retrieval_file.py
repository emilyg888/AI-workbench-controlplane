from __future__ import annotations

from pathlib import Path

from ..storage import find_workbench_root, read_jsonl
from .base import Passage


class FileRetrievalAdapter:
    """Simple substring retriever over a JSONL corpus. Placeholder for real
    vector store (Phase 6 introduces ChromaDB).

    Corpus lives at ``data/retrieval/<profile_name>.jsonl`` with one JSON per
    line: ``{"id": "...", "text": "...", "metadata": {...}}``.
    """

    name = "file"

    def __init__(self, profile_ref: str, root: Path | None = None) -> None:
        self.profile_ref = profile_ref
        self.root = root or find_workbench_root()

    def retrieve(self, query: str, profile: dict) -> list[Passage]:
        top_k = int(profile.get("top_k", 5))
        corpus_path = self._resolve_corpus()
        if not corpus_path.exists():
            return []
        q_tokens = {t for t in query.lower().split() if t}
        results: list[Passage] = []
        for rec in read_jsonl(corpus_path):
            text = str(rec.get("text", ""))
            score = self._score(q_tokens, text.lower())
            if score > 0:
                results.append(Passage(
                    id=str(rec.get("id", "")),
                    text=text,
                    score=score,
                    metadata=rec.get("metadata", {}),
                ))
        results.sort(key=lambda p: p.score, reverse=True)
        return results[:top_k]

    def _resolve_corpus(self) -> Path:
        p = Path(self.profile_ref)
        if p.is_absolute():
            return p
        if p.suffix == ".jsonl":
            candidate = self.root / p
            if candidate.exists():
                return candidate
        return self.root / "data" / "retrieval" / f"{self.profile_ref}.jsonl"

    @staticmethod
    def _score(q_tokens: set[str], text_lower: str) -> float:
        if not q_tokens:
            return 0.0
        hits = sum(1 for t in q_tokens if t in text_lower)
        return hits / len(q_tokens)
