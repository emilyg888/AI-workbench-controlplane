from __future__ import annotations

from pathlib import Path

import pytest

from workbench import bundle_manager, deployment_state_manager, rollback
from workbench.models import BundleState


def _approve(bid: str, workbench_root: Path) -> None:
    for s in (BundleState.EVALUATED, BundleState.CANDIDATE, BundleState.APPROVED):
        bundle_manager.transition_bundle(bid, s, root=workbench_root)


def test_rollback_to_previous(workbench_root: Path, stub_bundle_spec: dict) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    _approve("stub_bundle_v1", workbench_root)
    bundle_manager.create_bundle(
        {**stub_bundle_spec, "name": "b", "version": "2.0.0"},
        root=workbench_root,
    )
    _approve("b_v2", workbench_root)

    deployment_state_manager.set_active("dev", "stub_bundle_v1", root=workbench_root)
    deployment_state_manager.set_active("dev", "b_v2", root=workbench_root)

    dep = rollback.rollback("dev", reason="test", root=workbench_root)
    assert dep.active_bundle_id == "stub_bundle_v1"

    # history has a rollback event
    events = deployment_state_manager.history(env="dev", root=workbench_root)
    assert events[-1].action == "rollback"


def test_rollback_explicit_target_must_be_prior(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    _approve("stub_bundle_v1", workbench_root)
    deployment_state_manager.set_active("dev", "stub_bundle_v1", root=workbench_root)

    with pytest.raises(rollback.RollbackError):
        rollback.rollback("dev", to="ghost_v1", root=workbench_root)


def test_rollback_refuses_archived(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    _approve("stub_bundle_v1", workbench_root)
    bundle_manager.create_bundle(
        {**stub_bundle_spec, "name": "b", "version": "2.0.0"}, root=workbench_root,
    )
    _approve("b_v2", workbench_root)
    deployment_state_manager.set_active("dev", "stub_bundle_v1", root=workbench_root)
    deployment_state_manager.set_active("dev", "b_v2", root=workbench_root)
    bundle_manager.transition_bundle(
        "stub_bundle_v1", BundleState.ARCHIVED, root=workbench_root
    )
    with pytest.raises(rollback.RollbackError):
        rollback.rollback("dev", to="stub_bundle_v1", root=workbench_root)
