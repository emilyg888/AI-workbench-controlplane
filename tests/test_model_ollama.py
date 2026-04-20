from __future__ import annotations

import httpx
import respx

from workbench.adapters.model_ollama import OllamaError, OllamaModelAdapter


def test_ollama_success(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    with respx.mock(base_url="http://localhost:11434") as router:
        router.post("/api/generate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "response": "hello",
                    "prompt_eval_count": 3,
                    "eval_count": 1,
                },
            )
        )
        a = OllamaModelAdapter({"name": "llama3.1-8b"})
        r = a.generate("hi", {"temperature": 0.2})
        assert r.text == "hello"
        assert r.tokens_in == 3
        assert r.tokens_out == 1


def test_ollama_retries_on_503(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    with respx.mock(base_url="http://localhost:11434") as router:
        route = router.post("/api/generate").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(200, json={"response": "ok"}),
            ]
        )
        a = OllamaModelAdapter({"name": "llama3.1-8b", "max_retries": 3,
                                "timeout_seconds": 5})
        r = a.generate("hi", {})
        assert r.text == "ok"
        assert route.call_count == 3


def test_ollama_fails_after_retries(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    with respx.mock(base_url="http://localhost:11434") as router:
        router.post("/api/generate").mock(return_value=httpx.Response(503))
        a = OllamaModelAdapter({"name": "llama3.1-8b", "max_retries": 2,
                                "timeout_seconds": 5})
        import pytest
        with pytest.raises(OllamaError):
            a.generate("hi", {})
