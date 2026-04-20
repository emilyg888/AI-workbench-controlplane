from __future__ import annotations

from pathlib import Path

import pytest

from workbench import bundle_manager
from workbench.models import BundleState
from workbench.state_machine import InvalidTransitionError


def test_create_bundle_generates_id(workbench_root: Path, valid_bundle_spec: dict) -> None:
    b = bundle_manager.create_bundle(valid_bundle_spec, root=workbench_root)
    assert b.bundle_id == "claims_bundle_v1"
    assert b.state == BundleState.DRAFT
    assert b.created_at and b.updated_at


def test_create_bundle_persists(workbench_root: Path, valid_bundle_spec: dict) -> None:
    bundle_manager.create_bundle(valid_bundle_spec, root=workbench_root)
    fetched = bundle_manager.get_bundle("claims_bundle_v1", root=workbench_root)
    assert fetched.name == "claims_bundle"


def test_duplicate_rejected(workbench_root: Path, valid_bundle_spec: dict) -> None:
    bundle_manager.create_bundle(valid_bundle_spec, root=workbench_root)
    with pytest.raises(bundle_manager.DuplicateBundleError):
        bundle_manager.create_bundle(valid_bundle_spec, root=workbench_root)


def test_list_filters(workbench_root: Path, valid_bundle_spec: dict) -> None:
    bundle_manager.create_bundle(valid_bundle_spec, root=workbench_root)
    spec2 = {**valid_bundle_spec, "name": "fraud_bundle", "version": "2.0.0"}
    bundle_manager.create_bundle(spec2, root=workbench_root)

    assert len(bundle_manager.list_bundles(root=workbench_root)) == 2
    assert len(bundle_manager.list_bundles(name="fraud_bundle", root=workbench_root)) == 1
    assert len(bundle_manager.list_bundles(state="draft", root=workbench_root)) == 2
    assert len(bundle_manager.list_bundles(state="approved", root=workbench_root)) == 0


def test_get_missing_raises(workbench_root: Path) -> None:
    with pytest.raises(bundle_manager.BundleNotFoundError):
        bundle_manager.get_bundle("nonexistent_v1", root=workbench_root)


def test_transition_valid(workbench_root: Path, valid_bundle_spec: dict) -> None:
    bundle_manager.create_bundle(valid_bundle_spec, root=workbench_root)
    b = bundle_manager.transition_bundle(
        "claims_bundle_v1", BundleState.ARCHIVED, root=workbench_root
    )
    assert b.state == BundleState.ARCHIVED


def test_transition_invalid(workbench_root: Path, valid_bundle_spec: dict) -> None:
    bundle_manager.create_bundle(valid_bundle_spec, root=workbench_root)
    with pytest.raises(InvalidTransitionError):
        bundle_manager.transition_bundle(
            "claims_bundle_v1", BundleState.APPROVED, root=workbench_root
        )


def test_parent_must_exist(workbench_root: Path, valid_bundle_spec: dict) -> None:
    spec = {**valid_bundle_spec, "lineage": {"parent_bundle_id": "does_not_exist_v1"}}
    with pytest.raises(ValueError):
        bundle_manager.create_bundle(spec, root=workbench_root)
