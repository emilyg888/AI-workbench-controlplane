"""Runtime plane: FastAPI HTTP surface over ``serving.invoke``. Read-only
against the registry; does not mutate."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .. import runtime_resolver
from .invoke import invoke as _invoke


class InvokeRequest(BaseModel):
    input: dict[str, Any]


def create_app(env: str, root: Path | None = None) -> FastAPI:
    app = FastAPI(title="AI Workbench")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/active")
    def active() -> dict[str, Any]:
        try:
            rr = runtime_resolver.resolve(env, root=root)
        except runtime_resolver.NoActiveBundleError as e:
            raise HTTPException(status_code=503, detail=str(e)) from None
        return {
            "env": env,
            "bundle_id": rr.bundle.bundle_id,
            "activated_at": rr.activated_at,
            "model": rr.model.name,
            "retrieval": rr.retrieval.name,
        }

    @app.post("/v1/invoke")
    def invoke_endpoint(req: InvokeRequest) -> dict[str, Any]:
        try:
            result = _invoke(env, req.input, root=root)
        except runtime_resolver.NoActiveBundleError as e:
            raise HTTPException(status_code=503, detail=str(e)) from None
        return result.model_dump(mode="json")

    return app


def run_server(env: str, host: str = "127.0.0.1", port: int = 8080,
               root: Path | None = None) -> None:
    import uvicorn

    app = create_app(env, root=root)
    uvicorn.run(app, host=host, port=port, log_level="info")


def env_host_port() -> tuple[str, int]:
    host = os.environ.get("WORKBENCH_SERVE_HOST", "127.0.0.1")
    port = int(os.environ.get("WORKBENCH_SERVE_PORT", "8080"))
    return host, port
