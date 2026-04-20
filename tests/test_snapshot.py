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


def test_snapshot_is_idempotent_when_content_matches(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    _setup_and_propose(workbench_root, stub_bundle_spec, tiny_eval_set)
    b1 = bundle_manager.get_bundle("stub_bundle_v1", root=workbench_root)
    h1 = dict(b1.resolved.hashes)

    # re-snapshot with no source change — ok, hashes identical.
    b2 = bundle_manager.snapshot_bundle(
        "stub_bundle_v1", root=workbench_root
    )
    assert b2.resolved.hashes == h1


def test_snapshot_refuses_to_mutate_approved_bundle(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    import pytest as _pytest
    prompt_path = _setup_and_propose(
        workbench_root, stub_bundle_spec, tiny_eval_set
    )
    # Bundle is now APPROVED + resolved. Mutating source + re-snapshotting
    # must raise — otherwise the "immutable at approval" guarantee is a lie.
    prompt_path.write_text("TAMPERED")
    with _pytest.raises(bundle_manager.ImmutableBundleError):
        bundle_manager.snapshot_bundle(
            "stub_bundle_v1", root=workbench_root
        )


def test_snapshot_force_overrides_immutability(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    prompt_path = _setup_and_propose(
        workbench_root, stub_bundle_spec, tiny_eval_set
    )
    prompt_path.write_text("ADMIN FIX")
    b = bundle_manager.snapshot_bundle(
        "stub_bundle_v1", root=workbench_root, force=True
    )
    assert "ADMIN FIX" in b.resolved.prompt_text


def test_approval_baseline_run_id_stamped(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    _setup_and_propose(workbench_root, stub_bundle_spec, tiny_eval_set)
    b = bundle_manager.get_bundle("stub_bundle_v1", root=workbench_root)
    assert b.resolved.approval_baseline_run_id is not None
    assert b.resolved.approval_baseline_run_id.startswith("run_")


def test_retrieval_corpus_fingerprint(
    workbench_root: Path, stub_bundle_spec: dict, tiny_eval_set: str
) -> None:
    # File-backed retrieval profile + corpus
    corpus = workbench_root / "data" / "retrieval" / "demo.jsonl"
    corpus.parent.mkdir(parents=True, exist_ok=True)
    corpus.write_text(
        '{"id": "d1", "text": "first"}\n'
        '{"id": "d2", "text": "second"}\n'
    )
    spec = {**stub_bundle_spec, "name": "r_bundle", "version": "1.0.0"}
    spec["components"] = {
        **spec["components"],
        "retrieval": {"profile_ref": "demo"},
    }
    # Follow the same approval route as _setup_and_propose does for stub
    (workbench_root / "configs" / "promotion_rules.yaml").write_text(
        "version: '1'\nname: default\n"
        "thresholds: {aggregate: 0.0}\n"
        "regression_checks: {enabled: false}\n"
        "approval: {approved_requires: {mode: auto}}\n"
    )
    bundle_manager.create_bundle(spec, root=workbench_root)
    from workbench import evaluation_engine, experiment_runner, promotion_engine
    run = experiment_runner.run_experiment(
        "r_bundle_v1", tiny_eval_set, root=workbench_root
    )
    evaluation_engine.evaluate_run(run.run_id, root=workbench_root)
    promotion_engine.propose(run.run_id, root=workbench_root)

    b = bundle_manager.get_bundle("r_bundle_v1", root=workbench_root)
    assert b.resolved.retrieval.corpus_hash is not None
    assert b.resolved.retrieval.doc_count == 2
