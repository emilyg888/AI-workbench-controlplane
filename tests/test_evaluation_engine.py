from __future__ import annotations

import json
from pathlib import Path

import pytest

from workbench import bundle_manager, db, evaluation_engine, experiment_runner
from workbench.models import BundleState


def _run(workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str):
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    return experiment_runner.run_experiment(
        "stub_bundle_v1", tiny_eval_set, root=workbench_root
    )


def test_eval_writes_artifacts_and_transitions(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _run(workbench_root, stub_bundle_spec, tiny_eval_set)
    result = evaluation_engine.evaluate_run(run.run_id, root=workbench_root)

    rd = workbench_root / "runs" / run.run_id
    assert (rd / "metrics.json").exists()
    assert (rd / "scorecard.md").exists()
    assert (rd / "metrics_per_item.jsonl").exists()

    metrics = json.loads((rd / "metrics.json").read_text())
    assert metrics["run_id"] == run.run_id
    assert "aggregate" in metrics
    assert 0 <= result.aggregate <= 1

    b = bundle_manager.get_bundle("stub_bundle_v1", root=workbench_root)
    assert b.state == BundleState.EVALUATED


def test_eval_is_idempotent(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _run(workbench_root, stub_bundle_spec, tiny_eval_set)
    evaluation_engine.evaluate_run(run.run_id, root=workbench_root)
    bundle_manager.transition_bundle(
        "stub_bundle_v1", BundleState.CANDIDATE, root=workbench_root
    )
    # second eval should not blow up; bundle stays candidate
    evaluation_engine.evaluate_run(run.run_id, root=workbench_root)
    b = bundle_manager.get_bundle("stub_bundle_v1", root=workbench_root)
    assert b.state == BundleState.CANDIDATE


def test_duckdb_gets_per_metric_columns(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _run(workbench_root, stub_bundle_spec, tiny_eval_set)
    evaluation_engine.evaluate_run(run.run_id, root=workbench_root)
    con = db.connect(workbench_root)
    row = db.get_run(con, run.run_id)
    con.close()
    assert row["aggregate_score"] is not None
    assert row["scoring_profile"] is not None
    assert row["completeness"] is not None


def test_compare_runs_detects_regression(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    run = _run(workbench_root, stub_bundle_spec, tiny_eval_set)
    evaluation_engine.evaluate_run(run.run_id, root=workbench_root)

    from workbench.comparison import compare
    baseline = json.loads(
        (workbench_root / "runs" / run.run_id / "metrics.json").read_text()
    )
    candidate = dict(baseline)
    candidate = {**baseline, "run_id": "run_cand", "scores": {
        **baseline["scores"], "correctness": baseline["scores"].get("correctness", 1.0) - 0.1
    }}
    report = compare(baseline, candidate)
    assert report.any_regression is True


def test_missing_run_raises(workbench_root: Path) -> None:
    with pytest.raises(FileNotFoundError):
        evaluation_engine.evaluate_run("no_such_run", root=workbench_root)
