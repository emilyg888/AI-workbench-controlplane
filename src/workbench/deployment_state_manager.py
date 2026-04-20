from __future__ import annotations

from pathlib import Path

from .bundle_manager import get_bundle
from .models import Deployment, utcnow_iso
from .storage import find_workbench_root, read_json, write_json_atomic


class UnknownEnvironmentError(LookupError):
    pass


def _deployments_path(root: Path) -> Path:
    return root / "registry" / "deployments.json"


def _load(root: Path) -> dict[str, Deployment]:
    raw = read_json(_deployments_path(root))
    return {env: Deployment.model_validate(v) for env, v in raw.items()}


def _save(root: Path, data: dict[str, Deployment]) -> None:
    write_json_atomic(
        _deployments_path(root),
        {env: d.model_dump(mode="json") for env, d in data.items()},
    )


def list_environments(root: Path | None = None) -> list[str]:
    root = root or find_workbench_root()
    return sorted(_load(root).keys())


def get_active(env: str, root: Path | None = None) -> Deployment:
    root = root or find_workbench_root()
    data = _load(root)
    if env not in data:
        raise UnknownEnvironmentError(f"Unknown environment: {env!r}")
    return data[env]


def set_active(env: str, bundle_id: str, root: Path | None = None) -> Deployment:
    root = root or find_workbench_root()
    data = _load(root)
    if env not in data:
        raise UnknownEnvironmentError(f"Unknown environment: {env!r}")
    get_bundle(bundle_id, root=root)  # raises if not found
    data[env] = Deployment(active_bundle_id=bundle_id, updated_at=utcnow_iso())
    _save(root, data)
    return data[env]
