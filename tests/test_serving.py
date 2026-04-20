from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from workbench import bundle_manager, db, deployment_state_manager, runtime_resolver
from workbench.models import BundleState
from workbench.serving.http import create_app
from workbench.serving.invoke import invoke as invoke_fn


def _deploy(workbench_root: Path, stub_bundle_spec: dict) -> str:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    bid = "stub_bundle_v1"
    for state in (BundleState.EVALUATED, BundleState.CANDIDATE, BundleState.APPROVED):
        bundle_manager.transition_bundle(bid, state, root=workbench_root)
    deployment_state_manager.set_active("dev", bid, root=workbench_root)
    runtime_resolver.invalidate_cache()
    return bid


def test_invoke_round_trip_logs_to_db(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    _deploy(workbench_root, stub_bundle_spec)
    result = invoke_fn("dev", {"question": "hello"}, root=workbench_root)
    assert result.bundle_id == "stub_bundle_v1"
    assert result.policy_action == "allow"
    assert "[stub]" in result.output

    con = db.connect(workbench_root)
    row = con.execute(
        "SELECT COUNT(*) FROM inference_requests WHERE trace_id = ?",
        [result.trace_id]
    ).fetchone()
    con.close()
    assert row[0] == 1


def test_invoke_policy_redact_on_input(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    # Point the bundle at a real policy pack with regex_block/redact
    pack = workbench_root / "data" / "policies" / "stub.yaml"
    pack.parent.mkdir(parents=True, exist_ok=True)
    pack.write_text(
        "input_rules:\n"
        "  - id: no_email\n"
        "    type: regex_block\n"
        "    pattern: '[\\w.+-]+@[\\w.-]+'\n"
        "    action: redact\n"
    )
    _deploy(workbench_root, stub_bundle_spec)
    result = invoke_fn("dev", {"question": "email me at a@b.com"}, root=workbench_root)
    # redaction happens on input text; stub echoes back — so REDACTED should appear
    assert "[REDACTED]" in result.output or "a@b.com" not in result.output


def test_http_healthz_and_active(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    _deploy(workbench_root, stub_bundle_spec)
    app = create_app("dev", root=workbench_root)
    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}
    r = client.get("/v1/active").json()
    assert r["bundle_id"] == "stub_bundle_v1"


def test_http_invoke_endpoint(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    _deploy(workbench_root, stub_bundle_spec)
    app = create_app("dev", root=workbench_root)
    client = TestClient(app)
    r = client.post("/v1/invoke", json={"input": {"question": "x"}})
    assert r.status_code == 200
    body = r.json()
    assert body["bundle_id"] == "stub_bundle_v1"


def test_http_503_when_no_active(workbench_root: Path) -> None:
    runtime_resolver.invalidate_cache()
    app = create_app("dev", root=workbench_root)
    client = TestClient(app)
    r = client.post("/v1/invoke", json={"input": {}})
    assert r.status_code == 503
