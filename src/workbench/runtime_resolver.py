from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import bundle_manager, deployment_state_manager
from .adapters.base import ModelAdapter, RetrievalAdapter
from .adapters.registry import (
    get_model_adapter,
    get_retrieval_adapter,
    try_register_ollama,
)
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
    policy = PolicyEnforcer(bundle.components.policy.pack_ref, root=root)
    prompt_template = _load_prompt(root, bundle.components.prompt.template_ref)

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
