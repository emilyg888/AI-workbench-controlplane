from __future__ import annotations

from typing import Any

from .base import EvalExample, Prediction, ScorerResult, register_scorer


@register_scorer("non_empty")
class NonEmptyScorer:
    name = "non_empty"

    def score(
        self,
        predictions: list[Prediction],
        eval_set: list[EvalExample],
        profile: dict[str, Any],
    ) -> ScorerResult:
        total = len(predictions)
        if total == 0:
            return ScorerResult(name=self.name, value=0.0)
        good = sum(
            1 for p in predictions
            if not p.error and (p.output or "").strip()
        )
        per_item = [
            {"input_id": p.input_id, "value": 1.0 if (not p.error and (p.output or "").strip()) else 0.0}
            for p in predictions
        ]
        return ScorerResult(name=self.name, value=good / total, per_item=per_item)
