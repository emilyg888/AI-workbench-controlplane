from __future__ import annotations

import httpx
import respx

from workbench.adapters.model_lmstudio import LMStudioError, LMStudioModelAdapter


def test_lmstudio_success(monkeypatch) -> None:
    monkeypatch.setenv("LMSTUDIO_HOST", "http://localhost:1234")
    with respx.mock(base_url="http://localhost:1234") as router:
        router.post("/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"role": "assistant", "content": "ok"}}
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 1},
                },
            )
        )
        a = LMStudioModelAdapter({"name": "qwen2.5-14b-instruct"})
        r = a.generate("hi", {"temperature": 0.2})
        assert r.text == "ok"
        assert r.tokens_in == 4
        assert r.tokens_out == 1


def test_lmstudio_retries_on_503(monkeypatch) -> None:
    monkeypatch.setenv("LMSTUDIO_HOST", "http://localhost:1234")
    with respx.mock(base_url="http://localhost:1234") as router:
        route = router.post("/v1/chat/completions").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json={
                    "choices": [
                        {"message": {"role": "assistant", "content": "ok"}}
                    ],
                    "usage": {},
                }),
            ]
        )
        a = LMStudioModelAdapter({
            "name": "qwen2.5-14b-instruct",
            "max_retries": 2,
            "timeout_seconds": 5,
        })
        r = a.generate("hi", {})
        assert r.text == "ok"
        assert route.call_count == 2


def test_lmstudio_fails_after_retries(monkeypatch) -> None:
    monkeypatch.setenv("LMSTUDIO_HOST", "http://localhost:1234")
    with respx.mock(base_url="http://localhost:1234") as router:
        router.post("/v1/chat/completions").mock(
            return_value=httpx.Response(503)
        )
        a = LMStudioModelAdapter({
            "name": "qwen2.5-14b-instruct",
            "max_retries": 2,
            "timeout_seconds": 5,
        })
        import pytest
        with pytest.raises(LMStudioError):
            a.generate("hi", {})
