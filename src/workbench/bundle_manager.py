from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import Bundle, BundleState, derive_bundle_id, utcnow_iso
from .state_machine import assert_transition
from .storage import find_workbench_root, read_json, write_json_atomic


class BundleNotFoundError(LookupError):
    pass


class DuplicateBundleError(ValueError):
    pass


def _bundles_path(root: Path) -> Path:
    return root / "registry" / "bundles.json"


def _load_all(root: Path) -> list[Bundle]:
    raw = read_json(_bundles_path(root))
    return [Bundle.model_validate(r) for r in raw]


def _save_all(root: Path, bundles: list[Bundle]) -> None:
    write_json_atomic(
        _bundles_path(root),
        [b.model_dump(mode="json") for b in bundles],
    )


def create_bundle(spec: dict[str, Any], root: Path | None = None) -> Bundle:
    root = root or find_workbench_root()
    now = utcnow_iso()

    spec = dict(spec)
    if "name" not in spec:
        raise ValueError("create_bundle: 'name' is required")
    if "version" not in spec:
        raise ValueError("create_bundle: 'version' is required")
    spec.setdefault("bundle_id", derive_bundle_id(spec["name"], spec["version"]))
    spec.setdefault("state", BundleState.DRAFT.value)
    spec.setdefault("created_at", now)
    spec["updated_at"] = now

    bundle = Bundle.model_validate(spec)

    existing = _load_all(root)
    if any(b.bundle_id == bundle.bundle_id for b in existing):
        raise DuplicateBundleError(
            f"Bundle with id {bundle.bundle_id!r} already exists"
        )

    if bundle.lineage.parent_bundle_id is not None and not any(
        b.bundle_id == bundle.lineage.parent_bundle_id for b in existing
    ):
        raise ValueError(
            f"parent_bundle_id {bundle.lineage.parent_bundle_id!r} does not exist"
        )

    existing.append(bundle)
    _save_all(root, existing)
    return bundle


def get_bundle(bundle_id: str, root: Path | None = None) -> Bundle:
    root = root or find_workbench_root()
    for b in _load_all(root):
        if b.bundle_id == bundle_id:
            return b
    raise BundleNotFoundError(f"Bundle {bundle_id!r} not found")


def list_bundles(
    state: str | None = None,
    name: str | None = None,
    root: Path | None = None,
) -> list[Bundle]:
    root = root or find_workbench_root()
    bundles = _load_all(root)
    if state is not None:
        bundles = [b for b in bundles if b.state.value == state]
    if name is not None:
        bundles = [b for b in bundles if b.name == name]
    return bundles


def transition_bundle(
    bundle_id: str,
    new_state: BundleState | str,
    root: Path | None = None,
) -> Bundle:
    root = root or find_workbench_root()
    if isinstance(new_state, str):
        new_state = BundleState(new_state)

    bundles = _load_all(root)
    for i, b in enumerate(bundles):
        if b.bundle_id == bundle_id:
            assert_transition(b.state, new_state)
            updated = b.model_copy(update={"state": new_state, "updated_at": utcnow_iso()})
            bundles[i] = updated
            _save_all(root, bundles)
            return updated
    raise BundleNotFoundError(f"Bundle {bundle_id!r} not found")
