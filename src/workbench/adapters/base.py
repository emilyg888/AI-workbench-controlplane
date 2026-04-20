"""Adapter boundary definitions.

**The LLM contract (design principle 3.5):**

- Input to ``ModelAdapter.generate`` is a validated prompt string. Every
  transformation — retrieval, prompt rendering, policy redaction —
  happens *before* this boundary inside the control plane.
- Output from ``ModelAdapter.generate`` is raw text in ``ModelResult.text``
  plus counters. The model is a **generator only**. Policy enforcement,
  parsing, and response shaping happen *after* this boundary, inside
  the serving layer.
- No adapter may mutate registry state, read other adapters, or make
  decisions about promotion/deployment.

This keeps the probabilistic component (the LLM) strictly sandwiched
between deterministic controls. The workbench's narrative —
*deterministic controls + probabilistic reasoning* — is enforced by
this contract.
"""
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
