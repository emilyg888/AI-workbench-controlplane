from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ScorerConfig(BaseModel):
    type: str
    weight: float = 0.0
    # Additional scorer-specific keys are preserved in ``extras``.
    extras: dict[str, Any] = Field(default_factory=dict)


class AggregateConfig(BaseModel):
    method: str = "weighted_mean"


class ScoringProfile(BaseModel):
    version: str = "1"
    name: str = "default"
    scorers: dict[str, ScorerConfig]
    aggregate: AggregateConfig = Field(default_factory=AggregateConfig)


def load_scoring_profile(path: Path) -> ScoringProfile:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not raw:
        raise ValueError(f"empty scoring profile: {path}")
    scorers_raw = raw.get("scorers") or {}
    scorers: dict[str, ScorerConfig] = {}
    for name, body in scorers_raw.items():
        body = dict(body or {})
        typ = body.pop("type", None)
        if typ is None:
            raise ValueError(f"scorer {name!r} is missing 'type'")
        weight = float(body.pop("weight", 0.0))
        scorers[name] = ScorerConfig(type=typ, weight=weight, extras=body)
    return ScoringProfile(
        version=str(raw.get("version", "1")),
        name=str(raw.get("name", "default")),
        scorers=scorers,
        aggregate=AggregateConfig(**(raw.get("aggregate") or {})),
    )


def profile_tag(profile: ScoringProfile) -> str:
    return f"{profile.name}@v{profile.version}"
