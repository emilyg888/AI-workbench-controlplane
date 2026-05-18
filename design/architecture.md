# Architecture

## 1. Purpose

AI Workbench Controlplane is a local-first control plane for managing the lifecycle of AI bundles from authoring through experiment execution, evaluation, promotion, deployment, observation, rollback, and audit evidence.

The core design principle is that the model alone is not the deployable unit. A bundle is the deployable unit:

```text
bundle = model + prompt + retrieval + policy + evaluation profile
```

The project serves engineers and data practitioners who need a governed, reviewable path for moving AI configurations across local `dev` and `prod` environments without relying on cloud services.

## 2. Current System Shape

The repository is a Python package with a Typer CLI entry point named `workbench`. The implementation is split into:

- control-plane modules that mutate registry, evaluation, promotion, deployment, and audit state;
- runtime-plane modules that resolve and execute the active bundle;
- adapter modules for model and retrieval backends;
- scoring, policy, serving, and Streamlit UI modules;
- local JSON/YAML/DuckDB/filesystem state used as the system of record.

All eight implementation phases described in `docs/SPEC_phase1.md` through `docs/SPEC_phase8.md` are represented in the current codebase.

## 3. Component Map

| Component | Path | Responsibility | Key dependencies |
|---|---|---|---|
| CLI | `src/workbench/cli.py` | User-facing command surface for bundle, run, evaluation, promotion, deployment, runtime, governance, and UI workflows. | Typer, Rich, workbench modules |
| Bundle manager | `src/workbench/bundle_manager.py` | Create, read, list, transition, and snapshot bundle records. | `models`, `state_machine`, `storage` |
| Experiment runner | `src/workbench/experiment_runner.py` | Execute bundles against eval sets and write run artifacts. | adapters, `db`, `storage` |
| Evaluation engine | `src/workbench/evaluation_engine.py` | Score run outputs, write metrics and scorecards, and compare baselines. | scorers, scoring profiles, run artifacts |
| Promotion engine | `src/workbench/promotion_engine.py` | Apply promotion rules and write promotion decisions/log entries. | `promotion_rules`, `bundle_manager`, `state_machine` |
| Deployment state manager | `src/workbench/deployment_state_manager.py` | Track active bundle per environment and deployment history. | registry JSON, environment config |
| Runtime resolver | `src/workbench/runtime_resolver.py` | Resolve active environment state into model, retrieval, prompt, and policy runtime objects. | adapters, `bundle_manager`, `deployment_state_manager` |
| Serving | `src/workbench/serving/` | Synchronous invoke and FastAPI serving paths for active bundles. | runtime resolver, DuckDB telemetry |
| Runtime comparison | `src/workbench/runtime_compare.py` | Compare champion/challenger runtime telemetry over a time window. | DuckDB inference telemetry |
| Rollback | `src/workbench/rollback.py` | Revert an environment to a previous or explicit bundle. | deployment history, state manager |
| Evidence pack | `src/workbench/evidence_pack.py` | Build hash-verified audit packages for promotion decisions. | run artifacts, registry, promotion log |
| Lineage | `src/workbench/lineage.py` | Render bundle ancestry and relationship views. | bundle registry |
| Doctor | `src/workbench/doctor.py` | Validate registry integrity and optionally repair supported drift. | registry, configs |
| Policy enforcement | `src/workbench/policy/enforcer.py` | Apply pre- and post-model policy checks. | YAML policy packs |
| Adapters | `src/workbench/adapters/` | Model and retrieval backend contracts and implementations. | HTTPX, optional Ollama/LM Studio/Chroma |
| Scorers | `src/workbench/scorers/` | Pluggable scoring implementations for exact match, substring, policy, latency, refusal, and related metrics. | scoring profiles |
| UI | `src/workbench/ui/` | Streamlit dashboard for bundles, runs, deployments, promotions, and comparisons. | Streamlit, Altair |
| Tests | `tests/` | Unit and integration coverage, including plane-boundary checks. | pytest, respx, freezegun |

## 4. Runtime Flow

```text
Authoring input
  -> bundle registry
  -> experiment runner
  -> run artifacts and DuckDB run history
  -> evaluation engine
  -> promotion engine
  -> deployment state manager
  -> runtime resolver
  -> model/retrieval/policy adapters
  -> response and inference telemetry
  -> comparison, rollback, lineage, and evidence workflows
```

Runtime execution reads the active bundle for an environment. It does not promote, approve, deploy, or roll back bundles.

## 5. Data Flow

Primary local state:

- `registry/bundles.json` stores bundle metadata and lifecycle state.
- `registry/deployments.json` stores active bundle pointers by environment.
- `registry/deployment_history.json` stores deployment changes.
- `registry/promotion_log.json` stores promotion decisions.
- `runs/run_<timestamp>_<bundle_id>/` stores configs, inputs, predictions, timings, metrics, scorecards, and decision artifacts.
- `db/workbench.duckdb` stores run and inference telemetry; it is ignored by git.
- `configs/*.yaml` and `configs/*.json` define scoring, promotion rules, and environments.
- `data/eval_sets/`, `data/policies/`, `data/prompts/`, `data/retrieval/`, `data/semantic/`, and `data/signals/` hold local inputs used by examples and runtime resolution.

## 6. Configuration

Configuration is file-based and local-first:

- `configs/environments.json` defines environments and runtime settings.
- `configs/promotion_rules.yaml` defines default promotion gates.
- `configs/scoring_profile.yaml` defines scoring metrics.
- `configs/examples/promotion_rules_strict.yaml` provides a stricter promotion example.
- `.env` and `*.env` files are ignored and must not be committed.

Optional runtime integrations are configured through environment variables or local service defaults:

- `OLLAMA_HOST` can point the Ollama adapter at a non-default Ollama host.
- ChromaDB and embedding packages are optional lazy imports.
- LM Studio is registered opportunistically when its local runtime is available.

Secret values should stay outside tracked files.

## 7. Testing and SIT

The project uses pytest and ruff. The practical SIT command for this housekeeping pass was:

```bash
uv run pytest -q
```

Result on 2026-05-18: 182 tests passed.

Important test coverage includes lifecycle transitions, deployment flow, runtime resolution, model adapter contracts, policy enforcement, evidence packs, UI AppTest coverage, and the control-plane/runtime-plane boundary.

## 8. Deployment / Execution

Local setup:

```bash
uv sync --extra dev
source .venv/bin/activate
workbench init
```

Common execution flow:

```bash
workbench create-bundle --name claims_bundle --version 1.0.0 --from-file examples/claims_v1.json
workbench run-experiment --bundle claims_bundle_v1 --eval-set claims_smoke
workbench eval <run_id>
workbench propose-promotion <run_id>
workbench deploy-to-dev claims_bundle_v1
workbench invoke --env dev --input '{"question": "..."}'
```

Runtime services:

```bash
workbench serve --env dev --port 8080
workbench ui
```

## 9. Governance / Operational Notes

The control-plane/runtime-plane boundary is explicit:

- control-plane modules emit decisions and mutate registry, deployment, promotion, run, and audit state;
- runtime-plane modules execute active bundles and may write inference telemetry, but must not call lifecycle mutation APIs;
- `tests/test_plane_boundary.py` enforces this contract through AST checks.

Runtime-plane modules may read bundle and deployment state through approved read paths and may write inference telemetry through `db.insert_inference`. They must not create bundles, transition bundle state, approve or reject promotions, deploy or undeploy bundles, run experiments, evaluate runs, or trigger rollback.

Operational auditability comes from append-oriented registry files, run artifacts, deployment history, promotion decisions, lineage views, evidence packs, and persisted runtime telemetry.

## 10. Known Gaps

See `design/issues-pending-review.md`.
