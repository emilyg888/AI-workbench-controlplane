from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from . import bundle_manager, deployment_state_manager, promotion_engine
from .models import BundleState
from .storage import find_workbench_root


class Issue(BaseModel):
    severity: str  # "info" | "warn" | "error"
    check: str
    message: str
    fix: str | None = None  # suggested remediation


class Report(BaseModel):
    ok: bool
    issues: list[Issue]


def _check(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    bundles = bundle_manager.list_bundles(root=root)
    bundle_ids = {b.bundle_id for b in bundles}

    # 1. Deployment references exist
    for env in deployment_state_manager.list_environments(root=root):
        dep = deployment_state_manager.get_active_full(env, root=root)
        if dep.active_bundle_id and dep.active_bundle_id not in bundle_ids:
            issues.append(Issue(
                severity="error",
                check="dangling_deployment",
                message=f"{env}.active_bundle_id={dep.active_bundle_id} "
                        f"does not exist in bundles.json",
                fix=f"workbench undeploy --env {env}",
            ))

    # 2. Active bundles should be in 'deployed' state
    for env in deployment_state_manager.list_environments(root=root):
        dep = deployment_state_manager.get_active_full(env, root=root)
        if dep.active_bundle_id and dep.active_bundle_id in bundle_ids:
            b = next(x for x in bundles if x.bundle_id == dep.active_bundle_id)
            if b.state != BundleState.DEPLOYED:
                issues.append(Issue(
                    severity="warn",
                    check="active_not_deployed_state",
                    message=f"{env} active {b.bundle_id} is in state "
                            f"{b.state.value!r}; expected 'deployed'",
                    fix="workbench set-state <bundle_id> deployed",
                ))

    # 3. Promotion log references exist
    for entry in promotion_engine.read_log(root=root):
        bid = entry.get("bundle_id")
        if bid and bid not in bundle_ids:
            issues.append(Issue(
                severity="warn",
                check="orphan_promotion_decision",
                message=f"promotion decision {entry.get('decision_id')} "
                        f"references missing bundle {bid}",
            ))

    # 4. Run directories with no matching bundle
    runs_dir = root / "runs"
    if runs_dir.exists():
        for d in runs_dir.iterdir():
            if not d.is_dir():
                continue
            config = d / "config.json"
            if not config.exists():
                continue
            try:
                import json
                cfg = json.loads(config.read_text())
                bid = cfg.get("bundle", {}).get("bundle_id")
                if bid and bid not in bundle_ids:
                    issues.append(Issue(
                        severity="info",
                        check="orphan_run",
                        message=f"run {d.name} references missing bundle {bid}",
                    ))
            except Exception:
                pass

    # 5. Deployment history chronology
    events = deployment_state_manager.history(root=root)
    last_at = ""
    for e in events:
        if e.at < last_at:
            issues.append(Issue(
                severity="warn",
                check="history_out_of_order",
                message=f"event {e.event_id} at {e.at} precedes {last_at}",
            ))
        last_at = e.at

    return issues


def run_doctor(
    root: Path | None = None, fix: bool = False, yes: bool = False
) -> Report:
    root = root or find_workbench_root()
    issues = _check(root)

    if fix and yes:
        # Safe non-destructive fixes: run any pending DB migrations by connect
        from . import db
        con = db.connect(root)
        con.close()

    return Report(ok=all(i.severity != "error" for i in issues), issues=issues)
