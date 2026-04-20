from __future__ import annotations

from pathlib import Path

import pytest

from workbench import bundle_manager, deployment_state_manager


def test_initial_state_both_null(workbench_root: Path) -> None:
    dev = deployment_state_manager.get_active("dev", root=workbench_root)
    prod = deployment_state_manager.get_active("prod", root=workbench_root)
    assert dev.active_bundle_id is None and dev.updated_at is None
    assert prod.active_bundle_id is None and prod.updated_at is None


def test_list_environments(workbench_root: Path) -> None:
    assert deployment_state_manager.list_environments(root=workbench_root) == ["dev", "prod"]


def test_set_active_skip_preconditions(
    workbench_root: Path, valid_bundle_spec: dict
) -> None:
    bundle_manager.create_bundle(valid_bundle_spec, root=workbench_root)
    dep = deployment_state_manager.set_active(
        "dev", "claims_bundle_v1",
        skip_preconditions=True, root=workbench_root,
    )
    assert dep.active_bundle_id == "claims_bundle_v1"
    assert dep.activated_at is not None


def test_set_active_unknown_env(workbench_root: Path, valid_bundle_spec: dict) -> None:
    bundle_manager.create_bundle(valid_bundle_spec, root=workbench_root)
    with pytest.raises(deployment_state_manager.UnknownEnvironmentError):
        deployment_state_manager.set_active(
            "staging", "claims_bundle_v1",
            skip_preconditions=True, root=workbench_root,
        )


def test_set_active_unknown_bundle(workbench_root: Path) -> None:
    # With preconditions enforced, missing bundle → PreconditionError
    with pytest.raises(deployment_state_manager.PreconditionError):
        deployment_state_manager.set_active("dev", "ghost_v1", root=workbench_root)
