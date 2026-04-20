"""ChromaDB-backed retrieval adapter.

This module imports chromadb lazily — if the dependency is not installed, the
adapter raises a helpful error at construction time. The rest of the workbench
keeps working without chromadb.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Passage


class ChromaRetrievalAdapter:
    name = "chroma"

    def __init__(self, profile_ref: str, root: Path | None = None,
                 collection: str = "default") -> None:
        try:
            import chromadb  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "chromadb not installed. Install with: "
                "uv add chromadb sentence-transformers"
            ) from e
        import chromadb
        self.profile_ref = profile_ref
        self.root = root or Path.cwd()
        persist_dir = self.root / "data" / "retrieval" / profile_ref / "chroma"
        persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection_name = collection
        self._collection = self.client.get_or_create_collection(collection)

    def index(self, documents: list[dict[str, Any]]) -> int:
        ids = [str(d.get("id", str(i))) for i, d in enumerate(documents)]
        texts = [str(d.get("text", "")) for d in documents]
        metas = [dict(d.get("metadata", {})) for d in documents]
        self._collection.upsert(ids=ids, documents=texts, metadatas=metas)
        return len(ids)

    def retrieve(self, query: str, profile: dict) -> list[Passage]:
        top_k = int(profile.get("top_k", 5))
        results = self._collection.query(query_texts=[query], n_results=top_k)
        ids = (results.get("ids") or [[]])[0]
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[0.0] * len(ids)])[0]
        out: list[Passage] = []
        for i, d, m, dist in zip(ids, docs, metas, distances):
            out.append(Passage(id=str(i), text=str(d), score=1.0 - float(dist),
                               metadata=dict(m or {})))
        return out
