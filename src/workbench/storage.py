from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ENV_ROOT = "WORKBENCH_ROOT"


def find_workbench_root(start: Path | None = None) -> Path:
    override = os.environ.get(ENV_ROOT)
    if override:
        return Path(override).resolve()
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / "registry" / "bundles.json").exists():
            return p
    raise FileNotFoundError(
        "Could not locate workbench root (no registry/bundles.json found walking up "
        f"from {cur}). Run `workbench init` or set {ENV_ROOT}."
    )


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


SCAFFOLD_DIRS = [
    "configs",
    "registry",
    "runs",
    "db",
    "data/eval_sets",
    "data/retrieval",
    "data/policies",
    "data/prompts",
    "data/semantic",
    "data/signals",
    "examples",
    "docs",
]


def ensure_registry_files(root: Path, force: bool = False) -> list[str]:
    """Seed registry/ and configs/ with Phase 1 initial content.

    Returns list of paths created or overwritten (relative to root).
    """
    touched: list[str] = []
    for d in SCAFFOLD_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)

    seeds: dict[str, Any] = {
        "registry/bundles.json": [],
        "registry/deployments.json": {
            "dev": {"active_bundle_id": None, "updated_at": None},
            "prod": {"active_bundle_id": None, "updated_at": None},
        },
        "registry/promotion_log.json": [],
        "configs/environments.json": {
            "dev": {"description": "Local development environment"},
            "prod": {"description": "Local production-equivalent environment"},
        },
    }
    for rel, data in seeds.items():
        target = root / rel
        if target.exists() and not force:
            if _is_nonempty_registry(target):
                continue
        write_json_atomic(target, data)
        touched.append(rel)
    return touched


def _is_nonempty_registry(path: Path) -> bool:
    try:
        data = read_json(path)
    except Exception:
        return False
    if isinstance(data, list):
        return len(data) > 0
    if isinstance(data, dict):
        # deployments.json is "non-empty" only if any env has an active bundle
        for v in data.values():
            if isinstance(v, dict) and v.get("active_bundle_id"):
                return True
        return False
    return False
