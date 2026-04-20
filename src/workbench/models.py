from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

BUNDLE_ID_RE = re.compile(r"^[a-z0-9_]+_v[0-9]+$")
NAME_RE = re.compile(r"^[a-z0-9_]+$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class BundleState(str, Enum):
    DRAFT = "draft"
    EVALUATED = "evaluated"
    CANDIDATE = "candidate"
    APPROVED = "approved"
    DEPLOYED = "deployed"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    provider: str
    params: dict[str, Any] = Field(default_factory=dict)


class PromptSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    template_ref: str
    version: str = "v1"


class RetrievalSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    profile_ref: str
    version: str = "v1"


class PolicySpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    pack_ref: str
    version: str = "v1"


class EvaluationSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    profile_ref: str
    version: str = "v1"


class LayerRef(BaseModel):
    ref: str | None = None


class BundleComponents(BaseModel):
    model: ModelSpec
    prompt: PromptSpec
    retrieval: RetrievalSpec
    policy: PolicySpec
    evaluation: EvaluationSpec
    semantic_layer: LayerRef = Field(default_factory=LayerRef)
    signal_layer: LayerRef = Field(default_factory=LayerRef)


class Lineage(BaseModel):
    parent_bundle_id: str | None = None
    notes: str | None = None


class Bundle(BaseModel):
    bundle_id: str
    name: str
    version: str
    state: BundleState = BundleState.DRAFT
    created_at: str
    updated_at: str
    created_by: str = "local-user"
    components: BundleComponents
    lineage: Lineage = Field(default_factory=Lineage)
    schema_version: str = "1"

    @field_validator("bundle_id")
    @classmethod
    def _valid_bundle_id(cls, v: str) -> str:
        if not BUNDLE_ID_RE.match(v):
            raise ValueError(f"bundle_id must match {BUNDLE_ID_RE.pattern!r}, got {v!r}")
        return v

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not NAME_RE.match(v):
            raise ValueError(f"name must match {NAME_RE.pattern!r}, got {v!r}")
        return v

    @field_validator("version")
    @classmethod
    def _valid_version(cls, v: str) -> str:
        if not SEMVER_RE.match(v):
            raise ValueError(f"version must be semver X.Y.Z, got {v!r}")
        return v

    @field_validator("created_at", "updated_at")
    @classmethod
    def _valid_iso(cls, v: str) -> str:
        datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v


class Deployment(BaseModel):
    active_bundle_id: str | None = None
    updated_at: str | None = None


class DeploymentState(BaseModel):
    dev: Deployment = Field(default_factory=Deployment)
    prod: Deployment = Field(default_factory=Deployment)


class Environment(BaseModel):
    description: str


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def derive_bundle_id(name: str, version: str) -> str:
    major = version.split(".", 1)[0]
    return f"{name}_v{major}"
