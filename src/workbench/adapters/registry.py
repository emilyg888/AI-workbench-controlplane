from __future__ import annotations

from pathlib import Path

from .base import ModelAdapter, RetrievalAdapter
from .model_stub import StubModelAdapter
from .retrieval_file import FileRetrievalAdapter
from .retrieval_stub import StubRetrievalAdapter


class AdapterError(RuntimeError):
    pass


_MODEL_FACTORIES: dict[str, object] = {
    "stub": lambda spec, root: StubModelAdapter(),
    "local-stub": lambda spec, root: StubModelAdapter(),
}


_RETRIEVAL_FACTORIES: dict[str, object] = {
    "stub": lambda profile_ref, root: StubRetrievalAdapter(),
    "file": lambda profile_ref, root: FileRetrievalAdapter(profile_ref, root=root),
}


def register_model_adapter(provider: str, factory) -> None:
    _MODEL_FACTORIES[provider] = factory


def register_retrieval_adapter(kind: str, factory) -> None:
    _RETRIEVAL_FACTORIES[kind] = factory


def get_model_adapter(spec: dict, root: Path | None = None) -> ModelAdapter:
    provider = spec.get("provider", "stub")
    try:
        factory = _MODEL_FACTORIES[provider]
    except KeyError:
        raise AdapterError(
            f"No model adapter registered for provider {provider!r}. "
            f"Known: {sorted(_MODEL_FACTORIES)}"
        ) from None
    return factory(spec, root)  # type: ignore[operator]


def get_retrieval_adapter(profile_ref: str, root: Path | None = None) -> RetrievalAdapter:
    """Pick a retrieval adapter based on the profile_ref convention:

    - ``stub`` or ``stub:*`` → StubRetrievalAdapter
    - anything else → FileRetrievalAdapter
    """
    if profile_ref == "stub" or profile_ref.startswith("stub:"):
        return _RETRIEVAL_FACTORIES["stub"](profile_ref, root)  # type: ignore[operator]
    return _RETRIEVAL_FACTORIES["file"](profile_ref, root)  # type: ignore[operator]


def try_register_ollama() -> bool:
    """Lazy import + register ollama adapter. Returns True if registered."""
    try:
        from .model_ollama import OllamaModelAdapter
    except Exception:
        return False
    _MODEL_FACTORIES["local-ollama"] = lambda spec, root: OllamaModelAdapter(spec)
    _MODEL_FACTORIES["ollama"] = lambda spec, root: OllamaModelAdapter(spec)
    return True


def try_register_chroma() -> bool:
    """Lazy import + register chroma adapter. Returns True if registered."""
    try:
        from .retrieval_chroma import ChromaRetrievalAdapter
    except Exception:
        return False

    def _factory(profile_ref: str, root: Path | None):
        return ChromaRetrievalAdapter(profile_ref, root=root)

    _RETRIEVAL_FACTORIES["chroma"] = _factory
    return True
