from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from workbench import (
    bundle_manager,
    db,
    deployment_state_manager,
    prod_eval,
    runtime_resolver,
)
from workbench.models import BundleState
from workbench.serving.invoke import invoke as invoke_fn


def _approve_and_deploy(workbench_root: Path, stub_bundle_spec: dict) -> str:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    bid = "stub_bundle_v1"
    for s in (BundleState.EVALUATED, BundleState.CANDIDATE, BundleState.APPROVED):
        bundle_manager.transition_bundle(bid, s, root=workbench_root)
    deployment_state_manager.set_active("dev", bid, root=workbench_root)
    runtime_resolver.invalidate_cache()
    return bid


def _seed(con, env: str, bundle_id: str, at: datetime,
          latency: int, policy_action: str = "allow",
          error: str | None = None, input_obj: dict | None = None) -> None:
    import json as _json
    con.execute(
        "INSERT INTO inference_requests "
        "(trace_id, env, bundle_id, request_at, input, output, "
        "latency_ms, policy_action, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            f"t_{at.isoformat()}_{latency}",
            env, bundle_id, at,
            _json.dumps(input_obj or {"question": "hi"}),
            _json.dumps({"text": "answer"}),
            latency, policy_action, error,
        ],
    )


def test_sample_production_writes_jsonl(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    _approve_and_deploy(workbench_root, stub_bundle_spec)
    invoke_fn("dev", {"question": "first"}, root=workbench_root)
    invoke_fn("dev", {"question": "second"}, root=workbench_root)

    out = prod_eval.sample_production("dev", since_hours=1.0,
                                      limit=10, root=workbench_root)
    assert out.exists()
    lines = [line for line in out.read_text().splitlines() if line]
    assert len(lines) == 2


def test_drift_check_flags_latency_spike(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    bid = _approve_and_deploy(workbench_root, stub_bundle_spec)
    con = db.connect(workbench_root)
    now = datetime.now(timezone.utc)
    # baseline window: 5 requests at ~100ms, 2h..23h ago
    for i in range(10):
        _seed(con, "dev", bid, now - timedelta(hours=5 + i),
              latency=100)
    # recent window: 5 requests at ~2000ms in last hour
    for i in range(5):
        _seed(con, "dev", bid, now - timedelta(minutes=10 + i),
              latency=2000)
    con.close()

    report = prod_eval.drift_check(
        "dev", recent_hours=1.0, baseline_hours=24.0,
        root=workbench_root,
    )
    assert report.drifted
    assert any("latency" in r for r in report.drift_reasons)


def test_drift_check_clean_when_steady(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    bid = _approve_and_deploy(workbench_root, stub_bundle_spec)
    con = db.connect(workbench_root)
    now = datetime.now(timezone.utc)
    for i in range(10):
        _seed(con, "dev", bid, now - timedelta(hours=2 + i),
              latency=100)
    for i in range(5):
        _seed(con, "dev", bid, now - timedelta(minutes=10 + i),
              latency=105)
    con.close()

    report = prod_eval.drift_check(
        "dev", recent_hours=1.0, baseline_hours=24.0,
        root=workbench_root,
    )
    assert not report.drifted


def test_drift_check_raises_when_no_active_bundle(
    workbench_root: Path,
) -> None:
    with pytest.raises(ValueError):
        prod_eval.drift_check("dev", root=workbench_root)


def test_drift_check_vs_approval_raises_without_baseline(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    _approve_and_deploy(workbench_root, stub_bundle_spec)
    # manual approve path → no approval_baseline_run_id stamped
    with pytest.raises(ValueError):
        prod_eval.drift_check(
            "dev", vs_approval=True, root=workbench_root,
        )


def test_drift_check_vs_approval_uses_pinned_metrics(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    from workbench import (
        bundle_manager,
        evaluation_engine,
        experiment_runner,
        promotion_engine,
    )
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    run = experiment_runner.run_experiment(
        "stub_bundle_v1", tiny_eval_set, root=workbench_root
    )
    evaluation_engine.evaluate_run(run.run_id, root=workbench_root)
    (workbench_root / "configs" / "promotion_rules.yaml").write_text(
        "version: '1'\nname: default\n"
        "thresholds: {aggregate: 0.0}\n"
        "regression_checks: {enabled: false}\n"
        "approval: {approved_requires: {mode: auto}}\n"
    )
    promotion_engine.propose(run.run_id, root=workbench_root)
    deployment_state_manager.set_active(
        "dev", "stub_bundle_v1", root=workbench_root
    )
    # Now seed only healthy recent traffic matching approval p95 — no drift.
    con = db.connect(workbench_root)
    now = datetime.now(timezone.utc)
    for i in range(5):
        _seed(con, "dev", "stub_bundle_v1", now - timedelta(minutes=10 + i),
              latency=1)
    con.close()
    report = prod_eval.drift_check(
        "dev", vs_approval=True, root=workbench_root,
    )
    assert not report.drifted


def test_approval_metadata_stamped_from_propose(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    from workbench import (
        bundle_manager,
        evaluation_engine,
        experiment_runner,
        promotion_engine,
    )
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    run = experiment_runner.run_experiment(
        "stub_bundle_v1", tiny_eval_set, root=workbench_root
    )
    evaluation_engine.evaluate_run(run.run_id, root=workbench_root)
    (workbench_root / "configs" / "promotion_rules.yaml").write_text(
        "version: '1'\nname: default\n"
        "thresholds: {aggregate: 0.0}\n"
        "regression_checks: {enabled: false}\n"
        "approval: {approved_requires: {mode: auto}}\n"
    )
    promotion_engine.propose(run.run_id, root=workbench_root)
    b = bundle_manager.get_bundle("stub_bundle_v1", root=workbench_root)
    assert b.resolved.approval_baseline_run_id == run.run_id
