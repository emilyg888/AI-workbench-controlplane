from __future__ import annotations

from typing import Any

from .base import EvalExample, Prediction, ScorerResult, _by_id, register_scorer


@register_scorer("substring")
class SubstringScorer:
    name = "substring"

    def score(
        self,
        predictions: list[Prediction],
        eval_set: list[EvalExample],
        profile: dict[str, Any],
    ) -> ScorerResult:
        index = _by_id(eval_set)
        per_item: list[dict[str, Any]] = []
        hits = 0
        total = 0
        for p in predictions:
            ex = index.get(p.input_id)
            if ex is None or ex.expected is None or p.error is not None:
                per_item.append({"input_id": p.input_id, "value": 0.0})
                total += 1
                continue
            needle = str(ex.expected).lower().strip()
            haystack = str(p.output or "").lower()
            hit = 1.0 if needle and needle in haystack else 0.0
            hits += int(hit)
            total += 1
            per_item.append({"input_id": p.input_id, "value": hit})
        value = hits / total if total else 0.0
        return ScorerResult(name=self.name, value=value, per_item=per_item)
