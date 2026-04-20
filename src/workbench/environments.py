from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .storage import find_workbench_root, read_json


class Environment(BaseModel):
    description: str = ""
    requires_bundle_state: str = "approved"
    requires_previous_env: str | None = None
    min_dwell_before_next_env_hours: float = 0.0
    # Phase 7 adds `challenger`; keep the field open here.
    extras: dict[str, Any] = Field(default_factory=dict)


def load_environments(root: Path | None = None) -> dict[str, Environment]:
    root = root or find_workbench_root()
    raw = read_json(root / "configs" / "environments.json")
    out: dict[str, Environment] = {}
    for name, body in (raw or {}).items():
        body = dict(body or {})
        known = {
            "description": body.pop("description", ""),
            "requires_bundle_state": body.pop("requires_bundle_state", "approved"),
            "requires_previous_env": body.pop("requires_previous_env", None),
            "min_dwell_before_next_env_hours":
                body.pop("min_dwell_before_next_env_hours", 0.0),
        }
        out[name] = Environment(**known, extras=body)
    return out
