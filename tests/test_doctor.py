from __future__ import annotations

import json
from pathlib import Path

from workbench import bundle_manager, deployment_state_manager, doctor
from workbench.models import BundleState


def test_clean_repo_reports_ok(workbench_root: Path) -> None:
    report = doctor.run_doctor(root=workbench_root)
    assert report.ok is True
    assert report.issues == []


def test_dangling_deployment_detected(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    # Write a deployment that points at a non-existent bundle
    path = workbench_root / "registry" / "deployments.json"
    path.write_text(json.dumps({
        "dev": {"active_bundle_id": "ghost_v1", "activated_at": "2026-04-20T00:00:00Z"},
        "prod": {"active_bundle_id": None, "activated_at": None},
    }))
    report = doctor.run_doctor(root=workbench_root)
    assert any(i.check == "dangling_deployment" for i in report.issues)


def test_state_drift_warning(workbench_root: Path, stub_bundle_spec: dict) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    for s in (BundleState.EVALUATED, BundleState.CANDIDATE, BundleState.APPROVED):
        bundle_manager.transition_bundle("stub_bundle_v1", s, root=workbench_root)
    deployment_state_manager.set_active("dev", "stub_bundle_v1", root=workbench_root)
    # Manually drift: force back to approved while still active in dev
    bundle_manager.transition_bundle(
        "stub_bundle_v1", BundleState.APPROVED, root=workbench_root,
    )
    report = doctor.run_doctor(root=workbench_root)
    assert any(i.check == "active_not_deployed_state" for i in report.issues)
