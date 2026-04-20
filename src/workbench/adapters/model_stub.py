from __future__ import annotations

import time

from .base import ModelResult


class StubModelAdapter:
    """Deterministic echo adapter for tests. Returns the prompt, prefixed."""

    name = "stub"

    def generate(self, prompt: str, params: dict) -> ModelResult:
        t0 = time.perf_counter_ns()
        text = f"[stub] {prompt[:200]}"
        latency_ms = max(1, (time.perf_counter_ns() - t0) // 1_000_000)
        return ModelResult(
            text=text,
            tokens_in=len(prompt.split()),
            tokens_out=len(text.split()),
            latency_ms=latency_ms,
            raw={"provider": "stub", "params": params},
        )
