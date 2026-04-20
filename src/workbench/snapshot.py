"""Materialise a bundle's ``*_ref`` pointers into a frozen snapshot.

Called at approval time. After this runs, the bundle record carries the
*contents* of the prompt / policy pack / retrieval profile / scoring
profile — not just pointers. Later edits to the source files cannot
change runtime behaviour.

Retrieval corpora are fingerprinted (not inlined) because they can be
large. Model weights can't be snapshotted locally; where possible the
Ollama ``digest`` is captured as a drift-detection hook.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import yaml

from .models import Bundle, ResolvedComponents, ResolvedRetrieval, utcnow_iso
from .storage import find_workbench_root, sha256_file


class SnapshotError(RuntimeError):
    pass


def _resolve_path(root: Path, ref: str) -> Path:
    p = Path(ref)
    return p if p.is_absolute() else root / p


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(_read_text(path)) or {}


def _corpus_fingerprint(path: Path) -> tuple[str, int]:
    """Stream a JSONL corpus, returning (sha256, line_count)."""
    h = hashlib.sha256()
    count = 0
    with path.open("rb") as f:
        for line in f:
            if line.strip():
                h.update(line)
                count += 1
    return h.hexdigest(), count


def _try_ollama_digest(model_name: str) -> str | None:
    """Best-effort Ollama model digest via HTTP. Returns None on any error."""
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    try:
        import httpx
        with httpx.Client(timeout=2.0) as client:
            r = client.post(f"{host}/api/show", json={"name": model_name})
        if r.status_code != 200:
            return None
        body = r.json()
        return body.get("digest") or body.get("details", {}).get("digest")
    except Exception:
        return None


def _snapshot_retrieval(
    root: Path, bundle: Bundle
) -> ResolvedRetrieval:
    profile_ref = bundle.components.retrieval.profile_ref
    if profile_ref.startswith("stub") or profile_ref == "stub":
        return ResolvedRetrieval()

    # File-backed retriever: corpus lives at data/retrieval/<profile>.jsonl
    candidates = [
        _resolve_path(root, profile_ref),
        root / "data" / "retrieval" / f"{profile_ref}.jsonl",
    ]
    for p in candidates:
        if p.exists() and p.suffix == ".jsonl":
            digest, n = _corpus_fingerprint(p)
            return ResolvedRetrieval(
                corpus_hash=digest,
                doc_count=n,
                source_path=str(p.relative_to(root) if p.is_relative_to(root)
                                else p),
            )
    return ResolvedRetrieval()


def snapshot_components(
    bundle: Bundle, root: Path | None = None, strict: bool = False
) -> ResolvedComponents:
    """Read + hash every referenced asset; return a ResolvedComponents.

    If ``strict`` is True, raises SnapshotError when a required asset is
    missing. Otherwise leaves the field as its default (None / {}).
    """
    root = root or find_workbench_root()
    c = bundle.components
    hashes: dict[str, str] = {}

    prompt_text: str | None = None
    prompt_path = _resolve_path(root, c.prompt.template_ref)
    if prompt_path.exists():
        prompt_text = _read_text(prompt_path)
        hashes["prompt"] = sha256_file(prompt_path)
    elif strict:
        raise SnapshotError(f"prompt template missing: {prompt_path}")

    policy_rules: dict[str, Any] = {}
    policy_path = _resolve_path(root, c.policy.pack_ref)
    if policy_path.exists():
        policy_rules = _read_yaml(policy_path)
        hashes["policy"] = sha256_file(policy_path)
    elif strict:
        raise SnapshotError(f"policy pack missing: {policy_path}")

    retrieval_config: dict[str, Any] = {}
    rp = _resolve_path(root, c.retrieval.profile_ref)
    if rp.exists() and rp.suffix in (".yaml", ".yml"):
        retrieval_config = _read_yaml(rp)
        hashes["retrieval"] = sha256_file(rp)

    retrieval = _snapshot_retrieval(root, bundle)
    if retrieval.corpus_hash:
        hashes["retrieval_corpus"] = retrieval.corpus_hash

    scoring_profile: dict[str, Any] = {}
    sp = _resolve_path(root, c.evaluation.profile_ref)
    if sp.exists() and sp.suffix in (".yaml", ".yml"):
        scoring_profile = _read_yaml(sp)
        hashes["evaluation"] = sha256_file(sp)

    semantic: dict[str, Any] | None = None
    if c.semantic_layer.ref:
        p = _resolve_path(root, c.semantic_layer.ref)
        if p.exists() and p.suffix in (".yaml", ".yml"):
            semantic = _read_yaml(p)
            hashes["semantic"] = sha256_file(p)

    signal: dict[str, Any] | None = None
    if c.signal_layer.ref:
        p = _resolve_path(root, c.signal_layer.ref)
        if p.exists() and p.suffix in (".yaml", ".yml"):
            signal = _read_yaml(p)
            hashes["signal"] = sha256_file(p)

    provider = bundle.components.model.provider.lower()
    if provider in ("local-ollama", "ollama"):
        digest = _try_ollama_digest(bundle.components.model.name)
        if digest:
            hashes["model"] = digest

    return ResolvedComponents(
        resolved_at=utcnow_iso(),
        prompt_text=prompt_text,
        policy_rules=policy_rules,
        retrieval_config=retrieval_config,
        retrieval=retrieval,
        scoring_profile=scoring_profile,
        semantic_layer=semantic,
        signal_layer=signal,
        hashes=hashes,
    )
