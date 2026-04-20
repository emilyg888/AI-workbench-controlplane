from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class RegressionChecks(BaseModel):
    enabled: bool = True
    baseline: str = "prod"  # "prod" | "dev" | <run_id>
    max_absolute_drop: float = 0.02
    strict_metrics: list[str] = Field(default_factory=list)


class ApprovedRequires(BaseModel):
    mode: Literal["auto", "manual"] = "auto"


class Approval(BaseModel):
    candidate_requires_all_thresholds: bool = True
    approved_requires: ApprovedRequires = Field(default_factory=ApprovedRequires)


class Guardrails(BaseModel):
    # max number of failing items per tag (read from metrics_per_item.jsonl
    # joined against inputs.jsonl tags). Any metric's per-item value == 0
    # counts as a failure for the items' tags.
    max_failures_per_tag: dict[str, int] = Field(default_factory=dict)


class PromotionRules(BaseModel):
    version: str = "1"
    name: str = "default"
    thresholds: dict[str, float] = Field(default_factory=dict)
    # Hard rules — any one failing short-circuits to rejected. Expressions
    # are of the form ``<metric> <op> <value>``, op in ==,!=,>=,<=,>,<.
    must_pass: list[str] = Field(default_factory=list)
    # Weighted metrics: reserved for future aggregate recalibration.
    # Phase 3 aggregate still governs; this block lets a reviewer see
    # the policy intent without changing behaviour.
    weighted_metrics: dict[str, float] = Field(default_factory=dict)
    guardrails: Guardrails = Field(default_factory=Guardrails)
    regression_checks: RegressionChecks = Field(default_factory=RegressionChecks)
    approval: Approval = Field(default_factory=Approval)


def load_promotion_rules(path: Path) -> PromotionRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return PromotionRules.model_validate(raw)


def rules_tag(rules: PromotionRules) -> str:
    return f"{rules.name}@v{rules.version}"
