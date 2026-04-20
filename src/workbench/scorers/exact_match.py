from __future__ import annotations

from typing import Any

from .base import EvalExample, Prediction, ScorerResult, _by_id, register_scorer


@register_scorer("exact_match")
class ExactMatchScorer:
    name = "exact_match"

    def score(
        self,
        predictions: list[Prediction],
        eval_set: list[EvalExample],
        profile: dict[str, Any],
    ) -> ScorerResult:
        case_sensitive = bool(profile.get("case_sensitive", False))
        index = _by_id(eval_set)
        per_item: list[dict[str, Any]] = []
        matches = 0
        total = 0
        for p in predictions:
            ex = index.get(p.input_id)
            if ex is None or ex.expected is None or p.error is not None:
                per_item.append({
                    "input_id": p.input_id, "value": 0.0,
                    "explanation": "no expected or prediction errored",
                })
                total += 1
                continue
            a = str(p.output or "").strip()
            b = str(ex.expected).strip()
            if not case_sensitive:
                a = a.lower()
                b = b.lower()
            hit = 1.0 if a == b else 0.0
            matches += int(hit)
            total += 1
            per_item.append({"input_id": p.input_id, "value": hit,
                             "explanation": "match" if hit else "mismatch"})
        value = matches / total if total else 0.0
        return ScorerResult(name=self.name, value=value, per_item=per_item)
