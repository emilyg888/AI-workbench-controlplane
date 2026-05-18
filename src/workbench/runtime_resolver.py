"""Runtime plane: resolve the active bundle for an env into an
executable runtime (model + retrieval + policy + prompt).

See design/architecture.md. Reads the registry via ``bundle_manager.get_bundle``
and ``deployment_state_manager.get_active_full``; never mutates.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import bundle_manager, deployment_state_manager
from .adapters.base import ModelAdapter, RetrievalAdapter
from .adapters.registry import (
    get_model_adapter,
    get_retrieval_adapter,
    try_register_lmstudio,
    try_register_ollama,
)
from .environments import load_environments
from .models import Bundle
from .policy.enforcer import PolicyEnforcer
from .storage import find_workbench_root


class NoActiveBundleError(LookupError):
    pass


@dataclass
class ResolvedRuntime:
    env: str
    bundle: Bundle
    model: ModelAdapter
    retrieval: RetrievalAdapter
    policy: PolicyEnforcer
    prompt_template: str
    activated_at: str | None


_CACHE: dict[str, tuple[tuple, ResolvedRuntime]] = {}


def invalidate_cache() -> None:
    _CACHE.clear()


def _load_prompt(root: Path, ref: str) -> str:
    p = Path(ref)
    if not p.is_absolute():
        p = root / p
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "Answer the question. If context is provided, use it."


def _prompt_from_bundle(root: Path, bundle: Bundle) -> str:
    """Prefer snapshotted prompt_text; fall back to live ``template_ref``."""
    if bundle.resolved and bundle.resolved.prompt_text is not None:
        return bundle.resolved.prompt_text
    return _load_prompt(root, bundle.components.prompt.template_ref)


def resolve(env: str, root: Path | None = None) -> ResolvedRuntime:
    root = root or find_workbench_root()
    dep = deployment_state_manager.get_active_full(env, root=root)
    if dep.active_bundle_id is None:
        raise NoActiveBundleError(f"no active bundle in env={env!r}")

    key = (env, dep.active_bundle_id, dep.activated_at)
    hit = _CACHE.get(env)
    if hit and hit[0] == key:
        return hit[1]

    bundle = bundle_manager.get_bundle(dep.active_bundle_id, root=root)

    try_register_ollama()
    try_register_lmstudio()

    model = get_model_adapter(
        {
            "provider": bundle.components.model.provider,
            "name": bundle.components.model.name,
            **bundle.components.model.params,
        },
        root=root,
    )
    retrieval = get_retrieval_adapter(
        bundle.components.retrieval.profile_ref, root=root
    )
    policy = PolicyEnforcer(
        bundle.components.policy.pack_ref,
        root=root,
        frozen_rules=(bundle.resolved.policy_rules
                      if bundle.resolved else None),
    )
    prompt_template = _prompt_from_bundle(root, bundle)

    resolved = ResolvedRuntime(
        env=env,
        bundle=bundle,
        model=model,
        retrieval=retrieval,
        policy=policy,
        prompt_template=prompt_template,
        activated_at=dep.activated_at,
    )
    _CACHE[env] = (key, resolved)
    return resolved


def _build_runtime_for_bundle(bundle: Bundle, root: Path) -> ResolvedRuntime:
    try_register_ollama()
    try_register_lmstudio()
    model = get_model_adapter(
        {"provider": bundle.components.model.provider,
         "name": bundle.components.model.name,
         **bundle.components.model.params},
        root=root,
    )
    retrieval = get_retrieval_adapter(
        bundle.components.retrieval.profile_ref, root=root
    )
    policy = PolicyEnforcer(
        bundle.components.policy.pack_ref,
        root=root,
        frozen_rules=(bundle.resolved.policy_rules
                      if bundle.resolved else None),
    )
    prompt = _prompt_from_bundle(root, bundle)
    return ResolvedRuntime(
        env="challenger",
        bundle=bundle,
        model=model,
        retrieval=retrieval,
        policy=policy,
        prompt_template=prompt,
        activated_at=None,
    )


def challenger_config(env: str, root: Path | None = None) -> dict | None:
    root = root or find_workbench_root()
    envs = load_environments(root)
    cfg = envs.get(env)
    if cfg is None:
        return None
    return cfg.extras.get("challenger")


def resolve_challenger(env: str, root: Path | None = None) -> ResolvedRuntime | None:
    root = root or find_workbench_root()
    cfg = challenger_config(env, root=root)
    if not cfg or not cfg.get("enabled"):
        return None
    bundle_id = cfg.get("bundle_id")
    if not bundle_id:
        return None
    bundle = bundle_manager.get_bundle(bundle_id, root=root)
    return _build_runtime_for_bundle(bundle, root)
