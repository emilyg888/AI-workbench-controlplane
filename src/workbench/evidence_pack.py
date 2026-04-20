from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import bundle_manager, promotion_engine
from .storage import find_workbench_root, sha256_file


class EvidencePackError(RuntimeError):
    pass


def _find_decision(decision_id: str, root: Path) -> dict:
    for entry in promotion_engine.read_log(root=root):
        if entry.get("decision_id") == decision_id:
            return entry
    raise EvidencePackError(f"decision not found: {decision_id}")


def _artifact_paths(root: Path, run_id: str | None) -> list[tuple[str, Path]]:
    """Returns (arcname, absolute_path) for each Phase-2/3/4 run artifact."""
    if run_id is None:
        return []
    rd = root / "runs" / run_id
    names = ("config.json", "inputs.jsonl", "predictions.jsonl",
             "timings.json", "metrics.json", "scorecard.md",
             "metrics_per_item.jsonl",
             "promotion_decision.json", "promotion_report.md")
    return [(f"candidate_run/{n}", rd / n) for n in names if (rd / n).exists()]


def build(decision_id: str, output: Path, root: Path | None = None) -> Path:
    root = root or find_workbench_root()
    decision = _find_decision(decision_id, root)
    bundle_id = decision["bundle_id"]
    run_id = decision.get("run_id")

    bundle = bundle_manager.get_bundle(bundle_id, root=root)

    manifest_files: list[tuple[str, Path]] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "bundle.json").write_text(
            json.dumps(bundle.model_dump(mode="json"), indent=2)
        )
        manifest_files.append(("bundle.json", tmp_path / "bundle.json"))

        (tmp_path / "promotion_decision.json").write_text(
            json.dumps(decision, indent=2)
        )
        manifest_files.append(("promotion_decision.json",
                               tmp_path / "promotion_decision.json"))

        rep = root / "runs" / (run_id or "_") / "promotion_report.md"
        if rep.exists():
            manifest_files.append(("promotion_report.md", rep))

        manifest_files.extend(_artifact_paths(root, run_id))

        baseline_run = (decision.get("checks", {})
                        .get("regression", {})
                        .get("baseline_run_id"))
        if baseline_run:
            br = root / "runs" / baseline_run
            for n in ("metrics.json", "scorecard.md"):
                if (br / n).exists():
                    manifest_files.append((f"baseline_run/{n}", br / n))

        for rel in ("configs/scoring_profile.yaml",
                    "configs/promotion_rules.yaml"):
            p = root / rel
            if p.exists():
                manifest_files.append((Path(rel).name, p))

        # build manifest with hashes
        manifest = {
            "pack_version": "1",
            "generated_at": datetime.now(timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "decision_id": decision_id,
            "bundle_id": bundle_id,
            "run_id": run_id,
            "files": [
                {"arcname": arc, "sha256": sha256_file(p), "size": p.stat().st_size}
                for arc, p in manifest_files
            ],
        }
        manifest_path = tmp_path / "MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(manifest_path, "MANIFEST.json")
            for arc, p in manifest_files:
                zf.write(p, arc)

    return output


def verify(pack_path: Path) -> bool:
    with zipfile.ZipFile(pack_path, "r") as zf:
        manifest = json.loads(zf.read("MANIFEST.json"))
        for entry in manifest.get("files", []):
            data = zf.read(entry["arcname"])
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                return False
    return True
