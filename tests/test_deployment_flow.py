from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from workbench import bundle_manager, deployment_state_manager
from workbench.models import BundleState


def _approved_bundle(workbench_root: Path, stub_bundle_spec: dict) -> str:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    bid = "stub_bundle_v1"
    for state in (BundleState.EVALUATED, BundleState.CANDIDATE, BundleState.APPROVED):
        bundle_manager.transition_bundle(bid, state, root=workbench_root)
    return bid


def test_happy_path_dev_then_prod(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    bid = _approved_bundle(workbench_root, stub_bundle_spec)

    # freeze clock: dev activates at T0
    t0 = datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc)
    deployment_state_manager.set_clock(lambda: t0)
    try:
        deployment_state_manager.set_active("dev", bid, root=workbench_root)
        b = bundle_manager.get_bundle(bid, root=workbench_root)
        assert b.state == BundleState.DEPLOYED

        # prod is blocked by dwell requirement (1h)
        with pytest.raises(deployment_state_manager.PreconditionError):
            deployment_state_manager.set_active("prod", bid, root=workbench_root)

        # advance 2 hours; now prod succeeds
        deployment_state_manager.set_clock(lambda: t0 + timedelta(hours=2))
        deployment_state_manager.set_active("prod", bid, root=workbench_root)
        dev = deployment_state_manager.get_active_full("dev", root=workbench_root)
        prod = deployment_state_manager.get_active_full("prod", root=workbench_root)
        assert dev.active_bundle_id == bid
        assert prod.active_bundle_id == bid
    finally:
        deployment_state_manager.reset_clock()


def test_prod_blocked_without_dev(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    bid = _approved_bundle(workbench_root, stub_bundle_spec)
    with pytest.raises(deployment_state_manager.PreconditionError):
        deployment_state_manager.set_active("prod", bid, root=workbench_root)


def test_non_approved_rejected(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    # state is draft
    with pytest.raises(deployment_state_manager.PreconditionError):
        deployment_state_manager.set_active(
            "dev", "stub_bundle_v1", root=workbench_root
        )


def test_undeploy_writes_history(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    bid = _approved_bundle(workbench_root, stub_bundle_spec)
    deployment_state_manager.set_active("dev", bid, root=workbench_root)
    deployment_state_manager.undeploy("dev", reason="test", root=workbench_root)
    events = deployment_state_manager.history(env="dev", root=workbench_root)
    assert [e.action for e in events] == ["activate", "undeploy"]
    dep = deployment_state_manager.get_active_full("dev", root=workbench_root)
    assert dep.active_bundle_id is None


def test_housekeep_demotes_deployed_to_approved(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    bid = _approved_bundle(workbench_root, stub_bundle_spec)
    deployment_state_manager.set_active("dev", bid, root=workbench_root)
    assert bundle_manager.get_bundle(bid, root=workbench_root).state == BundleState.DEPLOYED
    deployment_state_manager.undeploy("dev", reason="test", root=workbench_root)
    assert bundle_manager.get_bundle(bid, root=workbench_root).state == BundleState.APPROVED


def test_history_append_only(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    bid = _approved_bundle(workbench_root, stub_bundle_spec)
    deployment_state_manager.set_active("dev", bid, root=workbench_root)
    deployment_state_manager.undeploy("dev", root=workbench_root)
    deployment_state_manager.set_active("dev", bid, root=workbench_root)
    events = deployment_state_manager.history(root=workbench_root)
    assert len(events) == 3
