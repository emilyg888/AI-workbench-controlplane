from __future__ import annotations

from pathlib import Path

from workbench import bundle_manager, lineage


def _spec(name, version, parent=None, base=None):
    base = base or {
        "components": {
            "model": {"name": "s", "provider": "stub"},
            "prompt": {"template_ref": "x"},
            "retrieval": {"profile_ref": "stub"},
            "policy": {"pack_ref": "x"},
            "evaluation": {"profile_ref": "x"},
        },
    }
    spec = {**base, "name": name, "version": version}
    if parent:
        spec["lineage"] = {"parent_bundle_id": parent}
    return spec


def test_lineage_tree(workbench_root: Path) -> None:
    bundle_manager.create_bundle(_spec("a", "1.0.0"), root=workbench_root)
    bundle_manager.create_bundle(_spec("a", "2.0.0", parent="a_v1"),
                                 root=workbench_root)
    bundle_manager.create_bundle(_spec("a", "3.0.0", parent="a_v2"),
                                 root=workbench_root)
    out = lineage.tree("a_v2", root=workbench_root)
    assert "a_v1" in out
    assert "a_v2" in out
    assert "a_v3" in out


def test_lineage_dot(workbench_root: Path) -> None:
    bundle_manager.create_bundle(_spec("a", "1.0.0"), root=workbench_root)
    bundle_manager.create_bundle(_spec("a", "2.0.0", parent="a_v1"),
                                 root=workbench_root)
    out = lineage.dot("a_v1", root=workbench_root)
    assert out.startswith("digraph")
    assert '"a_v1" -> "a_v2"' in out
