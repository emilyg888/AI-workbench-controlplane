from __future__ import annotations

from pathlib import Path

from workbench import bundle_manager, deployment_state_manager, runtime_resolver
from workbench.adapters.base import ModelResult
from workbench.adapters.registry import register_model_adapter
from workbench.models import BundleState
from workbench.serving.invoke import invoke as invoke_fn


def _approve_deploy(workbench_root: Path, spec: dict) -> str:
    bundle_manager.create_bundle(spec, root=workbench_root)
    bid = f"{spec['name']}_v{spec['version'].split('.')[0]}"
    for s in (BundleState.EVALUATED, BundleState.CANDIDATE, BundleState.APPROVED):
        bundle_manager.transition_bundle(bid, s, root=workbench_root)
    deployment_state_manager.set_active("dev", bid, root=workbench_root)
    runtime_resolver.invalidate_cache()
    return bid


def test_contract_max_prompt_blocks(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    spec = {**stub_bundle_spec}
    spec["components"] = {
        **spec["components"],
        "contract": {"max_prompt_chars": 10},
    }
    _approve_deploy(workbench_root, spec)
    result = invoke_fn("dev", {"question": "a very long question" * 20},
                       root=workbench_root)
    assert result.policy_action == "input_block"
    assert "max_prompt_chars" in result.output


def test_contract_required_output_keys(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    # Register a one-off model adapter that emits non-JSON so the schema
    # contract fails deterministically.
    class JsonlessAdapter:
        name = "jsonless"

        def generate(self, prompt: str, params: dict) -> ModelResult:
            return ModelResult(text="plain text, not JSON",
                               latency_ms=1, raw={})

    register_model_adapter("jsonless", lambda spec, root: JsonlessAdapter())

    spec = {**stub_bundle_spec, "name": "jc_bundle", "version": "1.0.0"}
    spec["components"] = {
        **spec["components"],
        "model": {"name": "jsonless", "provider": "jsonless"},
        "contract": {"required_output_keys": ["answer"]},
    }
    _approve_deploy(workbench_root, spec)
    result = invoke_fn("dev", {"question": "x"}, root=workbench_root)
    assert result.policy_action == "output_block"
    assert "JSON" in result.output or "missing" in result.output


def test_contract_min_output_chars(
    workbench_root: Path, stub_bundle_spec: dict
) -> None:
    class TinyAdapter:
        name = "tiny"

        def generate(self, prompt: str, params: dict) -> ModelResult:
            return ModelResult(text="ok", latency_ms=1, raw={})

    register_model_adapter("tiny", lambda spec, root: TinyAdapter())

    spec = {**stub_bundle_spec, "name": "tc_bundle", "version": "1.0.0"}
    spec["components"] = {
        **spec["components"],
        "model": {"name": "tiny", "provider": "tiny"},
        "contract": {"min_output_chars": 100},
    }
    _approve_deploy(workbench_root, spec)
    result = invoke_fn("dev", {"question": "x"}, root=workbench_root)
    assert result.policy_action == "output_block"
