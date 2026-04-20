from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from . import db
from .storage import find_workbench_root


class BundleStats(BaseModel):
    bundle_id: str
    total: int
    errors: int
    p50_latency_ms: int
    p95_latency_ms: int
    policy_block_rate: float


class RuntimeCompareReport(BaseModel):
    env: str
    window_hours: float
    champion: BundleStats | None
    challenger: BundleStats | None


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


def _stats_for(con, env: str, bundle_id: str, since: datetime) -> BundleStats:
    rows = con.execute(
        "SELECT latency_ms, policy_action, error FROM inference_requests "
        "WHERE env = ? AND bundle_id = ? AND request_at >= ?",
        [env, bundle_id, since],
    ).fetchall()
    lats = [r[0] for r in rows if r[0] is not None]
    errors = sum(1 for r in rows if r[2])
    blocks = sum(1 for r in rows if r[1] and "block" in r[1])
    return BundleStats(
        bundle_id=bundle_id,
        total=len(rows),
        errors=errors,
        p50_latency_ms=_percentile(lats, 50),
        p95_latency_ms=_percentile(lats, 95),
        policy_block_rate=(blocks / len(rows)) if rows else 0.0,
    )


def compare_env(
    env: str,
    champion_bundle_id: str,
    challenger_bundle_id: str | None,
    window_hours: float = 24.0,
    root: Path | None = None,
) -> RuntimeCompareReport:
    root = root or find_workbench_root()
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    con = db.connect(root)
    champ = _stats_for(con, env, champion_bundle_id, since)
    chall = (_stats_for(con, env, challenger_bundle_id, since)
             if challenger_bundle_id else None)
    con.close()
    return RuntimeCompareReport(
        env=env, window_hours=window_hours,
        champion=champ, challenger=chall,
    )
