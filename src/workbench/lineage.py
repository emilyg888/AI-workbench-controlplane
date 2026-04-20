from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from . import bundle_manager
from .storage import find_workbench_root


def _load_all(root: Path) -> list:
    return bundle_manager.list_bundles(root=root)


def _index(bundles) -> tuple[dict[str, object], dict[str, list[str]]]:
    by_id = {b.bundle_id: b for b in bundles}
    children: dict[str, list[str]] = defaultdict(list)
    for b in bundles:
        parent = b.lineage.parent_bundle_id
        if parent:
            children[parent].append(b.bundle_id)
    return by_id, children


def tree(bundle_id: str, root: Path | None = None) -> str:
    root = root or find_workbench_root()
    by_id, children = _index(_load_all(root))
    if bundle_id not in by_id:
        raise KeyError(f"bundle not found: {bundle_id}")

    # climb to root ancestor for full tree
    ancestor = bundle_id
    seen = {ancestor}
    while by_id[ancestor].lineage.parent_bundle_id:
        parent = by_id[ancestor].lineage.parent_bundle_id
        if parent in seen:
            break  # cycle guard
        ancestor = parent
        seen.add(parent)

    lines: list[str] = []

    def render(node: str, prefix: str, is_last: bool) -> None:
        connector = "└── " if is_last else "├── " if prefix else ""
        b = by_id.get(node)
        label = f"{node} ({b.state.value})" if b else node
        lines.append(f"{prefix}{connector}{label}")
        kids = children.get(node, [])
        for i, k in enumerate(kids):
            new_prefix = prefix + ("    " if is_last else "│   " if prefix else "")
            render(k, new_prefix, i == len(kids) - 1)

    render(ancestor, "", True)
    return "\n".join(lines) + "\n"


def dot(bundle_id: str, root: Path | None = None) -> str:
    root = root or find_workbench_root()
    by_id, children = _index(_load_all(root))
    if bundle_id not in by_id:
        raise KeyError(f"bundle not found: {bundle_id}")

    # include everything connected to bundle_id's component
    to_visit = [bundle_id]
    seen: set[str] = set()
    while to_visit:
        n = to_visit.pop()
        if n in seen:
            continue
        seen.add(n)
        for k in children.get(n, []):
            to_visit.append(k)
        b = by_id.get(n)
        if b and b.lineage.parent_bundle_id:
            to_visit.append(b.lineage.parent_bundle_id)

    lines = ["digraph lineage {", '  rankdir=TB;',
             '  node [shape=box style=rounded];']
    for node in sorted(seen):
        b = by_id[node]
        lines.append(f'  "{node}" [label="{node}\\n{b.state.value}"];')
    for node in sorted(seen):
        b = by_id[node]
        parent = b.lineage.parent_bundle_id
        if parent and parent in seen:
            lines.append(f'  "{parent}" -> "{node}";')
    lines.append("}")
    return "\n".join(lines) + "\n"
