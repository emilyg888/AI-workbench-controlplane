from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from .bundle_manager import get_bundle, transition_bundle
from .environments import Environment, load_environments
from .models import BundleState, Deployment, utcnow_iso
from .state_machine import InvalidTransitionError
from .storage import find_workbench_root, read_json, write_json_atomic


class UnknownEnvironmentError(LookupError):
    pass


class PreconditionError(ValueError):
    pass


class DeploymentEvent(BaseModel):
    event_id: str
    env: str
    action: str  # "activate" | "undeploy" | "rollback"
    bundle_id: str | None
    previous_bundle_id: str | None
    at: str
    by: str = "local-user"
    promotion_decision_id: str | None = None
    notes: str | None = None


class FullDeployment(BaseModel):
    active_bundle_id: str | None = None
    activated_at: str | None = None
    activated_by: str | None = None
    promotion_decision_id: str | None = None

    @classmethod
    def from_legacy(cls, raw: dict) -> "FullDeployment":
        return cls(
            active_bundle_id=raw.get("active_bundle_id"),
            activated_at=raw.get("activated_at") or raw.get("updated_at"),
            activated_by=raw.get("activated_by"),
            promotion_decision_id=raw.get("promotion_decision_id"),
        )


# Injectable clock for tests.
_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


def set_clock(fn: Callable[[], datetime]) -> None:
    global _clock
    _clock = fn


def reset_clock() -> None:
    global _clock
    _clock = lambda: datetime.now(timezone.utc)


def _now_iso() -> str:
    return _clock().strftime("%Y-%m-%dT%H:%M:%SZ")


def _deployments_path(root: Path) -> Path:
    return root / "registry" / "deployments.json"


def _history_path(root: Path) -> Path:
    return root / "registry" / "deployment_history.json"


def _load(root: Path) -> dict[str, FullDeployment]:
    raw = read_json(_deployments_path(root))
    return {env: FullDeployment.from_legacy(v) for env, v in raw.items()}


def _save(root: Path, data: dict[str, FullDeployment]) -> None:
    write_json_atomic(
        _deployments_path(root),
        {env: d.model_dump(mode="json") for env, d in data.items()},
    )


def list_environments(root: Path | None = None) -> list[str]:
    root = root or find_workbench_root()
    return sorted(_load(root).keys())


def get_active(env: str, root: Path | None = None) -> Deployment:
    """Backward-compatible accessor: returns the legacy two-field model."""
    root = root or find_workbench_root()
    data = _load(root)
    if env not in data:
        raise UnknownEnvironmentError(f"Unknown environment: {env!r}")
    d = data[env]
    return Deployment(
        active_bundle_id=d.active_bundle_id,
        updated_at=d.activated_at,
    )


def get_active_full(env: str, root: Path | None = None) -> FullDeployment:
    root = root or find_workbench_root()
    data = _load(root)
    if env not in data:
        raise UnknownEnvironmentError(f"Unknown environment: {env!r}")
    return data[env]


def get_active_bundle(env: str, root: Path | None = None):
    """Returns the active Bundle for env, or None if env is empty."""
    dep = get_active_full(env, root=root)
    if dep.active_bundle_id is None:
        return None
    return get_bundle(dep.active_bundle_id, root=root)


def history(
    env: str | None = None,
    bundle_id: str | None = None,
    root: Path | None = None,
) -> list[DeploymentEvent]:
    root = root or find_workbench_root()
    p = _history_path(root)
    raw = read_json(p) if p.exists() else []
    events = [DeploymentEvent.model_validate(e) for e in raw]
    if env:
        events = [e for e in events if e.env == env]
    if bundle_id:
        events = [e for e in events if e.bundle_id == bundle_id]
    return events


def _append_history(root: Path, event: DeploymentEvent) -> None:
    p = _history_path(root)
    existing = read_json(p) if p.exists() else []
    existing.append(event.model_dump(mode="json"))
    write_json_atomic(p, existing)


def _new_event_id(env: str, action: str, now: datetime | None = None) -> str:
    ts = (now or _clock()).strftime("%Y%m%dT%H%M%SZ")
    return f"dep_{ts}_{env}_{action}"


def check_preconditions(
    env: str, bundle_id: str, root: Path | None = None
) -> list[str]:
    """Return a list of human-readable reasons the deployment is blocked."""
    root = root or find_workbench_root()
    envs = load_environments(root)
    if env not in envs:
        return [f"unknown environment: {env!r}"]
    env_cfg: Environment = envs[env]
    reasons: list[str] = []

    try:
        bundle = get_bundle(bundle_id, root=root)
    except Exception as e:
        return [f"bundle not found: {bundle_id!r} ({e})"]

    required_state = env_cfg.requires_bundle_state
    ok_states = {required_state, BundleState.DEPLOYED.value}
    if bundle.state.value not in ok_states:
        reasons.append(
            f"bundle state is {bundle.state.value!r}; requires "
            f"{required_state!r} (or deployed)"
        )

    # already-active short-circuit
    current = _load(root).get(env)
    if current and current.active_bundle_id == bundle_id:
        reasons.append(f"bundle {bundle_id!r} already active in {env!r}")

    prev = env_cfg.requires_previous_env
    if prev:
        prev_dep = _load(root).get(prev)
        if not prev_dep or prev_dep.active_bundle_id != bundle_id:
            reasons.append(
                f"bundle must be active in {prev!r} before {env!r}; "
                f"current {prev!r} active = "
                f"{prev_dep.active_bundle_id if prev_dep else 'none'}"
            )
        elif env_cfg.min_dwell_before_next_env_hours > 0 and prev_dep.activated_at:
            dwell_needed = timedelta(hours=env_cfg.min_dwell_before_next_env_hours)
            activated = datetime.strptime(
                prev_dep.activated_at, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
            if _clock() - activated < dwell_needed:
                have = _clock() - activated
                reasons.append(
                    f"dwell time in {prev!r} is {have}, requires {dwell_needed}"
                )
    return reasons


def set_active(
    env: str,
    bundle_id: str,
    promotion_decision_id: str | None = None,
    notes: str | None = None,
    by: str = "local-user",
    skip_preconditions: bool = False,
    action: str = "activate",
    root: Path | None = None,
) -> FullDeployment:
    root = root or find_workbench_root()
    data = _load(root)
    if env not in data:
        raise UnknownEnvironmentError(f"Unknown environment: {env!r}")

    if not skip_preconditions:
        reasons = check_preconditions(env, bundle_id, root=root)
        if reasons:
            raise PreconditionError("; ".join(reasons))

    previous = data[env].active_bundle_id
    now_iso = _now_iso()
    data[env] = FullDeployment(
        active_bundle_id=bundle_id,
        activated_at=now_iso,
        activated_by=by,
        promotion_decision_id=promotion_decision_id,
    )
    _save(root, data)

    _append_history(root, DeploymentEvent(
        event_id=_new_event_id(env, action),
        env=env,
        action=action,
        bundle_id=bundle_id,
        previous_bundle_id=previous,
        at=now_iso,
        by=by,
        promotion_decision_id=promotion_decision_id,
        notes=notes,
    ))

    # promote bundle state to deployed (if approved)
    bundle = get_bundle(bundle_id, root=root)
    if bundle.state == BundleState.APPROVED:
        try:
            transition_bundle(bundle_id, BundleState.DEPLOYED, root=root)
        except InvalidTransitionError:
            pass

    # housekeeping: old active bundle may need to go back from deployed -> approved
    if previous and previous != bundle_id:
        _housekeep_previous(previous, root=root)

    return data[env]


def undeploy(
    env: str, reason: str | None = None, root: Path | None = None
) -> FullDeployment:
    root = root or find_workbench_root()
    data = _load(root)
    if env not in data:
        raise UnknownEnvironmentError(f"Unknown environment: {env!r}")
    previous = data[env].active_bundle_id
    now_iso = _now_iso()
    data[env] = FullDeployment()
    _save(root, data)
    _append_history(root, DeploymentEvent(
        event_id=_new_event_id(env, "undeploy"),
        env=env,
        action="undeploy",
        bundle_id=None,
        previous_bundle_id=previous,
        at=now_iso,
        notes=reason,
    ))
    if previous:
        _housekeep_previous(previous, root=root)
    return data[env]


def _housekeep_previous(bundle_id: str, root: Path) -> None:
    """If the bundle is no longer active in any env and its state is deployed,
    demote it to approved."""
    still_active = any(
        d.active_bundle_id == bundle_id for d in _load(root).values()
    )
    if still_active:
        return
    try:
        b = get_bundle(bundle_id, root=root)
    except Exception:
        return
    if b.state == BundleState.DEPLOYED:
        try:
            transition_bundle(bundle_id, BundleState.APPROVED, root=root)
        except InvalidTransitionError:
            pass
