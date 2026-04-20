from __future__ import annotations

from workbench.scorers import get_scorer
from workbench.scorers.base import EvalExample, Prediction


def _preds(*rows) -> list[Prediction]:
    return [Prediction(input_id=iid, output=out, latency_ms=lat, error=err, context=ctx or [])
            for iid, out, lat, err, ctx in rows]


def _exs(*rows) -> list[EvalExample]:
    return [EvalExample(input_id=iid, expected=exp) for iid, exp in rows]


def test_exact_match_case_insensitive() -> None:
    s = get_scorer("exact_match")()
    preds = _preds(("a", "Hello", 100, None, None), ("b", "world", 100, None, None))
    exs = _exs(("a", "HELLO"), ("b", "nope"))
    r = s.score(preds, exs, {"case_sensitive": False})
    assert r.value == 0.5


def test_substring() -> None:
    s = get_scorer("substring")()
    preds = _preds(("a", "The deductible is $500 today.", 10, None, None))
    exs = _exs(("a", "deductible is $500"))
    r = s.score(preds, exs, {})
    assert r.value == 1.0


def test_passage_overlap_with_context() -> None:
    s = get_scorer("passage_overlap")()
    ctx = [{"text": "water damage is covered under the policy"}]
    preds = _preds(("a", "water damage covered", 10, None, ctx))
    exs = _exs(("a", "yes"))
    r = s.score(preds, exs, {"min_overlap": 0.3})
    assert r.value == 1.0


def test_passage_overlap_no_context_neutral() -> None:
    s = get_scorer("passage_overlap")()
    preds = _preds(("a", "anything", 10, None, None))
    exs = _exs(("a", "anything"))
    r = s.score(preds, exs, {})
    assert r.value == 1.0


def test_latency_budget_within() -> None:
    s = get_scorer("latency_budget")()
    preds = _preds(*[(f"q{i}", "ok", 500, None, None) for i in range(10)])
    r = s.score(preds, [], {"budget_p95_ms": 2000})
    assert r.value == 1.0


def test_latency_budget_over() -> None:
    s = get_scorer("latency_budget")()
    preds = _preds(*[(f"q{i}", "ok", 4000, None, None) for i in range(10)])
    r = s.score(preds, [], {"budget_p95_ms": 2000})
    assert r.value == 0.0


def test_non_empty() -> None:
    s = get_scorer("non_empty")()
    preds = _preds(("a", "hello", 10, None, None), ("b", "", 10, None, None),
                   ("c", None, 10, "boom", None))
    r = s.score(preds, [], {})
    assert r.value == 1 / 3


def test_refusal_correct_when_expected() -> None:
    s = get_scorer("refusal_classifier")()
    preds = _preds(("a", "I can't help with that", 10, None, None))
    exs = _exs(("a", "REFUSE: medical advice"))
    r = s.score(preds, exs, {})
    assert r.value == 1.0


def test_policy_check_empty_pack_passes(workbench_root) -> None:
    s = get_scorer("policy_check")()
    preds = _preds(("a", "anything", 10, None, None))
    r = s.score(preds, [], {})
    assert r.value == 1.0


def test_policy_check_blocks_keyword(workbench_root) -> None:
    pack = workbench_root / "data" / "policies" / "pack.yaml"
    pack.write_text(
        "output_rules:\n"
        "  - id: no_advice\n"
        "    type: keyword_block\n"
        "    keywords: ['buy this stock']\n"
    )
    s = get_scorer("policy_check")()
    preds = _preds(
        ("a", "You should buy this stock", 10, None, None),
        ("b", "safe reply", 10, None, None),
    )
    r = s.score(preds, [], {"policy_pack_ref": str(pack)})
    assert r.value == 0.5
