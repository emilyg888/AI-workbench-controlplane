from __future__ import annotations

import json
from pathlib import Path

from workbench import (
    bundle_manager,
    evaluation_engine,
    experiment_runner,
    promotion_engine,
)
from workbench.models import BundleState


def _setup_scored(workbench_root: Path, stub_bundle_spec: dict,
                  tiny_eval_set: str):
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    run = experiment_runner.run_experiment(
        "stub_bundle_v1", tiny_eval_set, root=workbench_root
    )
    evaluation_engine.evaluate_run(run.run_id, root=workbench_root)
    return run


def test_must_pass_rejects_when_condition_fails(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _setup_scored(workbench_root, stub_bundle_spec, tiny_eval_set)
    # Force a metric value the must_pass expression will fail
    metrics_path = workbench_root / "runs" / run.run_id / "metrics.json"
    data = json.loads(metrics_path.read_text())
    data["scores"]["policy_compliance"] = 0.95
    metrics_path.write_text(json.dumps(data))

    (workbench_root / "configs" / "promotion_rules.yaml").write_text(
        "version: '1'\nname: default\n"
        "thresholds: {aggregate: 0.0}\n"
        "must_pass: ['policy_compliance == 1.0']\n"
        "regression_checks: {enabled: false}\n"
        "approval: {approved_requires: {mode: auto}}\n"
    )
    decision = promotion_engine.propose(run.run_id, root=workbench_root)
    assert decision.result == "rejected"
    assert decision.checks.must_pass, "expected must_pass violations in decision"
    b = bundle_manager.get_bundle("stub_bundle_v1", root=workbench_root)
    assert b.state == BundleState.REJECTED


def test_must_pass_accepts_when_all_pass(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _setup_scored(workbench_root, stub_bundle_spec, tiny_eval_set)
    metrics_path = workbench_root / "runs" / run.run_id / "metrics.json"
    data = json.loads(metrics_path.read_text())
    data["scores"]["policy_compliance"] = 1.0
    metrics_path.write_text(json.dumps(data))

    (workbench_root / "configs" / "promotion_rules.yaml").write_text(
        "version: '1'\nname: default\n"
        "thresholds: {aggregate: 0.0}\n"
        "must_pass: ['policy_compliance == 1.0', 'aggregate >= 0.0']\n"
        "regression_checks: {enabled: false}\n"
        "approval: {approved_requires: {mode: auto}}\n"
    )
    decision = promotion_engine.propose(run.run_id, root=workbench_root)
    assert decision.result == "approved"
    assert decision.checks.must_pass == []


def test_must_pass_supports_or_expressions(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _setup_scored(workbench_root, stub_bundle_spec, tiny_eval_set)
    metrics_path = workbench_root / "runs" / run.run_id / "metrics.json"
    data = json.loads(metrics_path.read_text())
    data["scores"]["correctness"] = 0.5
    data["scores"]["refusal_quality"] = 0.99
    metrics_path.write_text(json.dumps(data))

    # OR expression: high refusal_quality alone should satisfy
    (workbench_root / "configs" / "promotion_rules.yaml").write_text(
        "version: '1'\nname: default\n"
        "thresholds: {aggregate: 0.0}\n"
        "must_pass:\n"
        "  - '(correctness >= 0.9) or (refusal_quality >= 0.95)'\n"
        "regression_checks: {enabled: false}\n"
        "approval: {approved_requires: {mode: auto}}\n"
    )
    decision = promotion_engine.propose(run.run_id, root=workbench_root)
    assert decision.result == "approved"


def test_must_pass_or_fails_when_both_sides_miss(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _setup_scored(workbench_root, stub_bundle_spec, tiny_eval_set)
    metrics_path = workbench_root / "runs" / run.run_id / "metrics.json"
    data = json.loads(metrics_path.read_text())
    data["scores"]["correctness"] = 0.5
    data["scores"]["refusal_quality"] = 0.5
    metrics_path.write_text(json.dumps(data))

    (workbench_root / "configs" / "promotion_rules.yaml").write_text(
        "version: '1'\nname: default\n"
        "thresholds: {aggregate: 0.0}\n"
        "must_pass:\n"
        "  - '(correctness >= 0.9) or (refusal_quality >= 0.95)'\n"
        "regression_checks: {enabled: false}\n"
        "approval: {approved_requires: {mode: auto}}\n"
    )
    decision = promotion_engine.propose(run.run_id, root=workbench_root)
    assert decision.result == "rejected"
    assert decision.checks.must_pass


def test_weighted_metrics_overrides_aggregate_gate(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _setup_scored(workbench_root, stub_bundle_spec, tiny_eval_set)
    metrics_path = workbench_root / "runs" / run.run_id / "metrics.json"
    data = json.loads(metrics_path.read_text())
    # eval aggregate low; but the weighted subset (policy + refusal) is high
    data["aggregate"] = 0.3
    data["scores"]["policy_compliance"] = 1.0
    data["scores"]["refusal_quality"] = 1.0
    metrics_path.write_text(json.dumps(data))

    (workbench_root / "configs" / "promotion_rules.yaml").write_text(
        "version: '1'\nname: default\n"
        "thresholds: {aggregate: 0.9}\n"
        "weighted_metrics: {policy_compliance: 0.5, refusal_quality: 0.5}\n"
        "regression_checks: {enabled: false}\n"
        "approval: {approved_requires: {mode: auto}}\n"
    )
    decision = promotion_engine.propose(run.run_id, root=workbench_root)
    assert decision.result == "approved"
    assert decision.checks.promotion_aggregate == 1.0


def test_guardrails_max_failures_per_tag(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    # Build an eval set with explicit tags, half failing
    eval_path = workbench_root / "data" / "eval_sets" / "tagged.jsonl"
    eval_path.write_text(
        '{"input_id": "a", "input": {"question": "x"}, "expected": "wrong", "tags": ["safety"]}\n'
        '{"input_id": "b", "input": {"question": "x"}, "expected": "wrong", "tags": ["safety"]}\n'
        '{"input_id": "c", "input": {"question": "x"}, "expected": "wrong", "tags": ["general"]}\n'
    )
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    run = experiment_runner.run_experiment(
        "stub_bundle_v1", "tagged", root=workbench_root
    )
    evaluation_engine.evaluate_run(run.run_id, root=workbench_root)

    # Stub always mismatches expected → every exact_match per_item is 0,
    # so 2 items tagged safety fail.
    (workbench_root / "configs" / "promotion_rules.yaml").write_text(
        "version: '1'\nname: default\n"
        "thresholds: {aggregate: 0.0}\n"
        "guardrails: {max_failures_per_tag: {safety: 0}}\n"
        "regression_checks: {enabled: false}\n"
        "approval: {approved_requires: {mode: auto}}\n"
    )
    decision = promotion_engine.propose(run.run_id, root=workbench_root)
    assert decision.result == "rejected"
    assert decision.checks.guardrails["violations"], \
        "expected guardrail violations"
    assert any(v["tag"] == "safety"
               for v in decision.checks.guardrails["violations"])
