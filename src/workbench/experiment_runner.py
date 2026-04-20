from __future__ import annotations

import logging
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from . import bundle_manager, db
from .adapters.registry import get_model_adapter, get_retrieval_adapter
from .models import utcnow_iso
from .storage import (
    find_workbench_root,
    new_run_dir,
    read_jsonl,
    sha256_file,
    write_json_atomic,
    write_jsonl,
)


class EvalSetNotFoundError(FileNotFoundError):
    pass


class RunResult(BaseModel):
    run_id: str
    bundle_id: str
    eval_set: str
    run_dir: Path
    total_inputs: int
    succeeded: int
    failed: int
    p50_latency_ms: int
    p95_latency_ms: int
    status: str

    model_config = {"arbitrary_types_allowed": True}


def _eval_set_path(root: Path, name: str) -> Path:
    if name.endswith(".jsonl"):
        p = Path(name)
        return p if p.is_absolute() else root / p
    return root / "data" / "eval_sets" / f"{name}.jsonl"


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


def _render_prompt(template: str, user_input: dict, context: list[dict]) -> str:
    ctx_text = "\n".join(f"- {c['text']}" for c in context) if context else ""
    body = user_input.get("question") or user_input.get("input") or str(user_input)
    if "{input}" in template or "{context}" in template:
        return template.replace("{input}", str(body)).replace("{context}", ctx_text)
    return f"{template}\n\nContext:\n{ctx_text}\n\nQuestion: {body}"


def _load_prompt_template(root: Path, ref: str) -> str:
    p = Path(ref)
    if not p.is_absolute():
        p = root / p
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "Answer the question. If context is provided, use it."


def run_experiment(
    bundle_id: str,
    eval_set: str,
    limit: int | None = None,
    root: Path | None = None,
) -> RunResult:
    root = root or find_workbench_root()
    bundle = bundle_manager.get_bundle(bundle_id, root=root)

    eval_path = _eval_set_path(root, eval_set)
    if not eval_path.exists():
        raise EvalSetNotFoundError(f"Eval set not found: {eval_path}")

    examples = list(read_jsonl(eval_path))
    if limit is not None:
        examples = examples[:limit]

    model = get_model_adapter(
        {"provider": bundle.components.model.provider,
         "name": bundle.components.model.name,
         **bundle.components.model.params},
        root=root,
    )
    retrieval = get_retrieval_adapter(
        bundle.components.retrieval.profile_ref,
        root=root,
    )
    prompt_template = _load_prompt_template(root, bundle.components.prompt.template_ref)

    started = datetime.now(timezone.utc)
    run_id, run_dir = new_run_dir(root, bundle_id, now=started)

    log_path = run_dir / "run.log"
    logger = _setup_run_logger(run_id, log_path)

    con = db.connect(root)
    db.insert_run(con, {
        "run_id": run_id,
        "bundle_id": bundle_id,
        "eval_set": eval_set,
        "started_at": started,
        "status": "running",
    })
    con.close()

    write_jsonl(run_dir / "inputs.jsonl", examples)

    predictions: list[dict] = []
    latencies: list[int] = []
    succeeded = 0
    failed = 0
    status = "running"

    try:
        for i, ex in enumerate(examples, start=1):
            input_id = ex.get("input_id", f"ex_{i:04d}")
            try:
                passages = retrieval.retrieve(
                    str(ex.get("input", ex)),
                    {"top_k": 5},
                )
                context = [p.model_dump() for p in passages]
                prompt = _render_prompt(prompt_template, ex.get("input", ex), context)
                t0 = time.perf_counter_ns()
                result = model.generate(prompt, bundle.components.model.params)
                latency_ms = result.latency_ms or max(
                    1, (time.perf_counter_ns() - t0) // 1_000_000
                )
                latencies.append(latency_ms)
                predictions.append({
                    "input_id": input_id,
                    "input": ex.get("input", ex),
                    "output": result.text,
                    "context": context,
                    "latency_ms": latency_ms,
                    "error": None,
                })
                succeeded += 1
                logger.info("[%d/%d] %s ... %dms ✓", i, len(examples), input_id, latency_ms)
            except Exception as exc:
                logger.exception("[%d/%d] %s failed", i, len(examples), input_id)
                predictions.append({
                    "input_id": input_id,
                    "input": ex.get("input", ex),
                    "output": None,
                    "context": [],
                    "latency_ms": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                failed += 1
        status = "completed"
    except KeyboardInterrupt:
        status = "failed"
        logger.warning("Interrupted by user")
    except Exception:
        status = "failed"
        logger.error("Run failed:\n%s", traceback.format_exc())

    finished = datetime.now(timezone.utc)
    write_jsonl(run_dir / "predictions.jsonl", predictions)

    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)
    timings = {
        "run_id": run_id,
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_at": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_inputs": len(examples),
        "succeeded": succeeded,
        "failed": failed,
        "p50_latency_ms": p50,
        "p95_latency_ms": p95,
        "total_wall_ms": int((finished - started).total_seconds() * 1000),
    }
    write_json_atomic(run_dir / "timings.json", timings)

    config = _snapshot_config(bundle, eval_set, eval_path, run_id, model.name, retrieval.name)
    write_json_atomic(run_dir / "config.json", config)

    con = db.connect(root)
    db.update_run(
        con,
        run_id,
        finished_at=finished,
        total_inputs=len(examples),
        succeeded=succeeded,
        failed=failed,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        status=status,
    )
    con.close()

    return RunResult(
        run_id=run_id,
        bundle_id=bundle_id,
        eval_set=eval_set,
        run_dir=run_dir,
        total_inputs=len(examples),
        succeeded=succeeded,
        failed=failed,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        status=status,
    )


def _snapshot_config(bundle, eval_set: str, eval_path: Path, run_id: str,
                     model_name: str, retrieval_name: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "bundle": bundle.model_dump(mode="json"),
        "eval_set": {
            "name": eval_set,
            "path": str(eval_path),
            "sha256": sha256_file(eval_path) if eval_path.exists() else None,
        },
        "adapters": {"model": model_name, "retrieval": retrieval_name},
        "python_version": sys.version.split()[0],
        "snapshot_at": utcnow_iso(),
    }


def _setup_run_logger(run_id: str, log_path: Path) -> logging.Logger:
    lg = logging.getLogger(f"workbench.run.{run_id}")
    lg.setLevel(logging.INFO)
    lg.propagate = False
    for h in list(lg.handlers):
        lg.removeHandler(h)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    lg.addHandler(fh)
    return lg
