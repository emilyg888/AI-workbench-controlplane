from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from . import (
    bundle_manager,
    comparison,
    db,
    deployment_state_manager,
    evaluation_engine,
    experiment_runner,
    promotion_engine,
)
from .models import BundleState
from .state_machine import InvalidTransitionError
from .storage import ensure_registry_files, find_workbench_root, read_json

app = typer.Typer(add_completion=False, help="AI Workbench Control Plane CLI")
console = Console()
err = Console(stderr=True)

EXIT_OK = 0
EXIT_ERR = 1
EXIT_VALIDATION = 2
EXIT_NOT_FOUND = 3
EXIT_CONFLICT = 4


def _fail(msg: str, code: int) -> None:
    err.print(f"[red]error:[/red] {msg}")
    raise typer.Exit(code=code)


def _root_or_fail() -> Path:
    try:
        return find_workbench_root()
    except FileNotFoundError as e:
        _fail(str(e), EXIT_ERR)
        raise  # unreachable


@app.command()
def init(
    path: Path = typer.Option(Path.cwd(), "--path", help="Workbench root directory."),
    force: bool = typer.Option(False, "--force", help="Overwrite non-empty registry files."),
) -> None:
    """Create scaffold + seed registry/configs files (idempotent)."""
    root = path.resolve()
    touched = ensure_registry_files(root, force=force)
    if touched:
        console.print(f"[green]✓[/green] Initialised {root} scaffold "
                      f"(seeded {len(touched)} file(s))")
    else:
        console.print(f"[green]✓[/green] {root} already initialised (no changes)")


@app.command("create-bundle")
def create_bundle(
    name: str = typer.Option(..., "--name", help="Bundle name (lowercase)."),
    version: str = typer.Option(..., "--version", help="Semver X.Y.Z."),
    from_file: Path = typer.Option(..., "--from-file", help="Bundle JSON file."),
) -> None:
    """Register a new bundle in draft state."""
    root = _root_or_fail()
    try:
        spec = json.loads(from_file.read_text())
    except FileNotFoundError:
        _fail(f"file not found: {from_file}", EXIT_NOT_FOUND)
    except json.JSONDecodeError as e:
        _fail(f"invalid JSON in {from_file}: {e}", EXIT_VALIDATION)

    spec["name"] = name
    spec["version"] = version

    try:
        bundle = bundle_manager.create_bundle(spec, root=root)
    except ValidationError as e:
        _fail(f"schema validation failed:\n{e}", EXIT_VALIDATION)
    except bundle_manager.DuplicateBundleError as e:
        _fail(str(e), EXIT_CONFLICT)
    except ValueError as e:
        _fail(str(e), EXIT_VALIDATION)

    console.print(
        f"[green]✓[/green] Created bundle [bold]{bundle.bundle_id}[/bold] "
        f"(state={bundle.state.value})"
    )


@app.command("list-bundles")
def list_bundles(
    state: str | None = typer.Option(None, "--state", help="Filter by state."),
    name: str | None = typer.Option(None, "--name", help="Filter by name."),
) -> None:
    """List bundles, optionally filtered."""
    root = _root_or_fail()
    bundles = bundle_manager.list_bundles(state=state, name=name, root=root)
    if not bundles:
        console.print("[dim](no bundles)[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    for col in ("BUNDLE_ID", "NAME", "VERSION", "STATE", "UPDATED_AT"):
        table.add_column(col)
    for b in bundles:
        table.add_row(b.bundle_id, b.name, b.version, b.state.value, b.updated_at)
    console.print(table)


@app.command("show-bundle")
def show_bundle(bundle_id: str = typer.Argument(...)) -> None:
    """Print a bundle's full JSON record."""
    root = _root_or_fail()
    try:
        b = bundle_manager.get_bundle(bundle_id, root=root)
    except bundle_manager.BundleNotFoundError as e:
        _fail(str(e), EXIT_NOT_FOUND)
    console.print_json(data=b.model_dump(mode="json"))


@app.command("show-active")
def show_active(env: str | None = typer.Option(None, "--env", help="dev|prod")) -> None:
    """Show active bundle per environment."""
    root = _root_or_fail()
    envs = [env] if env else deployment_state_manager.list_environments(root=root)
    out = []
    for e in envs:
        try:
            dep = deployment_state_manager.get_active(e, root=root)
        except deployment_state_manager.UnknownEnvironmentError as exc:
            _fail(str(exc), EXIT_NOT_FOUND)
        out.append({"env": e, **dep.model_dump(mode="json")})
    if len(out) == 1:
        console.print_json(data=out[0])
    else:
        console.print_json(data=out)


@app.command("set-state")
def set_state(
    bundle_id: str = typer.Argument(...),
    new_state: str = typer.Argument(
        ..., help="draft|evaluated|candidate|approved|deployed|archived"
    ),
) -> None:
    """Transition a bundle to a new state (gated by state machine)."""
    root = _root_or_fail()
    try:
        target = BundleState(new_state)
    except ValueError:
        _fail(f"unknown state: {new_state!r}", EXIT_VALIDATION)

    try:
        before = bundle_manager.get_bundle(bundle_id, root=root)
        bundle_manager.transition_bundle(bundle_id, target, root=root)
    except bundle_manager.BundleNotFoundError as e:
        _fail(str(e), EXIT_NOT_FOUND)
    except InvalidTransitionError as e:
        _fail(str(e), EXIT_VALIDATION)

    console.print(
        f"[green]✓[/green] Transitioned {bundle_id}: "
        f"{before.state.value} → {target.value}"
    )


# ---------------------------------------------------------------------------
# Phase 2: experiment execution
# ---------------------------------------------------------------------------


@app.command("run-experiment")
def run_experiment_cmd(
    bundle: str = typer.Option(..., "--bundle", help="Bundle id to execute."),
    eval_set: str = typer.Option(..., "--eval-set", help="Eval set name or path."),
    limit: int | None = typer.Option(None, "--limit", help="Cap the number of inputs."),
) -> None:
    """Run a bundle against an eval set; writes run artifact + DuckDB row."""
    root = _root_or_fail()
    try:
        result = experiment_runner.run_experiment(bundle, eval_set, limit=limit, root=root)
    except bundle_manager.BundleNotFoundError as e:
        _fail(str(e), EXIT_NOT_FOUND)
    except experiment_runner.EvalSetNotFoundError as e:
        _fail(str(e), EXIT_NOT_FOUND)
    except Exception as e:
        _fail(f"run failed: {e}", EXIT_ERR)

    console.print(
        f"[green]✓[/green] Run complete: [bold]{result.run_id}[/bold]\n"
        f"  {result.succeeded} succeeded, {result.failed} failed, "
        f"p50={result.p50_latency_ms}ms, p95={result.p95_latency_ms}ms\n"
        f"  Artifacts: {result.run_dir}"
    )


@app.command("list-runs")
def list_runs_cmd(
    bundle: str | None = typer.Option(None, "--bundle"),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """Tabular list of runs from DuckDB."""
    root = _root_or_fail()
    con = db.connect(root)
    rows = db.list_runs(con, bundle_id=bundle, limit=limit)
    con.close()
    if not rows:
        console.print("[dim](no runs)[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    for col in ("RUN_ID", "BUNDLE", "EVAL_SET", "STATUS", "P50", "P95"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["run_id"], r["bundle_id"], r["eval_set"],
            str(r.get("status") or ""),
            str(r.get("p50_latency_ms") or ""),
            str(r.get("p95_latency_ms") or ""),
        )
    console.print(table)


@app.command("show-run")
def show_run_cmd(run_id: str = typer.Argument(...)) -> None:
    """Pretty-print a run's config.json + timings summary."""
    root = _root_or_fail()
    run_dir = root / "runs" / run_id
    if not run_dir.exists():
        _fail(f"run not found: {run_id}", EXIT_NOT_FOUND)
    config = read_json(run_dir / "config.json")
    timings = read_json(run_dir / "timings.json")
    console.print("[bold]Config[/bold]")
    console.print_json(data=config)
    console.print("[bold]Timings[/bold]")
    console.print_json(data=timings)


# ---------------------------------------------------------------------------
# Phase 3: evaluation engine
# ---------------------------------------------------------------------------


@app.command("eval")
def eval_cmd(
    run_id: str = typer.Argument(...),
    profile: str | None = typer.Option(None, "--profile"),
    baseline: str | None = typer.Option(None, "--baseline"),
) -> None:
    """Score a run; writes metrics.json + scorecard.md."""
    root = _root_or_fail()
    try:
        result = evaluation_engine.evaluate_run(
            run_id, profile_name=profile, baseline_run_id=baseline, root=root
        )
    except FileNotFoundError as e:
        _fail(str(e), EXIT_NOT_FOUND)
    lines = [f"{k:20s} {v:.3f}" for k, v in result.scores.items()]
    console.print("\n".join(lines))
    console.print(f"[bold]aggregate           {result.aggregate:.3f}[/bold]")
    console.print(
        f"[green]✓[/green] Wrote metrics.json + scorecard.md for {run_id}"
    )


@app.command("show-scorecard")
def show_scorecard_cmd(run_id: str = typer.Argument(...)) -> None:
    root = _root_or_fail()
    p = root / "runs" / run_id / "scorecard.md"
    if not p.exists():
        _fail(f"scorecard missing: {p}", EXIT_NOT_FOUND)
    console.print(p.read_text(encoding="utf-8"))


@app.command("compare-runs")
def compare_runs_cmd(
    candidate_run_id: str = typer.Argument(...),
    baseline: str = typer.Option(..., "--baseline"),
) -> None:
    root = _root_or_fail()
    cand = root / "runs" / candidate_run_id / "metrics.json"
    base = root / "runs" / baseline / "metrics.json"
    if not cand.exists():
        _fail(f"candidate metrics missing: {cand}", EXIT_NOT_FOUND)
    if not base.exists():
        _fail(f"baseline metrics missing: {base}", EXIT_NOT_FOUND)
    report = comparison.compare(read_json(base), read_json(cand))
    table = Table(show_header=True, header_style="bold")
    for col in ("METRIC", "BASELINE", "CANDIDATE", "DELTA", "DIR"):
        table.add_column(col)
    for d in report.deltas:
        b = "—" if d.baseline is None else f"{d.baseline:.3f}"
        c = "—" if d.candidate is None else f"{d.candidate:.3f}"
        dd = "—" if d.delta is None else f"{d.delta:+.3f}"
        arrow = "↑" if d.direction == "up" else (
            "↓ regression" if d.direction == "down" else (
                "·" if d.direction == "flat" else "?"
            )
        )
        table.add_row(d.metric, b, c, dd, arrow)
    console.print(table)
    if report.any_regression:
        console.print("[red]Regressions detected[/red]")


# ---------------------------------------------------------------------------
# Phase 4: promotion workflow
# ---------------------------------------------------------------------------


@app.command("propose-promotion")
def propose_promotion_cmd(
    run_id: str = typer.Argument(...),
    rules: str | None = typer.Option(None, "--rules"),
) -> None:
    """Run the promotion engine; may transition bundle to candidate/approved/rejected."""
    root = _root_or_fail()
    try:
        decision = promotion_engine.propose(run_id, rules_profile=rules, root=root)
    except FileNotFoundError as e:
        _fail(str(e), EXIT_NOT_FOUND)
    except bundle_manager.BundleNotFoundError as e:
        _fail(str(e), EXIT_NOT_FOUND)

    console.print(
        f"[green]✓[/green] Decision: [bold]{decision.result}[/bold] "
        f"(approver={decision.approver})\n"
        f"  Decision ID: {decision.decision_id}"
    )


@app.command("approve")
def approve_cmd(
    bundle_id: str = typer.Argument(...),
    notes: str | None = typer.Option(None, "--notes"),
) -> None:
    root = _root_or_fail()
    try:
        decision = promotion_engine.approve(
            bundle_id, approver="manual", notes=notes, root=root
        )
    except bundle_manager.BundleNotFoundError as e:
        _fail(str(e), EXIT_NOT_FOUND)
    except InvalidTransitionError as e:
        _fail(str(e), EXIT_VALIDATION)
    console.print(f"[green]✓[/green] Approved {bundle_id} ({decision.decision_id})")


@app.command("reject")
def reject_cmd(
    bundle_id: str = typer.Argument(...),
    reason: str = typer.Option(..., "--reason"),
) -> None:
    root = _root_or_fail()
    try:
        decision = promotion_engine.reject(bundle_id, reason, root=root)
    except bundle_manager.BundleNotFoundError as e:
        _fail(str(e), EXIT_NOT_FOUND)
    except promotion_engine.PromotionError as e:
        _fail(str(e), EXIT_VALIDATION)
    console.print(f"[yellow]✗[/yellow] Rejected {bundle_id} ({decision.decision_id})")


@app.command("show-promotion-log")
def show_promotion_log_cmd(
    bundle: str | None = typer.Option(None, "--bundle"),
) -> None:
    root = _root_or_fail()
    entries = promotion_engine.read_log(root=root)
    if bundle:
        entries = [e for e in entries if e.get("bundle_id") == bundle]
    if not entries:
        console.print("[dim](no decisions)[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    for col in ("DECISION_ID", "BUNDLE", "RESULT", "APPROVER", "AT"):
        table.add_column(col)
    for e in entries:
        table.add_row(e["decision_id"], e["bundle_id"], e["result"],
                      e.get("approver", ""), e.get("decided_at", ""))
    console.print(table)


# ---------------------------------------------------------------------------
# Phase 5: environment deployment states
# ---------------------------------------------------------------------------


def _deploy(env: str, bundle_id: str, notes: str | None) -> None:
    root = _root_or_fail()
    try:
        dep = deployment_state_manager.set_active(
            env, bundle_id, notes=notes, root=root
        )
    except deployment_state_manager.UnknownEnvironmentError as e:
        _fail(str(e), EXIT_NOT_FOUND)
    except deployment_state_manager.PreconditionError as e:
        _fail(str(e), EXIT_VALIDATION)
    console.print(
        f"[green]✓[/green] {env} → [bold]{bundle_id}[/bold] "
        f"(activated {dep.activated_at})"
    )


@app.command("deploy-to-dev")
def deploy_to_dev_cmd(
    bundle_id: str = typer.Argument(...),
    notes: str | None = typer.Option(None, "--notes"),
) -> None:
    _deploy("dev", bundle_id, notes)


@app.command("deploy-to-prod")
def deploy_to_prod_cmd(
    bundle_id: str = typer.Argument(...),
    notes: str | None = typer.Option(None, "--notes"),
) -> None:
    _deploy("prod", bundle_id, notes)


@app.command("undeploy")
def undeploy_cmd(
    env: str = typer.Option(..., "--env"),
    reason: str | None = typer.Option(None, "--reason"),
) -> None:
    root = _root_or_fail()
    try:
        deployment_state_manager.undeploy(env, reason=reason, root=root)
    except deployment_state_manager.UnknownEnvironmentError as e:
        _fail(str(e), EXIT_NOT_FOUND)
    console.print(f"[yellow]✗[/yellow] Undeployed {env}")


@app.command("show-deployment-history")
def show_deployment_history_cmd(
    env: str | None = typer.Option(None, "--env"),
    bundle: str | None = typer.Option(None, "--bundle"),
) -> None:
    root = _root_or_fail()
    events = deployment_state_manager.history(env=env, bundle_id=bundle, root=root)
    if not events:
        console.print("[dim](no events)[/dim]")
        return
    table = Table(show_header=True, header_style="bold")
    for col in ("EVENT_ID", "ENV", "ACTION", "BUNDLE", "PREVIOUS", "AT"):
        table.add_column(col)
    for e in events:
        table.add_row(e.event_id, e.env, e.action,
                      e.bundle_id or "—", e.previous_bundle_id or "—", e.at)
    console.print(table)


if __name__ == "__main__":
    app()
