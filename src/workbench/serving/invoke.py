"""Runtime plane: synchronous single-shot invocation of a resolved
bundle. Applies input policy → retrieval → prompt render → model
generate → output policy → contract validation, then logs request
telemetry to DuckDB. Never mutates registry state."""
from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .. import db, runtime_resolver
from ..storage import find_workbench_root


def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({"error": "unserialisable"})


def _validate_output(text: str, contract) -> str | None:
    """Return contract violation message if any; else None."""
    if contract.min_output_chars and len(text) < contract.min_output_chars:
        return (f"output below contract min_output_chars="
                f"{contract.min_output_chars}")
    if contract.max_output_chars and len(text) > contract.max_output_chars:
        return (f"output exceeds contract max_output_chars="
                f"{contract.max_output_chars}")
    if contract.required_output_keys:
        try:
            parsed = json.loads(text)
        except Exception:
            return "output not parseable as JSON; contract requires keys"
        if not isinstance(parsed, dict):
            return "output JSON is not an object"
        missing = [k for k in contract.required_output_keys
                   if k not in parsed]
        if missing:
            return f"output missing required keys: {missing}"
    return None


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
    champion = runtime_resolver.resolve(env, root=root)
    challenger_cfg = runtime_resolver.challenger_config(env, root=root)
    challenger = runtime_resolver.resolve_challenger(env, root=root)
    trace_id = _new_trace_id()

    serving_rr = champion
    if challenger and challenger_cfg:
        mode = challenger_cfg.get("mode", "shadow")
        if mode == "traffic_split":
            frac = float(challenger_cfg.get("traffic_fraction", 0.0))
            import hashlib as _h
            bucket = int(_h.md5(trace_id.encode()).hexdigest(), 16) % 100
            if bucket < int(frac * 100):
                serving_rr = challenger
        # shadow mode: champion serves, challenger run async-ish below

    rr = serving_rr
    t0 = time.perf_counter_ns()
    error: str | None = None
    policy_action = "allow"
    output_text = ""
    context_dicts: list[dict] = []

    contract = rr.bundle.components.contract
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
            # Contract: prompt size bound (pre-LLM boundary)
            if contract.max_prompt_chars and len(prompt) > contract.max_prompt_chars:
                policy_action = "input_block"
                output_text = (f"prompt exceeds contract "
                               f"max_prompt_chars={contract.max_prompt_chars}")
            else:
                result = rr.model.generate(
                    prompt, rr.bundle.components.model.params
                )
                post = rr.policy.check_output(result.text)
                if not post.allowed:
                    policy_action = post.action
                    output_text = post.transformed_text
                else:
                    # Contract: output bounds + schema (post-LLM boundary)
                    contract_err = _validate_output(result.text, contract)
                    if contract_err:
                        policy_action = "output_block"
                        output_text = contract_err
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
            "input": _safe_json(user_input),
            "output": _safe_json({"text": output_text}),
            "latency_ms": int(latency_ms),
            "policy_action": policy_action,
            "error": error,
        })
        con.close()
    except Exception:
        pass

    # Shadow-mode: invoke challenger synchronously (local-first = no threads),
    # log the response, keep serving champion's output. Challenger errors are
    # isolated from the user path.
    if (
        challenger
        and challenger_cfg
        and challenger_cfg.get("mode", "shadow") == "shadow"
        and serving_rr is champion
    ):
        try:
            _shadow_invoke(env, challenger, user_input, trace_id, root=root)
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


def _shadow_invoke(
    env: str, rr: "runtime_resolver.ResolvedRuntime",
    user_input: dict, trace_id: str, root: Path | None,
) -> None:
    t0 = time.perf_counter_ns()
    error = None
    action = "allow"
    text = ""
    try:
        body = str(user_input.get("question") or user_input.get("input") or user_input)
        pre = rr.policy.check_input(body)
        if not pre.allowed:
            action, text = pre.action, pre.transformed_text
        else:
            passages = rr.retrieval.retrieve(body, {"top_k": 5})
            ctx = [p.model_dump() for p in passages]
            prompt = _render(rr.prompt_template, user_input, ctx)
            result = rr.model.generate(prompt, rr.bundle.components.model.params)
            post = rr.policy.check_output(result.text)
            action = post.action
            text = post.transformed_text if not post.allowed else result.text
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    latency_ms = max(1, (time.perf_counter_ns() - t0) // 1_000_000)
    try:
        con = db.connect(root or find_workbench_root())
        db.insert_inference(con, {
            "trace_id": trace_id + "_shadow",
            "env": env,
            "bundle_id": rr.bundle.bundle_id,
            "request_at": datetime.now(timezone.utc),
            "input": None, "output": None,
            "latency_ms": int(latency_ms),
            "policy_action": action,
            "error": error,
        })
        con.close()
    except Exception:
        pass
    _ = text  # unused — we don't surface shadow output
