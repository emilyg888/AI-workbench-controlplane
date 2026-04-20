"""LM Studio model adapter (OpenAI-compatible local API).

LM Studio exposes ``POST /v1/chat/completions`` on a local port
(default 1234). We keep the surface tiny — one request per call, no
streaming — and let LM Studio handle model loading. The model name in
the bundle spec is passed through verbatim.
"""
from __future__ import annotations

import os
import time

import httpx

from .base import ModelResult

DEFAULT_BASE = "http://localhost:1234"


class LMStudioError(RuntimeError):
    pass


class LMStudioModelAdapter:
    name = "lmstudio"

    def __init__(self, spec: dict) -> None:
        self.spec = spec
        self.model = spec.get("name", "local-model")
        self.base = os.environ.get("LMSTUDIO_HOST", DEFAULT_BASE).rstrip("/")
        self.timeout = float(spec.get("timeout_seconds", 60))
        self.max_retries = int(spec.get("max_retries", 2))

    def generate(self, prompt: str, params: dict) -> ModelResult:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": params.get("temperature", 0.2),
            "max_tokens": params.get("max_tokens", 1024),
            "stream": False,
        }
        url = f"{self.base}/v1/chat/completions"
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            t0 = time.perf_counter_ns()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    r = client.post(url, json=payload)
                r.raise_for_status()
                body = r.json()
                latency_ms = max(1, (time.perf_counter_ns() - t0) // 1_000_000)
                choices = body.get("choices") or []
                text = ""
                if choices:
                    text = choices[0].get("message", {}).get("content", "") or ""
                usage = body.get("usage") or {}
                return ModelResult(
                    text=text,
                    tokens_in=usage.get("prompt_tokens"),
                    tokens_out=usage.get("completion_tokens"),
                    latency_ms=int(latency_ms),
                    raw=body,
                )
            except httpx.HTTPStatusError as e:
                last_exc = e
                if e.response.status_code < 500:
                    break
                time.sleep(min(2 ** attempt, 5))
            except httpx.RequestError as e:
                last_exc = e
                time.sleep(min(2 ** attempt, 5))
        raise LMStudioError(f"LM Studio request failed: {last_exc}")
