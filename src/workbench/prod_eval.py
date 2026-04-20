"""Production eval loop: materialise served traffic into eval sets and
detect drift against a baseline window.

Closes the loop between runtime logging (Phase 6 ``inference_requests``)
and the scoring pipeline (Phase 3). Since live traffic has no ground
truth, drift here is label-free: latency shift, error rate shift,
policy-block rate shift.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from . import db, deployment_state_manager
from .storage import find_workbench_root, write_jsonl


class WindowStats(BaseModel):
    window_hours: float
    since: str
    until: str
    total: int
    errors: int
    error_rate: float
    p50_latency_ms: int
    p95_latency_ms: int
    policy_block_rate: float


class DriftReport(BaseModel):
    env: str
    bundle_id: str
    recent: WindowStats
    baseline: WindowStats
    deltas: dict[str, float]
    drifted: bool
    drift_reasons: list[str]


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


def _stats(con, env: str, bundle_id: str,
           since: datetime, until: datetime) -> WindowStats:
    rows = con.execute(
        "SELECT latency_ms, policy_action, error FROM inference_requests "
        "WHERE env = ? AND bundle_id = ? "
        "AND request_at >= ? AND request_at < ?",
        [env, bundle_id, since, until],
    ).fetchall()
    total = len(rows)
    lats = [r[0] for r in rows if r[0] is not None]
    errs = sum(1 for r in rows if r[2])
    blocks = sum(1 for r in rows if r[1] and "block" in r[1])
    return WindowStats(
        window_hours=(until - since).total_seconds() / 3600,
        since=since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        until=until.strftime("%Y-%m-%dT%H:%M:%SZ"),
        total=total,
        errors=errs,
        error_rate=(errs / total) if total else 0.0,
        p50_latency_ms=_percentile(lats, 50),
        p95_latency_ms=_percentile(lats, 95),
        policy_block_rate=(blocks / total) if total else 0.0,
    )


def sample_production(
    env: str,
    since_hours: float = 24.0,
    limit: int | None = 100,
    output: Path | None = None,
    root: Path | None = None,
) -> Path:
    """Dump a JSONL eval set from recent inference_requests for this env.

    The output matches the Phase 2 eval-set schema (``input_id``,
    ``input``, optional ``expected``) with ``expected`` omitted since
    production traffic is unlabelled.
    """
    root = root or find_workbench_root()
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=since_hours)
    con = db.connect(root)
    q = ("SELECT trace_id, input FROM inference_requests "
         "WHERE env = ? AND request_at >= ? "
         "ORDER BY request_at DESC")
    params = [env, since]
    if limit:
        q += " LIMIT ?"
        params.append(limit)
    rows = con.execute(q, params).fetchall()
    con.close()

    records: list[dict] = []
    for trace_id, input_json in rows:
        try:
            payload = json.loads(input_json) if input_json else {}
        except Exception:
            continue
        records.append({
            "input_id": trace_id,
            "input": payload,
            "tags": ["production"],
        })
    output = output or (root / "data" / "eval_sets" /
                        f"prod_{env}_{now.strftime('%Y%m%dT%H%M%SZ')}.jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(output, records)
    return output


def drift_check(
    env: str,
    recent_hours: float = 1.0,
    baseline_hours: float = 24.0,
    error_rate_threshold: float = 0.05,
    latency_p95_pct_threshold: float = 0.25,
    block_rate_threshold: float = 0.05,
    root: Path | None = None,
) -> DriftReport:
    """Compare the most recent window against the preceding baseline window
    for the env's active bundle. Returns a DriftReport with flags.
    """
    root = root or find_workbench_root()
    dep = deployment_state_manager.get_active_full(env, root=root)
    if dep.active_bundle_id is None:
        raise ValueError(f"no active bundle in env={env!r}")

    now = datetime.now(timezone.utc)
    recent_since = now - timedelta(hours=recent_hours)
    baseline_until = recent_since
    baseline_since = baseline_until - timedelta(hours=baseline_hours)

    con = db.connect(root)
    recent = _stats(con, env, dep.active_bundle_id, recent_since, now)
    baseline = _stats(con, env, dep.active_bundle_id, baseline_since,
                      baseline_until)
    con.close()

    reasons: list[str] = []
    deltas = {
        "error_rate": recent.error_rate - baseline.error_rate,
        "policy_block_rate":
            recent.policy_block_rate - baseline.policy_block_rate,
        "p95_latency_ms":
            recent.p95_latency_ms - baseline.p95_latency_ms,
    }
    if deltas["error_rate"] > error_rate_threshold:
        reasons.append(
            f"error_rate up by {deltas['error_rate']:+.3f}"
        )
    if deltas["policy_block_rate"] > block_rate_threshold:
        reasons.append(
            f"policy_block_rate up by {deltas['policy_block_rate']:+.3f}"
        )
    if baseline.p95_latency_ms > 0:
        pct = deltas["p95_latency_ms"] / baseline.p95_latency_ms
        if pct > latency_p95_pct_threshold:
            reasons.append(f"p95 latency up by {pct:+.1%}")
    return DriftReport(
        env=env,
        bundle_id=dep.active_bundle_id,
        recent=recent,
        baseline=baseline,
        deltas=deltas,
        drifted=bool(reasons),
        drift_reasons=reasons,
    )
