from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from . import bundle_manager, comparison, db
from .models import BundleState, utcnow_iso
from .scorers import Prediction, get_scorer
from .scorers.base import EvalExample
from .scoring_profile import ScoringProfile, load_scoring_profile, profile_tag
from .state_machine import InvalidTransitionError
from .storage import (
    find_workbench_root,
    read_json,
    read_jsonl,
    write_json_atomic,
    write_jsonl,
)


METRIC_KEY_TO_DB_COLUMN = {
    "correctness": "correctness",
    "groundedness": "groundedness",
    "policy_compliance": "policy_compliance",
    "refusal_quality": "refusal_quality",
    "latency": "latency_score",
    "completeness": "completeness",
}


class EvalResult(BaseModel):
    run_id: str
    bundle_id: str
    scores: dict[str, float]
    aggregate: float
    scoring_profile: str
    scored_at: str


def _run_dir(root: Path, run_id: str) -> Path:
    return root / "runs" / run_id


def _load_run_artifacts(
    root: Path, run_id: str
) -> tuple[dict, list[Prediction], list[EvalExample]]:
    rd = _run_dir(root, run_id)
    if not rd.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    config = read_json(rd / "config.json")
    preds = [Prediction.model_validate(r) for r in read_jsonl(rd / "predictions.jsonl")]
    inputs = [EvalExample.model_validate(r) for r in read_jsonl(rd / "inputs.jsonl")]
    return config, preds, inputs


def _resolve_profile(root: Path, config: dict, profile_name: str | None) -> ScoringProfile:
    ref = None
    if profile_name and profile_name != "default":
        ref = root / "configs" / f"scoring_profile_{profile_name}.yaml"
    else:
        bundle = config.get("bundle", {})
        ref_str = (bundle.get("components", {})
                   .get("evaluation", {})
                   .get("profile_ref"))
        if ref_str:
            p = Path(ref_str)
            ref = p if p.is_absolute() else root / p
    if ref is None or not ref.exists():
        ref = root / "configs" / "scoring_profile.yaml"
    return load_scoring_profile(ref)


def _aggregate(scores: dict[str, float], profile: ScoringProfile) -> float:
    method = profile.aggregate.method
    entries = [(name, scores[name], profile.scorers[name].weight)
               for name in scores if name in profile.scorers]
    if not entries:
        return 0.0
    if method == "min":
        return min(v for _, v, _ in entries)
    if method == "harmonic_mean":
        vals = [max(v, 1e-9) for _, v, _ in entries]
        return len(vals) / sum(1 / v for v in vals)
    total_w = sum(w for _, _, w in entries) or 1.0
    return sum(v * w for _, v, w in entries) / total_w


def evaluate_run(
    run_id: str,
    profile_name: str | None = None,
    baseline_run_id: str | None = None,
    root: Path | None = None,
) -> EvalResult:
    root = root or find_workbench_root()
    config, predictions, eval_set = _load_run_artifacts(root, run_id)
    bundle_id = config["bundle"]["bundle_id"]

    profile = _resolve_profile(root, config, profile_name)

    results: dict[str, Any] = {}
    per_item_rows: list[dict] = []
    for metric_name, scfg in profile.scorers.items():
        scorer_cls = get_scorer(scfg.type)
        scorer = scorer_cls()
        cfg = dict(scfg.extras)
        result = scorer.score(predictions, eval_set, cfg)
        results[metric_name] = result
        for row in result.per_item:
            per_item_rows.append({"metric": metric_name, **row})

    scores = {name: round(r.value, 4) for name, r in results.items()}
    aggregate = round(_aggregate(scores, profile), 4)
    scored_at = utcnow_iso()

    run_dir = _run_dir(root, run_id)
    metrics_doc = {
        "run_id": run_id,
        "bundle_id": bundle_id,
        "scoring_profile": profile_tag(profile),
        "scored_at": scored_at,
        "scores": scores,
        "aggregate": aggregate,
        "per_item_path": "metrics_per_item.jsonl",
    }
    write_json_atomic(run_dir / "metrics.json", metrics_doc)
    write_jsonl(run_dir / "metrics_per_item.jsonl", per_item_rows)
    (run_dir / "scorecard.md").write_text(
        _render_scorecard(metrics_doc, profile, results, predictions),
        encoding="utf-8",
    )

    if baseline_run_id:
        baseline_metrics = _load_metrics(root, baseline_run_id)
        report = comparison.compare(baseline_metrics, metrics_doc)
        (run_dir / f"comparison_vs_{baseline_run_id}.md").write_text(
            comparison.render_markdown(report), encoding="utf-8",
        )

    _persist_to_db(root, run_id, metrics_doc, profile)
    _transition_bundle_safe(root, bundle_id)

    return EvalResult(
        run_id=run_id,
        bundle_id=bundle_id,
        scores=scores,
        aggregate=aggregate,
        scoring_profile=profile_tag(profile),
        scored_at=scored_at,
    )


def _load_metrics(root: Path, run_id: str) -> dict:
    p = _run_dir(root, run_id) / "metrics.json"
    if not p.exists():
        raise FileNotFoundError(f"metrics.json missing for {run_id}")
    return read_json(p)


def _render_scorecard(
    metrics: dict,
    profile: ScoringProfile,
    results: dict,
    predictions: list,
) -> str:
    lines = [
        f"# Scorecard — {metrics['bundle_id']}",
        "",
        f"**Run:** {metrics['run_id']}",
        f"**Scoring profile:** {metrics['scoring_profile']}",
        f"**Scored:** {metrics['scored_at']}",
        "",
        f"## Aggregate: **{metrics['aggregate']:.3f}**",
        "",
        "| Metric | Score | Weight | Weighted |",
        "|---|---|---|---|",
    ]
    for name, scfg in profile.scorers.items():
        score = metrics["scores"].get(name, 0.0)
        w = scfg.weight
        lines.append(f"| {name} | {score:.3f} | {w:.2f} | {score * w:.3f} |")

    failing_items = [p for p in predictions if p.error]
    if failing_items:
        lines += ["", "## Failures"]
        for p in failing_items[:20]:
            lines.append(f"- {p.input_id}: {p.error}")
    return "\n".join(lines) + "\n"


def _persist_to_db(root: Path, run_id: str, metrics: dict, profile: ScoringProfile) -> None:
    con = db.connect(root)
    updates: dict[str, Any] = {
        "aggregate_score": metrics["aggregate"],
        "scoring_profile": metrics["scoring_profile"],
        "scored_at": datetime.now(timezone.utc),
    }
    for name, value in metrics["scores"].items():
        col = METRIC_KEY_TO_DB_COLUMN.get(name)
        if col:
            updates[col] = value
    db.update_run(con, run_id, **updates)
    con.close()


def _transition_bundle_safe(root: Path, bundle_id: str) -> None:
    bundle = bundle_manager.get_bundle(bundle_id, root=root)
    if bundle.state == BundleState.DRAFT:
        try:
            bundle_manager.transition_bundle(
                bundle_id, BundleState.EVALUATED, root=root
            )
        except InvalidTransitionError:
            pass
    # idempotent: past-draft states are left untouched
