from __future__ import annotations

import os
import time

import httpx

from .base import ModelResult

DEFAULT_BASE = "http://localhost:11434"


class OllamaError(RuntimeError):
    pass


class OllamaModelAdapter:
    """Calls a local Ollama server over HTTP. Retries transient errors."""

    name = "ollama"

    def __init__(self, spec: dict) -> None:
        self.spec = spec
        self.model = spec.get("name", "llama3.1-8b")
        self.base = os.environ.get("OLLAMA_HOST", DEFAULT_BASE).rstrip("/")
        self.timeout = float(spec.get("timeout_seconds", 30))
        self.max_retries = int(spec.get("max_retries", 3))

    def generate(self, prompt: str, params: dict) -> ModelResult:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": params.get("temperature", 0.2),
                "num_predict": params.get("max_tokens", 1024),
            },
        }
        url = f"{self.base}/api/generate"
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            t0 = time.perf_counter_ns()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    r = client.post(url, json=payload)
                r.raise_for_status()
                body = r.json()
                latency_ms = max(1, (time.perf_counter_ns() - t0) // 1_000_000)
                return ModelResult(
                    text=str(body.get("response", "")),
                    tokens_in=body.get("prompt_eval_count"),
                    tokens_out=body.get("eval_count"),
                    latency_ms=int(latency_ms),
                    raw=body,
                )
            except httpx.HTTPStatusError as e:
                last_exc = e
                if e.response.status_code < 500:
                    break  # don't retry on 4xx
                time.sleep(min(2 ** attempt, 5))
            except httpx.RequestError as e:
                last_exc = e
                time.sleep(min(2 ** attempt, 5))
        raise OllamaError(f"Ollama generate failed after retries: {last_exc}")
