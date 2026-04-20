from __future__ import annotations

import json
from pathlib import Path

import pytest

from workbench import bundle_manager, db, experiment_runner


def test_end_to_end_stub_run(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    result = experiment_runner.run_experiment(
        "stub_bundle_v1", tiny_eval_set, root=workbench_root
    )

    assert result.total_inputs == 3
    assert result.succeeded == 3
    assert result.failed == 0
    assert result.status == "completed"

    for name in ("config.json", "inputs.jsonl", "predictions.jsonl",
                 "timings.json", "run.log"):
        assert (result.run_dir / name).exists(), name

    preds = [json.loads(l) for l in (result.run_dir / "predictions.jsonl").read_text().splitlines() if l]
    assert len(preds) == 3
    assert all(p["error"] is None for p in preds)
    assert all(p["output"] is not None for p in preds)


def test_run_row_in_duckdb(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    result = experiment_runner.run_experiment(
        "stub_bundle_v1", tiny_eval_set, root=workbench_root
    )
    con = db.connect(workbench_root)
    row = db.get_run(con, result.run_id)
    con.close()
    assert row is not None
    assert row["status"] == "completed"
    assert row["total_inputs"] == 3


def test_limit_truncates(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    result = experiment_runner.run_experiment(
        "stub_bundle_v1", tiny_eval_set, limit=2, root=workbench_root
    )
    assert result.total_inputs == 2
    assert result.succeeded == 2


def test_missing_bundle_raises(workbench_root: Path, tiny_eval_set: str) -> None:
    with pytest.raises(bundle_manager.BundleNotFoundError):
        experiment_runner.run_experiment("nope_v1", tiny_eval_set, root=workbench_root)


def test_missing_eval_set_raises(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    with pytest.raises(experiment_runner.EvalSetNotFoundError):
        experiment_runner.run_experiment(
            "stub_bundle_v1", "does_not_exist", root=workbench_root
        )


def test_config_json_captures_bundle(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    result = experiment_runner.run_experiment(
        "stub_bundle_v1", tiny_eval_set, root=workbench_root
    )
    config = json.loads((result.run_dir / "config.json").read_text())
    assert config["bundle"]["bundle_id"] == "stub_bundle_v1"
    assert config["adapters"]["model"] == "stub"
    assert config["eval_set"]["sha256"] is not None
