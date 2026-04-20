from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class Prediction(BaseModel):
    input_id: str
    input: Any = None
    output: str | None = None
    context: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None


class EvalExample(BaseModel):
    input_id: str
    input: Any = None
    expected: Any = None
    tags: list[str] = Field(default_factory=list)


class ScorerResult(BaseModel):
    name: str
    value: float
    per_item: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None


class Scorer(Protocol):
    name: str

    def score(
        self,
        predictions: list[Prediction],
        eval_set: list[EvalExample],
        profile: dict[str, Any],
    ) -> ScorerResult: ...


_REGISTRY: dict[str, type] = {}


def register_scorer(type_key: str):
    def deco(cls):
        _REGISTRY[type_key] = cls
        return cls
    return deco


def get_scorer(type_key: str) -> type:
    try:
        return _REGISTRY[type_key]
    except KeyError:
        raise KeyError(
            f"no scorer registered for type={type_key!r}. "
            f"known: {sorted(_REGISTRY)}"
        ) from None


def _by_id(examples: list[EvalExample]) -> dict[str, EvalExample]:
    return {e.input_id: e for e in examples}
