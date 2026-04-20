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


class PromotionRules(BaseModel):
    version: str = "1"
    name: str = "default"
    thresholds: dict[str, float] = Field(default_factory=dict)
    regression_checks: RegressionChecks = Field(default_factory=RegressionChecks)
    approval: Approval = Field(default_factory=Approval)


def load_promotion_rules(path: Path) -> PromotionRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return PromotionRules.model_validate(raw)


def rules_tag(rules: PromotionRules) -> str:
    return f"{rules.name}@v{rules.version}"
