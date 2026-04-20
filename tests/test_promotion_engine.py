from __future__ import annotations

import json
from pathlib import Path

import pytest

from workbench import (
    bundle_manager,
    evaluation_engine,
    experiment_runner,
    promotion_engine,
)
from workbench.models import BundleState


def _setup_scored_bundle(workbench_root: Path, stub_bundle_spec: dict,
                         tiny_eval_set: str):
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    run = experiment_runner.run_experiment(
        "stub_bundle_v1", tiny_eval_set, root=workbench_root
    )
    evaluation_engine.evaluate_run(run.run_id, root=workbench_root)
    return run


def _install_rules(workbench_root: Path, **thresholds: float) -> None:
    path = workbench_root / "configs" / "promotion_rules.yaml"
    yaml = [
        "version: '1'",
        "name: default",
        "thresholds:",
    ]
    for k, v in thresholds.items():
        yaml.append(f"  {k}: {v}")
    yaml += [
        "regression_checks:",
        "  enabled: false",
        "approval:",
        "  approved_requires:",
        "    mode: auto",
    ]
    path.write_text("\n".join(yaml))


def test_propose_approves_when_all_thresholds_pass(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _setup_scored_bundle(workbench_root, stub_bundle_spec, tiny_eval_set)
    _install_rules(workbench_root, aggregate=0.0)
    decision = promotion_engine.propose(run.run_id, root=workbench_root)
    assert decision.result == "approved"
    b = bundle_manager.get_bundle("stub_bundle_v1", root=workbench_root)
    assert b.state == BundleState.APPROVED


def test_propose_rejects_when_threshold_fails(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _setup_scored_bundle(workbench_root, stub_bundle_spec, tiny_eval_set)
    _install_rules(workbench_root, aggregate=0.99)
    decision = promotion_engine.propose(run.run_id, root=workbench_root)
    assert decision.result == "rejected"
    b = bundle_manager.get_bundle("stub_bundle_v1", root=workbench_root)
    assert b.state == BundleState.REJECTED


def test_promotion_log_append_only(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _setup_scored_bundle(workbench_root, stub_bundle_spec, tiny_eval_set)
    _install_rules(workbench_root, aggregate=0.99)  # will reject
    promotion_engine.propose(run.run_id, root=workbench_root)
    log = promotion_engine.read_log(root=workbench_root)
    assert len(log) == 1
    assert log[0]["result"] == "rejected"

    # create a second bundle that gets approved; log grows
    spec2 = {**stub_bundle_spec, "name": "other_bundle", "version": "1.0.0"}
    bundle_manager.create_bundle(spec2, root=workbench_root)
    run2 = experiment_runner.run_experiment(
        "other_bundle_v1", tiny_eval_set, root=workbench_root
    )
    evaluation_engine.evaluate_run(run2.run_id, root=workbench_root)
    _install_rules(workbench_root, aggregate=0.0)
    promotion_engine.propose(run2.run_id, root=workbench_root)
    log2 = promotion_engine.read_log(root=workbench_root)
    assert len(log2) == 2  # append-only: prior entries preserved


def test_manual_approve_requires_candidate_state(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _setup_scored_bundle(workbench_root, stub_bundle_spec, tiny_eval_set)
    # install manual approval rules so proposal leaves bundle in candidate
    (workbench_root / "configs" / "promotion_rules.yaml").write_text(
        "version: '1'\nname: default\n"
        "thresholds: {aggregate: 0.0}\n"
        "regression_checks: {enabled: false}\n"
        "approval: {approved_requires: {mode: manual}}\n"
    )
    decision = promotion_engine.propose(run.run_id, root=workbench_root)
    assert decision.result == "candidate"
    b = bundle_manager.get_bundle("stub_bundle_v1", root=workbench_root)
    assert b.state == BundleState.CANDIDATE

    approved = promotion_engine.approve(
        "stub_bundle_v1", approver="human", root=workbench_root
    )
    assert approved.result == "approved"


def test_evidence_artifacts_written(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _setup_scored_bundle(workbench_root, stub_bundle_spec, tiny_eval_set)
    _install_rules(workbench_root, aggregate=0.0)
    promotion_engine.propose(run.run_id, root=workbench_root)
    rd = workbench_root / "runs" / run.run_id
    assert (rd / "promotion_decision.json").exists()
    assert (rd / "promotion_report.md").exists()


def test_regression_strict_metric_fails_even_tiny_drop(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    # Build candidate run (stub bundle)
    run = _setup_scored_bundle(workbench_root, stub_bundle_spec, tiny_eval_set)
    # Construct a baseline metrics file and wire deployments.json to point to it
    baseline_metrics = {
        "run_id": "baseline_run",
        "bundle_id": "baseline_bundle_v1",
        "scoring_profile": "default@v1",
        "scored_at": "2026-04-19T00:00:00Z",
        "scores": {"policy_compliance": 1.0, "completeness": 1.0},
        "aggregate": 1.0,
    }
    (workbench_root / "runs" / "baseline_run").mkdir()
    (workbench_root / "runs" / "baseline_run" / "metrics.json").write_text(
        json.dumps(baseline_metrics)
    )

    # Make candidate's policy_compliance strictly lower
    cand_path = workbench_root / "runs" / run.run_id / "metrics.json"
    cand = json.loads(cand_path.read_text())
    cand["scores"]["policy_compliance"] = 0.99
    cand_path.write_text(json.dumps(cand))

    (workbench_root / "configs" / "promotion_rules.yaml").write_text(
        "version: '1'\nname: default\n"
        "thresholds: {aggregate: 0.0}\n"
        "regression_checks:\n"
        "  enabled: true\n"
        "  baseline: baseline_run\n"
        "  max_absolute_drop: 0.5\n"
        "  strict_metrics: [policy_compliance]\n"
        "approval: {approved_requires: {mode: auto}}\n"
    )
    decision = promotion_engine.propose(run.run_id, root=workbench_root)
    assert decision.result == "rejected"
    assert decision.checks.regression["violations"]
