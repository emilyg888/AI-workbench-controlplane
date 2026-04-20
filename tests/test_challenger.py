from __future__ import annotations

import json
from pathlib import Path

from workbench import (
    bundle_manager,
    db,
    deployment_state_manager,
    runtime_resolver,
)
from workbench.models import BundleState
from workbench.serving.invoke import invoke as invoke_fn


def _approve(bid: str, workbench_root: Path) -> None:
    for s in (BundleState.EVALUATED, BundleState.CANDIDATE, BundleState.APPROVED):
        bundle_manager.transition_bundle(bid, s, root=workbench_root)


def _setup_two_bundles(workbench_root: Path, stub_bundle_spec: dict) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    _approve("stub_bundle_v1", workbench_root)
    bundle_manager.create_bundle(
        {**stub_bundle_spec, "name": "chall", "version": "1.0.0"},
        root=workbench_root,
    )
    _approve("chall_v1", workbench_root)
    deployment_state_manager.set_active("dev", "stub_bundle_v1", root=workbench_root)


def _enable_challenger(workbench_root: Path, mode: str, fraction: float = 0.0) -> None:
    env_path = workbench_root / "configs" / "environments.json"
    cfg = json.loads(env_path.read_text())
    cfg["dev"]["challenger"] = {
        "enabled": True,
        "bundle_id": "chall_v1",
        "mode": mode,
        "traffic_fraction": fraction,
    }
    env_path.write_text(json.dumps(cfg))


def test_shadow_mode_champion_served_both_logged(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    _setup_two_bundles(workbench_root, stub_bundle_spec)
    _enable_challenger(workbench_root, mode="shadow")
    runtime_resolver.invalidate_cache()

    result = invoke_fn("dev", {"question": "hi"}, root=workbench_root)
    assert result.bundle_id == "stub_bundle_v1"

    con = db.connect(workbench_root)
    rows = con.execute(
        "SELECT bundle_id FROM inference_requests "
        "WHERE trace_id LIKE ? OR trace_id = ?",
        [f"{result.trace_id}%", result.trace_id],
    ).fetchall()
    con.close()
    bundles_served = {r[0] for r in rows}
    assert bundles_served == {"stub_bundle_v1", "chall_v1"}


def test_traffic_split_routes_some_to_challenger(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    _setup_two_bundles(workbench_root, stub_bundle_spec)
    _enable_challenger(workbench_root, mode="traffic_split", fraction=1.0)
    runtime_resolver.invalidate_cache()

    result = invoke_fn("dev", {"question": "hi"}, root=workbench_root)
    # With 100% fraction, all traffic goes to challenger
    assert result.bundle_id == "chall_v1"
