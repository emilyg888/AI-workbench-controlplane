"""Enforces control-plane / runtime-plane separation.

See docs/PLANES.md for the contract. This test AST-parses every
runtime-plane module and asserts that no forbidden mutation call names
appear.
"""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "workbench"


RUNTIME_MODULES = [
    SRC / "runtime_resolver.py",
    SRC / "runtime_compare.py",
    SRC / "adapters" / "base.py",
    SRC / "adapters" / "model_ollama.py",
    SRC / "adapters" / "model_stub.py",
    SRC / "adapters" / "retrieval_stub.py",
    SRC / "adapters" / "retrieval_file.py",
    SRC / "adapters" / "retrieval_chroma.py",
    SRC / "adapters" / "registry.py",
    SRC / "policy" / "enforcer.py",
    SRC / "serving" / "invoke.py",
    SRC / "serving" / "http.py",
]


FORBIDDEN = {
    # bundle_manager
    "create_bundle", "transition_bundle", "snapshot_bundle",
    # deployment_state_manager
    "set_active", "undeploy",
    # promotion_engine
    "propose", "approve", "reject",
    # rollback
    "rollback",
    # experiment / evaluation
    "run_experiment", "evaluate_run",
}


def _calls_in(path: Path) -> set[str]:
    """Return the set of attribute-style call names (``x.foo``) in the file."""
    tree = ast.parse(path.read_text())
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)
    return calls


def test_runtime_makes_no_control_plane_calls() -> None:
    leaks: dict[str, set[str]] = {}
    for path in RUNTIME_MODULES:
        assert path.exists(), f"missing runtime module: {path}"
        called = _calls_in(path)
        bad = called & FORBIDDEN
        if bad:
            leaks[path.name] = bad
    assert not leaks, f"runtime → control-plane mutation leaks: {leaks}"


def test_runtime_modules_documented() -> None:
    """Each non-trivial runtime module should have a module docstring."""
    required_stems = {
        "runtime_resolver", "runtime_compare",
        "invoke", "http", "enforcer", "base",
    }
    missing: list[str] = []
    for path in RUNTIME_MODULES:
        if path.stem not in required_stems:
            continue
        tree = ast.parse(path.read_text())
        if ast.get_docstring(tree) is None:
            missing.append(str(path.relative_to(SRC)))
    assert not missing, f"missing module docstring: {missing}"
