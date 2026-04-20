from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

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


DEFAULT_SCORING_PROFILE_YAML = """version: "1"
name: default
scorers:
  correctness:
    type: exact_match
    weight: 0.35
    case_sensitive: false
  groundedness:
    type: passage_overlap
    weight: 0.25
    min_overlap: 0.3
  policy_compliance:
    type: policy_check
    weight: 0.20
    policy_pack_ref: data/policies/stub.yaml
  refusal_quality:
    type: refusal_classifier
    weight: 0.05
  latency:
    type: latency_budget
    weight: 0.10
    budget_p95_ms: 2000
  completeness:
    type: non_empty
    weight: 0.05
aggregate:
  method: weighted_mean
"""


DEFAULT_PROMOTION_RULES_YAML = """version: "1"
name: default

thresholds:
  correctness: 0.85
  groundedness: 0.90
  policy_compliance: 1.00
  refusal_quality: 0.80
  latency: 0.70
  completeness: 0.95
  aggregate: 0.85

regression_checks:
  enabled: true
  baseline: prod
  max_absolute_drop: 0.02
  strict_metrics:
    - policy_compliance

approval:
  candidate_requires_all_thresholds: true
  approved_requires:
    mode: auto
"""


def ensure_registry_files(root: Path, force: bool = False) -> list[str]:
    """Seed registry/ and configs/ with initial content.

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
        "registry/deployment_history.json": [],
        "configs/environments.json": {
            "dev": {
                "description": "Local development environment",
                "requires_bundle_state": "approved",
                "min_dwell_before_next_env_hours": 0,
            },
            "prod": {
                "description": "Local production-equivalent environment",
                "requires_bundle_state": "approved",
                "requires_previous_env": "dev",
                "min_dwell_before_next_env_hours": 1,
            },
        },
    }
    for rel, data in seeds.items():
        target = root / rel
        if target.exists() and not force:
            if _is_nonempty_registry(target):
                continue
        write_json_atomic(target, data)
        touched.append(rel)

    yaml_seeds = {
        "configs/scoring_profile.yaml": DEFAULT_SCORING_PROFILE_YAML,
        "configs/promotion_rules.yaml": DEFAULT_PROMOTION_RULES_YAML,
    }
    for rel, content in yaml_seeds.items():
        target = root / rel
        if target.exists() and target.stat().st_size > 0 and not force:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
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


def write_jsonl(path: Path, records: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    n = 0
    with tmp.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return n


def read_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def append_jsonl(path: Path, record: dict) -> None:
    """Append a single record. Not atomic; for per-request logging only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def new_run_id(bundle_id: str, now: datetime | None = None) -> str:
    ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{ts}_{bundle_id}"


def new_run_dir(root: Path, bundle_id: str, now: datetime | None = None) -> tuple[str, Path]:
    run_id = new_run_id(bundle_id, now=now)
    d = root / "runs" / run_id
    d.mkdir(parents=True, exist_ok=False)
    return run_id, d
