from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .. import db, runtime_resolver
from ..storage import find_workbench_root


class InvokeResult(BaseModel):
    output: str
    context: list[dict]
    bundle_id: str
    trace_id: str
    latency_ms: int
    policy_action: str
    error: str | None = None


def _new_trace_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"inv_{ts}_{secrets.token_hex(3)}"


def _render(template: str, user_input: dict, context: list[dict]) -> str:
    body = user_input.get("question") or user_input.get("input") or str(user_input)
    ctx_text = "\n".join(f"- {c.get('text', '')}" for c in context)
    if "{input}" in template or "{context}" in template:
        return template.replace("{input}", str(body)).replace("{context}", ctx_text)
    return f"{template}\n\nContext:\n{ctx_text}\n\nQuestion: {body}"


def invoke(
    env: str, user_input: dict[str, Any], root: Path | None = None
) -> InvokeResult:
    rr = runtime_resolver.resolve(env, root=root)
    trace_id = _new_trace_id()
    t0 = time.perf_counter_ns()
    error: str | None = None
    policy_action = "allow"
    output_text = ""
    context_dicts: list[dict] = []

    try:
        input_body = str(user_input.get("question") or user_input.get("input") or user_input)
        pre = rr.policy.check_input(input_body)
        if not pre.allowed:
            policy_action = pre.action
            output_text = pre.transformed_text
        else:
            safe_input = dict(user_input)
            if pre.action == "input_redact":
                safe_input["question"] = pre.transformed_text
            passages = rr.retrieval.retrieve(input_body, {"top_k": 5})
            context_dicts = [p.model_dump() for p in passages]
            prompt = _render(rr.prompt_template, safe_input, context_dicts)
            result = rr.model.generate(prompt, rr.bundle.components.model.params)
            post = rr.policy.check_output(result.text)
            if not post.allowed:
                policy_action = post.action
                output_text = post.transformed_text
            else:
                output_text = result.text
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    latency_ms = max(1, (time.perf_counter_ns() - t0) // 1_000_000)

    try:
        con = db.connect(root or find_workbench_root())
        db.insert_inference(con, {
            "trace_id": trace_id,
            "env": env,
            "bundle_id": rr.bundle.bundle_id,
            "request_at": datetime.now(timezone.utc),
            "input": None,
            "output": None,
            "latency_ms": int(latency_ms),
            "policy_action": policy_action,
            "error": error,
        })
        con.close()
    except Exception:
        pass

    return InvokeResult(
        output=output_text,
        context=context_dicts,
        bundle_id=rr.bundle.bundle_id,
        trace_id=trace_id,
        latency_ms=int(latency_ms),
        policy_action=policy_action,
        error=error,
    )
