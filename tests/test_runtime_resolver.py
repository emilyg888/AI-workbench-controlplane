from __future__ import annotations

from pathlib import Path

import pytest

from workbench import bundle_manager, deployment_state_manager, runtime_resolver
from workbench.models import BundleState


def _deploy_stub(workbench_root: Path, stub_bundle_spec: dict) -> str:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    bid = "stub_bundle_v1"
    for state in (BundleState.EVALUATED, BundleState.CANDIDATE, BundleState.APPROVED):
        bundle_manager.transition_bundle(bid, state, root=workbench_root)
    deployment_state_manager.set_active("dev", bid, root=workbench_root)
    return bid


def test_resolve_returns_runtime(workbench_root: Path, stub_bundle_spec: dict) -> None:
    _deploy_stub(workbench_root, stub_bundle_spec)
    runtime_resolver.invalidate_cache()
    rr = runtime_resolver.resolve("dev", root=workbench_root)
    assert rr.bundle.bundle_id == "stub_bundle_v1"
    assert rr.model.name == "stub"


def test_resolve_raises_on_empty_env(workbench_root: Path) -> None:
    runtime_resolver.invalidate_cache()
    with pytest.raises(runtime_resolver.NoActiveBundleError):
        runtime_resolver.resolve("dev", root=workbench_root)


def test_cache_hits_on_same_deployment(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    _deploy_stub(workbench_root, stub_bundle_spec)
    runtime_resolver.invalidate_cache()
    a = runtime_resolver.resolve("dev", root=workbench_root)
    b = runtime_resolver.resolve("dev", root=workbench_root)
    assert a is b  # same cached instance


def test_cache_invalidates_on_new_deployment(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    _deploy_stub(workbench_root, stub_bundle_spec)
    runtime_resolver.invalidate_cache()
    a = runtime_resolver.resolve("dev", root=workbench_root)

    # New bundle + re-deploy
    spec2 = {**stub_bundle_spec, "name": "other_bundle", "version": "1.0.0"}
    bundle_manager.create_bundle(spec2, root=workbench_root)
    for state in (BundleState.EVALUATED, BundleState.CANDIDATE, BundleState.APPROVED):
        bundle_manager.transition_bundle("other_bundle_v1", state, root=workbench_root)
    import time
    time.sleep(1.1)  # ensure activated_at timestamp differs
    deployment_state_manager.set_active("dev", "other_bundle_v1", root=workbench_root)

    b = runtime_resolver.resolve("dev", root=workbench_root)
    assert a is not b
    assert b.bundle.bundle_id == "other_bundle_v1"
