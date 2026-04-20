from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import bundle_manager, deployment_state_manager
from .models import BundleState, utcnow_iso
from .promotion_rules import PromotionRules, load_promotion_rules, rules_tag
from .state_machine import InvalidTransitionError, assert_transition
from .storage import find_workbench_root, read_json, write_json_atomic

PROMO_LOG_PATH_REL = "registry/promotion_log.json"


class PromotionRulesNotFoundError(FileNotFoundError):
    pass


class PromotionError(RuntimeError):
    pass


class CheckResult(BaseModel):
    value: float | None
    threshold: float | None
    pass_: bool = Field(alias="pass")

    model_config = {"populate_by_name": True}


class Checks(BaseModel):
    thresholds: dict[str, CheckResult] = Field(default_factory=dict)
    regression: dict[str, Any] = Field(default_factory=dict)


class PromotionDecision(BaseModel):
    decision_id: str
    bundle_id: str
    run_id: str | None
    decided_at: str
    rules_profile: str
    result: str  # "approved" | "candidate" | "rejected"
    checks: Checks
    approver: str
    notes: str | None = None


def _rules_path(root: Path, name: str | None) -> Path:
    name = name or "default"
    if name == "default":
        return root / "configs" / "promotion_rules.yaml"
    return root / "configs" / f"promotion_rules_{name}.yaml"


def load_rules(name: str | None = None, root: Path | None = None) -> PromotionRules:
    root = root or find_workbench_root()
    p = _rules_path(root, name)
    if not p.exists():
        raise PromotionRulesNotFoundError(f"rules not found: {p}")
    return load_promotion_rules(p)


def _load_run_metrics(root: Path, run_id: str) -> dict:
    p = root / "runs" / run_id / "metrics.json"
    if not p.exists():
        raise FileNotFoundError(f"metrics.json missing for {run_id}")
    return read_json(p)


def _baseline_metrics(
    root: Path, rules: PromotionRules
) -> tuple[str | None, str | None, dict | None]:
    """Returns (baseline_bundle_id, baseline_run_id, baseline_metrics)."""
    if not rules.regression_checks.enabled:
        return None, None, None
    target = rules.regression_checks.baseline
    if target in ("prod", "dev"):
        try:
            dep = deployment_state_manager.get_active(target, root=root)
        except deployment_state_manager.UnknownEnvironmentError:
            return None, None, None
        if dep.active_bundle_id is None:
            return None, None, None
        latest = _latest_metrics_for_bundle(root, dep.active_bundle_id)
        if latest is None:
            return dep.active_bundle_id, None, None
        return dep.active_bundle_id, latest["run_id"], latest
    else:
        run_id = target
        p = root / "runs" / run_id / "metrics.json"
        if not p.exists():
            return None, None, None
        doc = read_json(p)
        return doc.get("bundle_id"), run_id, doc


def _latest_metrics_for_bundle(root: Path, bundle_id: str) -> dict | None:
    runs_dir = root / "runs"
    if not runs_dir.exists():
        return None
    candidates = []
    for d in runs_dir.iterdir():
        m = d / "metrics.json"
        if not m.exists():
            continue
        try:
            doc = read_json(m)
        except Exception:
            continue
        if doc.get("bundle_id") == bundle_id:
            candidates.append((doc.get("scored_at") or "", doc))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def _check_thresholds(
    metrics: dict, rules: PromotionRules
) -> tuple[dict[str, CheckResult], bool]:
    out: dict[str, CheckResult] = {}
    all_pass = True
    scores = metrics.get("scores", {})
    for name, th in rules.thresholds.items():
        value = metrics.get("aggregate") if name == "aggregate" else scores.get(name)
        ok = value is not None and value >= th
        out[name] = CheckResult(value=value, threshold=th, **{"pass": bool(ok)})
        if not ok:
            all_pass = False
    return out, all_pass


def _check_regression(
    candidate: dict, baseline: dict | None, rules: PromotionRules
) -> tuple[dict, bool]:
    info: dict[str, Any] = {"baseline_bundle_id": None,
                            "baseline_run_id": None, "violations": []}
    if baseline is None or not rules.regression_checks.enabled:
        return info, True
    info["baseline_bundle_id"] = baseline.get("bundle_id")
    info["baseline_run_id"] = baseline.get("run_id")
    drop = rules.regression_checks.max_absolute_drop
    strict = set(rules.regression_checks.strict_metrics)
    violations: list[dict] = []
    base_scores = baseline.get("scores", {})
    cand_scores = candidate.get("scores", {})
    for metric in sorted(set(base_scores) | set(cand_scores)):
        b = base_scores.get(metric)
        c = cand_scores.get(metric)
        if b is None or c is None:
            continue
        delta = c - b
        if metric in strict and delta < 0:
            violations.append({"metric": metric, "delta": round(delta, 4),
                               "rule": "strict_metric"})
        elif delta <= -drop:
            violations.append({"metric": metric, "delta": round(delta, 4),
                               "rule": f"max_absolute_drop ({drop})"})
    info["violations"] = violations
    return info, not violations


def _new_decision_id(bundle_id: str, now: datetime | None = None) -> str:
    ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"prom_{ts}_{bundle_id}"


def _append_log(root: Path, decision: PromotionDecision) -> None:
    p = root / PROMO_LOG_PATH_REL
    existing = read_json(p) if p.exists() else []
    existing.append(decision.model_dump(mode="json", by_alias=True))
    write_json_atomic(p, existing)


def _write_run_evidence(
    root: Path, run_id: str | None, decision: PromotionDecision,
    candidate_metrics: dict, rules: PromotionRules
) -> None:
    if not run_id:
        return
    rd = root / "runs" / run_id
    if not rd.exists():
        return
    write_json_atomic(rd / "promotion_decision.json",
                      decision.model_dump(mode="json", by_alias=True))
    (rd / "promotion_report.md").write_text(
        _render_report(decision, candidate_metrics, rules), encoding="utf-8"
    )


def _render_report(
    decision: PromotionDecision, metrics: dict, rules: PromotionRules
) -> str:
    lines = [
        f"# Promotion Decision — {decision.bundle_id}",
        "",
        f"**Result:** {decision.result} ({decision.approver})",
        f"**Rules profile:** {decision.rules_profile}",
        f"**Run:** {decision.run_id or 'n/a'}",
        "",
        "## Thresholds",
        "| Metric | Value | Threshold | Pass |",
        "|---|---|---|---|",
    ]
    for m, cr in decision.checks.thresholds.items():
        v = "—" if cr.value is None else f"{cr.value:.3f}"
        t = "—" if cr.threshold is None else f"{cr.threshold:.3f}"
        lines.append(f"| {m} | {v} | {t} | {'✓' if cr.pass_ else '✗'} |")
    reg = decision.checks.regression or {}
    lines += [
        "",
        f"## Regression vs baseline "
        f"({reg.get('baseline_bundle_id') or 'none'})",
    ]
    viols = reg.get("violations") or []
    if not viols:
        lines.append("No violations.")
    else:
        for v in viols:
            lines.append(f"- {v['metric']}: Δ={v['delta']:+.3f} ({v['rule']})")
    return "\n".join(lines) + "\n"


def propose(
    run_id: str, rules_profile: str | None = None, root: Path | None = None
) -> PromotionDecision:
    root = root or find_workbench_root()
    metrics = _load_run_metrics(root, run_id)
    bundle_id = metrics["bundle_id"]

    rules = load_rules(rules_profile, root=root)
    thresholds, thr_ok = _check_thresholds(metrics, rules)
    _, _, baseline = _baseline_metrics(root, rules)
    regression, reg_ok = _check_regression(metrics, baseline, rules)

    passes_gate = thr_ok and reg_ok

    bundle = bundle_manager.get_bundle(bundle_id, root=root)

    if not passes_gate:
        result = "rejected"
        if bundle.state not in (BundleState.REJECTED, BundleState.ARCHIVED):
            try:
                bundle_manager.transition_bundle(
                    bundle_id, BundleState.REJECTED, root=root
                )
            except InvalidTransitionError:
                pass
    else:
        if bundle.state == BundleState.EVALUATED:
            bundle_manager.transition_bundle(
                bundle_id, BundleState.CANDIDATE, root=root
            )
        result = "candidate"
        if rules.approval.approved_requires.mode == "auto":
            bundle_manager.transition_bundle(
                bundle_id, BundleState.APPROVED, root=root
            )
            result = "approved"

    decision = PromotionDecision(
        decision_id=_new_decision_id(bundle_id),
        bundle_id=bundle_id,
        run_id=run_id,
        decided_at=utcnow_iso(),
        rules_profile=rules_tag(rules),
        result=result,
        checks=Checks(thresholds=thresholds, regression=regression),
        approver="auto",
        notes=None,
    )
    _append_log(root, decision)
    _write_run_evidence(root, run_id, decision, metrics, rules)
    return decision


def approve(
    bundle_id: str, approver: str = "manual",
    notes: str | None = None, root: Path | None = None
) -> PromotionDecision:
    root = root or find_workbench_root()
    bundle = bundle_manager.get_bundle(bundle_id, root=root)
    assert_transition(bundle.state, BundleState.APPROVED)
    bundle_manager.transition_bundle(bundle_id, BundleState.APPROVED, root=root)
    decision = PromotionDecision(
        decision_id=_new_decision_id(bundle_id),
        bundle_id=bundle_id,
        run_id=None,
        decided_at=utcnow_iso(),
        rules_profile="manual",
        result="approved",
        checks=Checks(),
        approver=approver,
        notes=notes,
    )
    _append_log(root, decision)
    return decision


def reject(
    bundle_id: str, reason: str, root: Path | None = None
) -> PromotionDecision:
    root = root or find_workbench_root()
    bundle = bundle_manager.get_bundle(bundle_id, root=root)
    if bundle.state not in (BundleState.REJECTED, BundleState.ARCHIVED):
        try:
            bundle_manager.transition_bundle(
                bundle_id, BundleState.REJECTED, root=root
            )
        except InvalidTransitionError:
            raise PromotionError(
                f"cannot reject bundle in state {bundle.state.value}"
            ) from None
    decision = PromotionDecision(
        decision_id=_new_decision_id(bundle_id),
        bundle_id=bundle_id,
        run_id=None,
        decided_at=utcnow_iso(),
        rules_profile="manual",
        result="rejected",
        checks=Checks(),
        approver="manual",
        notes=reason,
    )
    _append_log(root, decision)
    return decision


def read_log(root: Path | None = None) -> list[dict]:
    root = root or find_workbench_root()
    p = root / PROMO_LOG_PATH_REL
    if not p.exists():
        return []
    return read_json(p) or []
