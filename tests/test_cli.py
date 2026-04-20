from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from workbench.cli import app

runner = CliRunner()


def _write_spec(root: Path, spec: dict) -> Path:
    p = root / "bundle.json"
    p.write_text(json.dumps(spec))
    return p


def test_init_creates_scaffold(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "registry" / "bundles.json").exists()
    assert (tmp_path / "registry" / "deployments.json").exists()
    assert (tmp_path / "configs" / "environments.json").exists()


def test_init_idempotent(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--path", str(tmp_path)])
    r2 = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert r2.exit_code == 0


def test_create_list_show(workbench_root: Path, valid_bundle_spec: dict) -> None:
    spec_file = _write_spec(workbench_root, valid_bundle_spec)
    r = runner.invoke(
        app,
        ["create-bundle", "--name", "claims_bundle", "--version", "1.0.0",
         "--from-file", str(spec_file)],
    )
    assert r.exit_code == 0, r.output
    assert "claims_bundle_v1" in r.output

    r = runner.invoke(app, ["list-bundles"])
    assert r.exit_code == 0
    assert "claims_bundle_v1" in r.output

    r = runner.invoke(app, ["show-bundle", "claims_bundle_v1"])
    assert r.exit_code == 0
    assert "claims_bundle_v1" in r.output


def test_show_active_initial_null(workbench_root: Path) -> None:
    r = runner.invoke(app, ["show-active", "--env", "dev"])
    assert r.exit_code == 0
    assert "null" in r.output


def test_set_state_valid(workbench_root: Path, valid_bundle_spec: dict) -> None:
    spec_file = _write_spec(workbench_root, valid_bundle_spec)
    runner.invoke(app, ["create-bundle", "--name", "claims_bundle",
                        "--version", "1.0.0", "--from-file", str(spec_file)])
    r = runner.invoke(app, ["set-state", "claims_bundle_v1", "archived"])
    assert r.exit_code == 0
    assert "draft → archived" in r.output


def test_set_state_invalid_exit_code_2(workbench_root: Path, valid_bundle_spec: dict) -> None:
    spec_file = _write_spec(workbench_root, valid_bundle_spec)
    runner.invoke(app, ["create-bundle", "--name", "claims_bundle",
                        "--version", "1.0.0", "--from-file", str(spec_file)])
    r = runner.invoke(app, ["set-state", "claims_bundle_v1", "approved"])
    assert r.exit_code == 2


def test_show_missing_exit_code_3(workbench_root: Path) -> None:
    r = runner.invoke(app, ["show-bundle", "missing_v1"])
    assert r.exit_code == 3


def test_duplicate_exit_code_4(workbench_root: Path, valid_bundle_spec: dict) -> None:
    spec_file = _write_spec(workbench_root, valid_bundle_spec)
    runner.invoke(app, ["create-bundle", "--name", "claims_bundle",
                        "--version", "1.0.0", "--from-file", str(spec_file)])
    r = runner.invoke(app, ["create-bundle", "--name", "claims_bundle",
                            "--version", "1.0.0", "--from-file", str(spec_file)])
    assert r.exit_code == 4
