from __future__ import annotations

from pathlib import Path

import pytest

from workbench.storage import ensure_registry_files


@pytest.fixture
def workbench_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated workbench root for each test."""
    ensure_registry_files(tmp_path)
    monkeypatch.setenv("WORKBENCH_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def valid_bundle_spec() -> dict:
    return {
        "name": "claims_bundle",
        "version": "1.0.0",
        "components": {
            "model": {"name": "llama3.1-8b", "provider": "local-ollama"},
            "prompt": {"template_ref": "data/prompts/claims_v1.txt"},
            "retrieval": {"profile_ref": "data/retrieval/claims_profile.yaml"},
            "policy": {"pack_ref": "data/policies/claims_pack.yaml"},
            "evaluation": {"profile_ref": "configs/scoring_profile.yaml"},
        },
    }
