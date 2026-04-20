from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from . import bundle_manager, deployment_state_manager
from .models import BundleState
from .state_machine import InvalidTransitionError
from .storage import ensure_registry_files, find_workbench_root

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


if __name__ == "__main__":
    app()
