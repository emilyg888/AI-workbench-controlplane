from __future__ import annotations

import re
from typing import Any

from .base import EvalExample, Prediction, ScorerResult, register_scorer

_TOKEN_RE = re.compile(r"\w+")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


@register_scorer("passage_overlap")
class PassageOverlapScorer:
    """Fraction of output tokens also present in retrieved context."""

    name = "passage_overlap"

    def score(
        self,
        predictions: list[Prediction],
        eval_set: list[EvalExample],
        profile: dict[str, Any],
    ) -> ScorerResult:
        min_overlap = float(profile.get("min_overlap", 0.3))
        per_item: list[dict[str, Any]] = []
        values: list[float] = []
        for p in predictions:
            if p.error or not p.output:
                per_item.append({"input_id": p.input_id, "value": 0.0})
                values.append(0.0)
                continue
            if not p.context:
                # No retrieval to ground against — neutral 1.0 (nothing to violate)
                per_item.append({"input_id": p.input_id, "value": 1.0,
                                 "explanation": "no retrieval context"})
                values.append(1.0)
                continue
            out_tokens = _tokens(p.output)
            ctx_tokens: set[str] = set()
            for c in p.context:
                ctx_tokens |= _tokens(str(c.get("text", "")))
            if not out_tokens:
                v = 0.0
            else:
                overlap = len(out_tokens & ctx_tokens) / len(out_tokens)
                v = 1.0 if overlap >= min_overlap else overlap / min_overlap
            per_item.append({"input_id": p.input_id, "value": v})
            values.append(v)
        value = sum(values) / len(values) if values else 0.0
        return ScorerResult(name=self.name, value=value, per_item=per_item)
