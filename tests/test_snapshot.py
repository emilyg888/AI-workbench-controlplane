from __future__ import annotations

from pathlib import Path

from workbench import (
    bundle_manager,
    deployment_state_manager,
    evaluation_engine,
    experiment_runner,
    promotion_engine,
    runtime_resolver,
)
from workbench.models import BundleState


def _setup_and_propose(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
):
    # Write a real prompt file and policy pack for the bundle to resolve
    (workbench_root / "data" / "prompts").mkdir(parents=True, exist_ok=True)
    prompt_path = workbench_root / "data" / "prompts" / "inline.txt"
    prompt_path.write_text("ORIGINAL: answer the question {input}")

    pack_path = workbench_root / "data" / "policies" / "stub.yaml"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text("input_rules: []\noutput_rules: []\n")

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
    return prompt_path


def test_snapshot_written_on_approval(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    _setup_and_propose(workbench_root, stub_bundle_spec, tiny_eval_set)
    b = bundle_manager.get_bundle("stub_bundle_v1", root=workbench_root)
    assert b.state == BundleState.APPROVED
    assert b.resolved is not None
    assert b.resolved.prompt_text is not None
    assert "ORIGINAL" in b.resolved.prompt_text
    assert "prompt" in b.resolved.hashes


def test_runtime_uses_snapshot_not_live_file(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    prompt_path = _setup_and_propose(
        workbench_root, stub_bundle_spec, tiny_eval_set
    )
    # Approved — now edit the live file. Runtime must ignore this change.
    prompt_path.write_text("DRIFTED: completely different content")

    deployment_state_manager.set_active(
        "dev", "stub_bundle_v1", root=workbench_root
    )
    runtime_resolver.invalidate_cache()
    rr = runtime_resolver.resolve("dev", root=workbench_root)
    assert "ORIGINAL" in rr.prompt_template
    assert "DRIFTED" not in rr.prompt_template


def test_snapshot_is_idempotent(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    prompt_path = _setup_and_propose(
        workbench_root, stub_bundle_spec, tiny_eval_set
    )
    b1 = bundle_manager.get_bundle("stub_bundle_v1", root=workbench_root)
    h1 = dict(b1.resolved.hashes)

    # re-snapshot — contents unchanged, hash stable
    b2 = bundle_manager.snapshot_bundle(
        "stub_bundle_v1", root=workbench_root
    )
    assert b2.resolved.hashes == h1

    # Now change the source → new snapshot captures the change
    prompt_path.write_text("UPDATED")
    b3 = bundle_manager.snapshot_bundle(
        "stub_bundle_v1", root=workbench_root
    )
    assert b3.resolved.hashes["prompt"] != h1["prompt"]
