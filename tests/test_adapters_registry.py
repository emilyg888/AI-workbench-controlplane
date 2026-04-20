from __future__ import annotations

from workbench.adapters import registry
from workbench.adapters.base import ModelResult, Passage
from workbench.adapters.model_stub import StubModelAdapter
from workbench.adapters.retrieval_file import FileRetrievalAdapter
from workbench.adapters.retrieval_stub import StubRetrievalAdapter


def test_stub_model_adapter_generates() -> None:
    a = registry.get_model_adapter({"provider": "stub", "name": "stub"})
    r = a.generate("hello", {})
    assert isinstance(r, ModelResult)
    assert "[stub]" in r.text
    assert isinstance(a, StubModelAdapter)


def test_stub_retrieval_adapter_returns_empty() -> None:
    a = registry.get_retrieval_adapter("stub")
    assert isinstance(a, StubRetrievalAdapter)
    assert a.retrieve("query", {}) == []


def test_file_retrieval_adapter_picked_for_other_profiles(tmp_path) -> None:
    a = registry.get_retrieval_adapter("claims_profile", root=tmp_path)
    assert isinstance(a, FileRetrievalAdapter)


def test_unknown_provider_raises() -> None:
    import pytest

    with pytest.raises(registry.AdapterError):
        registry.get_model_adapter({"provider": "mystery"})


def test_file_retrieval_scores_substring(tmp_path) -> None:
    corpus = tmp_path / "data" / "retrieval" / "docs.jsonl"
    corpus.parent.mkdir(parents=True)
    corpus.write_text(
        '{"id": "d1", "text": "water damage is covered"}\n'
        '{"id": "d2", "text": "deductible is 500"}\n'
        '{"id": "d3", "text": "unrelated content"}\n'
    )
    a = FileRetrievalAdapter("docs", root=tmp_path)
    hits = a.retrieve("water damage", {"top_k": 2})
    ids = [p.id for p in hits]
    assert "d1" in ids
    assert isinstance(hits[0], Passage)
