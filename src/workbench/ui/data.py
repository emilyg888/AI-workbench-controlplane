"""Thin data adapter for the UI.

Per SPEC_phase8 §7 and §9: this module is the *only* path by which UI
pages reach registry state. It delegates to existing business logic —
no parallel file reads.
"""
from __future__ import annotations

from pathlib import Path

from .. import (
    bundle_manager,
    db,
    deployment_state_manager,
    doctor,
    evidence_pack,
    lineage,
    promotion_engine,
)
from ..storage import find_workbench_root, read_json


def workbench_root() -> Path:
    return find_workbench_root()


def list_bundles(state: str | None = None, name: str | None = None):
    return bundle_manager.list_bundles(state=state, name=name)


def get_bundle(bundle_id: str):
    return bundle_manager.get_bundle(bundle_id)


def list_envs() -> list[str]:
    return deployment_state_manager.list_environments()


def get_active_full(env: str):
    return deployment_state_manager.get_active_full(env)


def deployment_history(env: str | None = None, bundle_id: str | None = None):
    return deployment_state_manager.history(env=env, bundle_id=bundle_id)


def list_runs(bundle_id: str | None = None, limit: int = 50):
    con = db.connect(workbench_root())
    rows = db.list_runs(con, bundle_id=bundle_id, limit=limit)
    con.close()
    return rows


def get_run_metrics(run_id: str) -> dict | None:
    p = workbench_root() / "runs" / run_id / "metrics.json"
    return read_json(p) if p.exists() else None


def get_scorecard(run_id: str) -> str | None:
    p = workbench_root() / "runs" / run_id / "scorecard.md"
    return p.read_text() if p.exists() else None


def promotion_log(bundle_id: str | None = None) -> list[dict]:
    entries = promotion_engine.read_log()
    if bundle_id:
        entries = [e for e in entries if e.get("bundle_id") == bundle_id]
    return entries


def doctor_report():
    return doctor.run_doctor()


def build_evidence_pack(decision_id: str, out: Path) -> Path:
    return evidence_pack.build(decision_id, out)


def lineage_dot(bundle_id: str) -> str:
    return lineage.dot(bundle_id)


def lineage_tree(bundle_id: str) -> str:
    return lineage.tree(bundle_id)
