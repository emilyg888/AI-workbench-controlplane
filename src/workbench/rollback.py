from __future__ import annotations

from pathlib import Path

from . import deployment_state_manager
from .bundle_manager import get_bundle
from .models import BundleState
from .storage import find_workbench_root


class RollbackError(RuntimeError):
    pass


def rollback(
    env: str,
    to: str | None = None,
    reason: str | None = None,
    root: Path | None = None,
):
    """Revert an env's active bundle.

    If ``to`` is None, rolls back to the immediately previous active
    bundle_id found in deployment_history.json.
    """
    root = root or find_workbench_root()
    events = deployment_state_manager.history(env=env, root=root)
    activations = [e for e in events if e.action in ("activate", "rollback")]
    if not activations:
        raise RollbackError(f"no prior activations in env={env!r}")

    current = activations[-1]
    target_bundle_id = to
    if target_bundle_id is None:
        # Previous active in this env — walk back for the most recent different one.
        prev = None
        for e in reversed(activations[:-1]):
            if e.bundle_id and e.bundle_id != current.bundle_id:
                prev = e.bundle_id
                break
        if prev is None:
            raise RollbackError(
                f"no earlier distinct bundle to roll back to in env={env!r}"
            )
        target_bundle_id = prev
    else:
        prior_ids = {e.bundle_id for e in activations[:-1] if e.bundle_id}
        if target_bundle_id not in prior_ids:
            raise RollbackError(
                f"bundle {target_bundle_id!r} was never previously active in {env!r}"
            )

    target_bundle = get_bundle(target_bundle_id, root=root)
    if target_bundle.state == BundleState.ARCHIVED:
        raise RollbackError(
            f"cannot roll back to archived bundle {target_bundle_id!r}"
        )

    return deployment_state_manager.set_active(
        env=env,
        bundle_id=target_bundle_id,
        notes=reason or "rollback",
        skip_preconditions=True,
        action="rollback",
        root=root,
    )
