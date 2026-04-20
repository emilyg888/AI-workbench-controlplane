from __future__ import annotations

from pathlib import Path

import pytest

from workbench import bundle_manager

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

UI_APP = str(
    Path(__file__).parent.parent / "src" / "workbench" / "ui" / "app.py"
)


def test_app_loads_home(workbench_root: Path, stub_bundle_spec: dict) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    at = AppTest.from_file(UI_APP, default_timeout=10)
    at.run()
    assert not at.exception
    assert any("Home" in str(h.value) for h in at.header)


def test_bundles_page_lists_bundles(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    bundle_manager.create_bundle(stub_bundle_spec, root=workbench_root)
    at = AppTest.from_file(UI_APP, default_timeout=10)
    at.run()
    at.sidebar.radio[0].set_value("Bundles").run()
    assert not at.exception


def test_no_direct_registry_access_in_ui() -> None:
    """SPEC §10: grep -r 'bundles.json' src/workbench/ui returns nothing
    (except data.py which doesn't touch it either)."""
    import subprocess
    ui_dir = Path(__file__).parent.parent / "src" / "workbench" / "ui"
    result = subprocess.run(
        ["grep", "-r", "registry/bundles.json", str(ui_dir)],
        capture_output=True, text=True,
    )
    assert result.stdout == "", f"UI leaks registry access: {result.stdout}"
