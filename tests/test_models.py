from __future__ import annotations

import pytest
from pydantic import ValidationError

from workbench.models import (
    Bundle,
    BundleState,
    derive_bundle_id,
    utcnow_iso,
)


def _full_spec(**overrides) -> dict:
    now = utcnow_iso()
    base = {
        "bundle_id": "claims_bundle_v1",
        "name": "claims_bundle",
        "version": "1.0.0",
        "state": "draft",
        "created_at": now,
        "updated_at": now,
        "components": {
            "model": {"name": "llama3.1-8b", "provider": "local-ollama"},
            "prompt": {"template_ref": "data/prompts/claims_v1.txt"},
            "retrieval": {"profile_ref": "data/retrieval/claims_profile.yaml"},
            "policy": {"pack_ref": "data/policies/claims_pack.yaml"},
            "evaluation": {"profile_ref": "configs/scoring_profile.yaml"},
        },
    }
    base.update(overrides)
    return base


def test_valid_bundle_parses() -> None:
    b = Bundle.model_validate(_full_spec())
    assert b.state == BundleState.DRAFT
    assert b.components.semantic_layer.ref is None


def test_bundle_id_regex() -> None:
    for bad in ["ClaimsBundle_v1", "claims_bundle", "claims-bundle_v1", "claims_bundle_v"]:
        with pytest.raises(ValidationError):
            Bundle.model_validate(_full_spec(bundle_id=bad))


def test_name_regex() -> None:
    with pytest.raises(ValidationError):
        Bundle.model_validate(_full_spec(name="Claims-Bundle"))


def test_version_semver() -> None:
    for bad in ["1.0", "v1.0.0", "1.0.0-beta"]:
        with pytest.raises(ValidationError):
            Bundle.model_validate(_full_spec(version=bad))


def test_state_enum() -> None:
    with pytest.raises(ValidationError):
        Bundle.model_validate(_full_spec(state="nonsense"))


def test_required_components() -> None:
    spec = _full_spec()
    del spec["components"]["model"]
    with pytest.raises(ValidationError):
        Bundle.model_validate(spec)


def test_derive_bundle_id() -> None:
    assert derive_bundle_id("claims_bundle", "1.0.0") == "claims_bundle_v1"
    assert derive_bundle_id("x", "12.3.4") == "x_v12"
