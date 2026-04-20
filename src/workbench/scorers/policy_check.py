from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ..storage import find_workbench_root
from .base import EvalExample, Prediction, ScorerResult, register_scorer


@register_scorer("policy_check")
class PolicyCheckScorer:
    """Loads a policy pack YAML, applies regex/keyword rules to outputs.
    Score = fraction of predictions with zero violations."""

    name = "policy_check"

    def score(
        self,
        predictions: list[Prediction],
        eval_set: list[EvalExample],
        profile: dict[str, Any],
    ) -> ScorerResult:
        pack_ref = profile.get("policy_pack_ref")
        rules = self._load_rules(pack_ref) if pack_ref else []
        per_item: list[dict[str, Any]] = []
        clean = 0
        total = 0
        for p in predictions:
            if p.error:
                per_item.append({"input_id": p.input_id, "value": 0.0,
                                 "explanation": "prediction errored"})
                total += 1
                continue
            violations = self._check(p.output or "", rules)
            ok = not violations
            clean += int(ok)
            total += 1
            per_item.append({
                "input_id": p.input_id,
                "value": 1.0 if ok else 0.0,
                "violations": violations,
            })
        value = clean / total if total else 1.0
        return ScorerResult(name=self.name, value=value, per_item=per_item)

    @staticmethod
    def _load_rules(pack_ref: str) -> list[dict]:
        try:
            root = find_workbench_root()
        except FileNotFoundError:
            return []
        p = Path(pack_ref)
        if not p.is_absolute():
            p = root / p
        if not p.exists():
            return []
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return list(data.get("output_rules") or [])

    @staticmethod
    def _check(text: str, rules: list[dict]) -> list[str]:
        hits: list[str] = []
        for rule in rules:
            rid = rule.get("id", "unnamed")
            rtype = rule.get("type")
            if rtype == "regex_block":
                pattern = rule.get("pattern", "")
                if pattern and re.search(pattern, text):
                    hits.append(rid)
            elif rtype == "keyword_block":
                for kw in rule.get("keywords", []) or []:
                    if kw and kw.lower() in text.lower():
                        hits.append(rid)
                        break
        return hits
