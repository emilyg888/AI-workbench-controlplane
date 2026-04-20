from __future__ import annotations

import json
from pathlib import Path

import pytest

from workbench.storage import ensure_registry_files, write_jsonl


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


@pytest.fixture
def stub_bundle_spec() -> dict:
    """Bundle spec whose adapters resolve without external services."""
    return {
        "name": "stub_bundle",
        "version": "1.0.0",
        "components": {
            "model": {"name": "stub", "provider": "stub"},
            "prompt": {"template_ref": "data/prompts/inline.txt"},
            "retrieval": {"profile_ref": "stub"},
            "policy": {"pack_ref": "data/policies/stub.yaml"},
            "evaluation": {"profile_ref": "configs/scoring_profile.yaml"},
        },
    }


@pytest.fixture
def tiny_eval_set(workbench_root: Path) -> str:
    """Writes a 3-item eval set to data/eval_sets/tiny.jsonl."""
    path = workbench_root / "data" / "eval_sets" / "tiny.jsonl"
    write_jsonl(path, [
        {"input_id": "t_001", "input": {"question": "What?"}, "expected": "what"},
        {"input_id": "t_002", "input": {"question": "Where?"}, "expected": "where"},
        {"input_id": "t_003", "input": {"question": "When?"}, "expected": "when"},
    ])
    return "tiny"


def write_bundle_file(root: Path, spec: dict) -> Path:
    p = root / "bundle.json"
    p.write_text(json.dumps(spec))
    return p
