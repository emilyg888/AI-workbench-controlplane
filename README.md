# ai-workbench-controlplane

Local-first control plane for managing AI bundle lifecycle.

The core principle is that the model alone is not the deployable unit. A bundle is the deployable unit:

```text
bundle = model + prompt + retrieval + policy + evaluation profile
```

The project provides versioned bundle registration, experiment execution, evaluation-driven promotion, explicit dev/prod deployment state, runtime execution, rollback, lineage, evidence packs, and a Streamlit dashboard.

## Architecture Summary

The system has two logical planes:

- Control plane: creates bundles, runs experiments, evaluates results, applies promotion rules, manages deployments, performs rollback, and creates evidence.
- Runtime plane: resolves the active bundle for an environment, executes model/retrieval/policy adapters, serves responses, and writes inference telemetry.

Local JSON/YAML files, run artifact folders, and DuckDB provide the system of record. See `design/architecture.md` for the detailed architecture and governance notes.

## Repository Structure

```text
Cost Control/ Cost-management playbook and slide materials
configs/      Environment, scoring, and promotion rule configuration
data/         Demo eval sets, policies, prompts, retrieval, semantic, and signal folders
design/       Canonical architecture and pending-review issues
docs/         Phase specs and supporting presentation/reference materials
examples/     Example bundle definitions
registry/     Bundle, deployment, deployment history, and promotion log state
runs/         Runtime and evaluation artifacts; contents are ignored except .gitkeep
src/workbench Python package and CLI implementation
tests/        Pytest suite
```

## Setup

```bash
uv sync --extra dev
source .venv/bin/activate
workbench init
```

## Run

```bash
workbench create-bundle --name claims_bundle --version 1.0.0 \
  --from-file examples/claims_v1.json

workbench run-experiment --bundle claims_bundle_v1 --eval-set claims_smoke
workbench eval <run_id>
workbench propose-promotion <run_id>
workbench deploy-to-dev claims_bundle_v1
workbench invoke --env dev --input '{"question": "..."}'
```

Additional runtime surfaces:

```bash
workbench serve --env dev --port 8080
workbench ui
```

## Test / SIT

```bash
uv run pytest -q
uv run ruff check .
```

Housekeeping SIT on 2026-05-18: `uv run pytest -q` passed with 182 tests and `uv run ruff check .` passed.

## Configuration

- `configs/environments.json` defines local environments.
- `configs/promotion_rules.yaml` defines default promotion gates.
- `configs/scoring_profile.yaml` defines evaluation metrics.
- `.env` and `*.env` are ignored and should hold local-only secrets if needed.
- Optional runtime adapters can use local Ollama, LM Studio, or ChromaDB installations.

## Documentation

- Architecture: `design/architecture.md`
- Pending review issues: `design/issues-pending-review.md`
- Phase specifications: `docs/SPEC_phase1.md` through `docs/SPEC_phase8.md`

## Current Status

All eight project phases are implemented locally. The current test suite covers bundle lifecycle, evaluation, promotion, deployment, runtime resolution, serving, rollback, lineage, evidence packs, policy enforcement, adapter contracts, UI behavior, and control-plane/runtime-plane separation.
