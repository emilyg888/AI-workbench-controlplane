from __future__ import annotations

from pydantic import BaseModel


REGRESSION_THRESHOLD = 0.02


class MetricDelta(BaseModel):
    metric: str
    baseline: float | None
    candidate: float | None
    delta: float | None
    direction: str  # "up", "down", "flat", "missing"
    regression: bool


class ComparisonReport(BaseModel):
    baseline_run_id: str | None
    candidate_run_id: str
    deltas: list[MetricDelta]
    any_regression: bool


def compare(
    baseline_metrics: dict,
    candidate_metrics: dict,
    strict_metrics: list[str] | None = None,
) -> ComparisonReport:
    base_scores = (baseline_metrics or {}).get("scores", {})
    cand_scores = candidate_metrics.get("scores", {})
    strict = set(strict_metrics or [])

    keys = sorted(set(base_scores) | set(cand_scores))
    deltas: list[MetricDelta] = []
    any_reg = False
    for k in keys:
        b = base_scores.get(k)
        c = cand_scores.get(k)
        if b is None or c is None:
            deltas.append(MetricDelta(
                metric=k, baseline=b, candidate=c, delta=None,
                direction="missing", regression=False,
            ))
            continue
        d = c - b
        if k in strict and d < 0:
            direction, reg = "down", True
        elif d >= REGRESSION_THRESHOLD:
            direction, reg = "up", False
        elif d <= -REGRESSION_THRESHOLD:
            direction, reg = "down", True
        else:
            direction, reg = "flat", False
        any_reg = any_reg or reg
        deltas.append(MetricDelta(
            metric=k, baseline=b, candidate=c, delta=d,
            direction=direction, regression=reg,
        ))

    return ComparisonReport(
        baseline_run_id=(baseline_metrics or {}).get("run_id"),
        candidate_run_id=candidate_metrics["run_id"],
        deltas=deltas,
        any_regression=any_reg,
    )


def render_markdown(report: ComparisonReport) -> str:
    lines = [
        f"# Comparison: {report.candidate_run_id}",
        f"**Baseline:** {report.baseline_run_id or 'none'}",
        "",
        "| Metric | Baseline | Candidate | Delta | Direction |",
        "|---|---|---|---|---|",
    ]
    arrow = {"up": "↑", "down": "↓ regression", "flat": "·", "missing": "?"}
    for d in report.deltas:
        b = "—" if d.baseline is None else f"{d.baseline:.3f}"
        c = "—" if d.candidate is None else f"{d.candidate:.3f}"
        delta = "—" if d.delta is None else f"{d.delta:+.3f}"
        lines.append(f"| {d.metric} | {b} | {c} | {delta} | {arrow[d.direction]} |")
    return "\n".join(lines) + "\n"
