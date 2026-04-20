from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class ModelResult(BaseModel):
    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int
    raw: dict[str, Any] = {}


class Passage(BaseModel):
    id: str
    text: str
    score: float = 0.0
    metadata: dict[str, Any] = {}


class ModelAdapter(Protocol):
    name: str

    def generate(self, prompt: str, params: dict) -> ModelResult: ...


class RetrievalAdapter(Protocol):
    name: str

    def retrieve(self, query: str, profile: dict) -> list[Passage]: ...
