from __future__ import annotations

from typing import Any

from .base import EvalExample, Prediction, ScorerResult, register_scorer


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


@register_scorer("latency_budget")
class LatencyBudgetScorer:
    """1.0 under budget, linearly decays to 0 at 2x budget (p95 basis)."""

    name = "latency_budget"

    def score(
        self,
        predictions: list[Prediction],
        eval_set: list[EvalExample],
        profile: dict[str, Any],
    ) -> ScorerResult:
        budget = float(profile.get("budget_p95_ms", 2000))
        lats = [p.latency_ms for p in predictions if not p.error and p.latency_ms]
        p95 = _percentile(lats, 95)
        if p95 <= budget:
            value = 1.0
        elif p95 >= 2 * budget:
            value = 0.0
        else:
            value = 1.0 - (p95 - budget) / budget
        return ScorerResult(
            name=self.name, value=value,
            per_item=[{"input_id": p.input_id, "latency_ms": p.latency_ms}
                      for p in predictions],
            notes=f"p95={p95}ms budget={int(budget)}ms",
        )
