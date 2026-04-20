from __future__ import annotations

import zipfile
from pathlib import Path

from workbench import (
    bundle_manager,
    evaluation_engine,
    evidence_pack,
    experiment_runner,
    promotion_engine,
)


def test_pack_is_self_contained_and_verifies(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    run = experiment_runner.run_experiment(
        "stub_bundle_v1", tiny_eval_set, root=workbench_root
    )
    evaluation_engine.evaluate_run(run.run_id, root=workbench_root)

    # Install permissive rules + propose
    (workbench_root / "configs" / "promotion_rules.yaml").write_text(
        "version: '1'\nname: default\n"
        "thresholds: {aggregate: 0.0}\n"
        "regression_checks: {enabled: false}\n"
        "approval: {approved_requires: {mode: auto}}\n"
    )
    decision = promotion_engine.propose(run.run_id, root=workbench_root)

    out = workbench_root / "pack.zip"
    evidence_pack.build(decision.decision_id, out, root=workbench_root)

    assert out.exists()
    assert evidence_pack.verify(out) is True

    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
    assert "MANIFEST.json" in names
    assert "bundle.json" in names
    assert "promotion_decision.json" in names
    assert any(n.startswith("candidate_run/") for n in names)
