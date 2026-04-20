# SPEC — Phase 1: Core Control Plane Skeleton

**Project:** AI Workbench Control Plane
**Phase:** 1 of 8
**Target environment:** Local-first on MacBook Pro (Apple Silicon or Intel), macOS 13+
**Status:** Draft specification
**Last updated:** 2026-04-20

---

## 1. Purpose & Goal

Establish the foundational lifecycle structure of the AI Workbench: define what a **bundle** is, persist it, and expose a CLI to create, list, show, and transition bundles between lifecycle states.

Phase 1 delivers **no execution, no evaluation, no promotion logic** — only the registry abstraction, state machine, and CLI scaffolding. It is the stable contract that Phases 2–8 build on.

### Guiding principle

> Model alone is not the deployable unit. **Bundle** is the deployable unit.
> Bundle = model + prompt + retrieval + policy + evaluation profile.

Phase 1 exists to make that abstraction real, persistent, and inspectable.

---

## 2. Scope

### 2.1 In scope for Phase 1

- Repository scaffold with the full directory tree (including empty folders for later phases)
- Bundle JSON schema + `pydantic` validator
- Bundle registry file (`registry/bundles.json`) with atomic read/write
- Deployment state file (`registry/deployments.json`) — `dev` and `prod` environments initialised to `null`
- Environment config file (`configs/environments.json`)
- Lifecycle state machine: `draft → evaluated → candidate → approved → deployed` + `archived`
- CLI with 6 working commands (`init`, `create-bundle`, `list-bundles`, `show-bundle`, `show-active`, `set-state`)
- Unit tests for the registry, state transitions, and deployment state
- Python `venv`-based environment setup (no Docker)
- `README.md` with setup and usage
- Stubs for Phases 2–6 modules so imports are stable from day one

### 2.2 Out of scope for Phase 1

Deferred to later phases:

| Deferred item                               | Phase   |
| ------------------------------------------- | ------- |
| Experiment runner / actual bundle execution | Phase 2 |
| Evaluation engine, metrics, scorecards      | Phase 3 |
| Promotion rules & automated approval        | Phase 4 |
| `deploy-to-dev` / `deploy-to-prod` commands | Phase 5 |
| Model / retrieval / policy adapters         | Phase 6 |
| Champion vs challenger comparison, rollback | Phase 7 |
| UI / dashboard                              | Phase 8 |

---

## 3. Local-First Stack (MacBook Pro)

All choices are Apple Silicon-friendly and require no cloud credentials, no Docker, and no external services.

| Concern                | Choice                                        | Reason                                     |
| ---------------------- | --------------------------------------------- | ------------------------------------------ |
| Language               | Python 3.11+ (via Homebrew or `pyenv`)        | Stable, native on Apple Silicon            |
| Env isolation          | `venv` (stdlib)                               | Simple; no Conda / Docker overhead         |
| Dependency mgmt        | `pip` + `requirements.txt` + `pyproject.toml` | Standard; easy to swap for `uv` later      |
| CLI framework          | `typer`                                       | Type-hint-driven, clean UX, autocompletion |
| Schema validation      | `pydantic` v2                                 | Bundle schema + JSON (de)serialisation     |
| Config files           | YAML (`pyyaml`) + JSON (stdlib)               | Per design §3.7                            |
| Embedded DB (Phase 2+) | `duckdb`                                      | Zero-config, Apple Silicon native          |
| Testing                | `pytest`                                      | Standard                                   |
| Lint + format          | `ruff`                                        | Fast, single tool                          |

### 3.1 One-time macOS prerequisites

```bash
brew install python@3.11
# optional but recommended:
brew install pyenv
```

### 3.2 Project bootstrap

```bash
cd ~/projects
git init ai-workbench && cd ai-workbench
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
workbench init
```

---

## 4. Bundle Schema (the Core Abstraction)

### 4.1 Canonical JSON form

```json
{
  "bundle_id": "claims_bundle_v1",
  "name": "claims_bundle",
  "version": "1.0.0",
  "state": "draft",
  "created_at": "2026-04-20T10:00:00Z",
  "updated_at": "2026-04-20T10:00:00Z",
  "created_by": "local-user",
  "components": {
    "model": {
      "name": "llama3.1-8b",
      "provider": "local-ollama",
      "params": { "temperature": 0.2, "max_tokens": 1024 }
    },
    "prompt": {
      "template_ref": "data/prompts/claims_v1.txt",
      "version": "v1"
    },
    "retrieval": {
      "profile_ref": "data/retrieval/claims_profile.yaml",
      "version": "v1"
    },
    "policy": {
      "pack_ref": "data/policies/claims_pack.yaml",
      "version": "v1"
    },
    "evaluation": {
      "profile_ref": "configs/scoring_profile.yaml",
      "version": "v1"
    },
    "semantic_layer": { "ref": "data/semantic/claims.yaml" },
    "signal_layer": { "ref": "data/signals/claims.yaml" }
  },
  "lineage": {
    "parent_bundle_id": null,
    "notes": "initial draft"
  }
}
```

### 4.2 Field rules

| Field                                        | Type           | Rule                                                                           |
| -------------------------------------------- | -------------- | ------------------------------------------------------------------------------ |
| `bundle_id`                                  | string         | Globally unique, format `^[a-z0-9_]+_v[0-9]+$`. Generated if not supplied.     |
| `name`                                       | string         | Required, lowercase, `[a-z0-9_]+`                                              |
| `version`                                    | string         | Required, semver `X.Y.Z`                                                       |
| `state`                                      | enum           | One of `draft`, `evaluated`, `candidate`, `approved`, `deployed`, `archived`   |
| `created_at` / `updated_at`                  | ISO8601 UTC    | Set by the system, never by the user                                           |
| `components.model`                           | object         | Required; `name` and `provider` mandatory                                      |
| `components.prompt`                          | object         | Required; `template_ref` must be a string (existence NOT validated in Phase 1) |
| `components.retrieval`                       | object         | Required; `profile_ref` mandatory                                              |
| `components.policy`                          | object         | Required; `pack_ref` mandatory                                                 |
| `components.evaluation`                      | object         | Required; `profile_ref` mandatory                                              |
| `components.semantic_layer` / `signal_layer` | object         | Optional; default `{"ref": null}`                                              |
| `lineage.parent_bundle_id`                   | string or null | Must reference an existing bundle if non-null                                  |

### 4.3 Phase 1 relaxation

In Phase 1, `*_ref` fields must be valid **strings** but their referenced files do NOT need to exist on disk. Phase 2 will enforce existence when the experiment runner actually loads them. This keeps Phase 1 tight and decoupled.

---

## 5. Lifecycle State Machine

### 5.1 State diagram

```
   ┌──────────┐
   │  draft   │
   └────┬─────┘
        │  (Phase 3: evaluation complete)
        ▼
   ┌──────────┐
   │evaluated │
   └────┬─────┘
        │  (Phase 4: passes promotion thresholds)
        ▼
   ┌──────────┐
   │candidate │
   └────┬─────┘
        │  (Phase 4: approved by rules + optional human)
        ▼
   ┌──────────┐
   │ approved │
   └────┬─────┘
        │  (Phase 5: deployed to an environment)
        ▼
   ┌──────────┐
   │ deployed │
   └──────────┘

   Any state ───► archived   (terminal)
```

### 5.2 Transition matrix

| From ↓ / To → | draft | evaluated | candidate | approved | deployed | archived |
| ------------- | ----- | --------- | --------- | -------- | -------- | -------- |
| **draft**     | —     | ✅        | ❌        | ❌       | ❌       | ✅       |
| **evaluated** | ❌    | —         | ✅        | ❌       | ❌       | ✅       |
| **candidate** | ❌    | ✅        | —         | ✅       | ❌       | ✅       |
| **approved**  | ❌    | ❌        | ❌        | —        | ✅       | ✅       |
| **deployed**  | ❌    | ❌        | ❌        | ✅       | —        | ✅       |
| **archived**  | ❌    | ❌        | ❌        | ❌       | ❌       | —        |

### 5.3 Phase 1 behaviour

Phase 1 writes the full state machine code but only **exposes** `draft → archived` via the CLI. All other transitions are reachable programmatically (and fully tested) so Phase 3/4/5 can wire them in without touching `state_machine.py`.

### 5.4 Principle enforcement

- **Principle 2 — Evaluation before deployment:** No transition skips `evaluated`. `draft → approved` is rejected at the state-machine layer.
- **Principle 4 — Evidence is persistent:** Every transition writes a new `updated_at` and (in Phase 4) a promotion-log entry.

---

## 6. Directory & File Layout

```
ai-workbench/
├── README.md
├── pyproject.toml
├── requirements.txt
├── .gitignore
├── .ruff.toml
│
├── configs/
│   ├── environments.json         # {"dev": {...}, "prod": {...}}
│   ├── promotion_rules.yaml      # placeholder for Phase 4
│   └── scoring_profile.yaml      # placeholder for Phase 3
│
├── registry/
│   ├── bundles.json              # []            — initial
│   ├── deployments.json          # {"dev": null, "prod": null}
│   └── promotion_log.json        # []            — initial
│
├── runs/                         # empty; populated by Phase 2
├── db/                           # empty; workbench.duckdb added in Phase 2
│
├── data/
│   ├── eval_sets/.gitkeep
│   ├── retrieval/.gitkeep
│   ├── policies/.gitkeep
│   ├── prompts/.gitkeep
│   ├── semantic/.gitkeep
│   └── signals/.gitkeep
│
├── examples/
│   └── claims_v1.json            # sample bundle for quick-start
│
├── src/workbench/
│   ├── __init__.py
│   ├── models.py                 # pydantic schemas (Bundle, Deployment, Env)
│   ├── state_machine.py          # transition validation
│   ├── storage.py                # atomic JSON read/write helpers
│   ├── bundle_manager.py         # CRUD on bundles.json
│   ├── deployment_state_manager.py  # read/write deployments.json
│   ├── cli.py                    # typer app
│   ├── experiment_runner.py      # stub — NotImplementedError
│   ├── evaluation_engine.py      # stub — NotImplementedError
│   ├── promotion_engine.py       # stub — NotImplementedError
│   ├── runtime_resolver.py       # stub — NotImplementedError
│   └── adapters/
│       └── __init__.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # tmp_path fixture for registry isolation
│   ├── test_models.py
│   ├── test_state_machine.py
│   ├── test_bundle_manager.py
│   ├── test_deployment_state.py
│   └── test_cli.py
│
└── docs/
    ├── phase-1.md                # this spec (trimmed)
    └── SPEC_phase1.md            # this file
```

---

## 7. Storage Contracts

### 7.1 `registry/bundles.json`

A JSON array of Bundle records (schema §4). Read fully into memory, mutated, then atomically written back.

### 7.2 `registry/deployments.json` — Phase 1 initial

```json
{
  "dev": { "active_bundle_id": null, "updated_at": null },
  "prod": { "active_bundle_id": null, "updated_at": null }
}
```

### 7.3 `registry/promotion_log.json`

Empty array in Phase 1. Schema defined but not written to until Phase 4.

### 7.4 `configs/environments.json`

```json
{
  "dev": { "description": "Local development environment" },
  "prod": { "description": "Local production-equivalent environment" }
}
```

### 7.5 Atomic write pattern

All JSON writes use:

1. Write to `<path>.tmp`
2. `os.fsync` the temp file
3. `os.replace(<path>.tmp, <path>)`

This guarantees no partial write can corrupt a registry file, even if the process is killed. The same pattern maps cleanly to S3 `PutObject` when cloud mode is enabled later (design §1 line 14: _"AWS by config change ONLY"_).

### 7.6 Concurrency

Phase 1 assumes single-user, single-process on a laptop. No file locking. Phase 7 adds optional `fcntl`-based advisory locking.

---

## 8. CLI Surface

Installed as a console script `workbench` via `pyproject.toml`.

| Command                                                                | Purpose                                                    | Phase 1 behaviour                                                                   |
| ---------------------------------------------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `workbench init`                                                       | Create folder tree + seed `registry/` and `configs/` files | Idempotent; refuses to overwrite non-empty registry files unless `--force`          |
| `workbench create-bundle --name X --version Y --from-file bundle.json` | Register a new bundle in `draft` state                     | Validates schema, generates `bundle_id`, sets timestamps, appends to `bundles.json` |
| `workbench list-bundles [--state STATE] [--name NAME]`                 | List bundles, optionally filtered                          | Tabular output                                                                      |
| `workbench show-bundle <bundle_id>`                                    | Print a bundle's full JSON record                          | Pretty-printed                                                                      |
| `workbench show-active [--env dev\|prod]`                              | Show active bundle per env                                 | Prints `null` for both in Phase 1                                                   |
| `workbench set-state <bundle_id> <new_state>`                          | Manual state transition                                    | Gated by state-machine; primary use in Phase 1 is `draft → archived`                |

### 8.1 Exit codes

| Code | Meaning                                       |
| ---- | --------------------------------------------- |
| 0    | Success                                       |
| 1    | Generic error                                 |
| 2    | Validation failure (schema, state transition) |
| 3    | Not found (bundle_id, environment)            |
| 4    | Conflict (duplicate bundle_id)                |

### 8.2 Example session

```bash
$ workbench init
✓ Initialised ai-workbench/ scaffold

$ workbench create-bundle --name claims_bundle --version 1.0.0 \
    --from-file examples/claims_v1.json
✓ Created bundle claims_bundle_v1 (state=draft)

$ workbench list-bundles
BUNDLE_ID           NAME            VERSION   STATE    UPDATED_AT
claims_bundle_v1    claims_bundle   1.0.0     draft    2026-04-20T10:00:00Z

$ workbench show-active --env dev
{ "env": "dev", "active_bundle_id": null, "updated_at": null }

$ workbench set-state claims_bundle_v1 archived
✓ Transitioned claims_bundle_v1: draft → archived
```

---

## 9. Module Responsibilities

### 9.1 `models.py`

Pure pydantic models: `Bundle`, `BundleComponents`, `ModelSpec`, `PromptSpec`, `RetrievalSpec`, `PolicySpec`, `EvaluationSpec`, `LayerRef`, `Lineage`, `Deployment`, `DeploymentState`, `Environment`, `BundleState` (Enum).

### 9.2 `state_machine.py`

Single source of truth for allowed transitions. Exposes `is_valid_transition(frm, to) -> bool` and `assert_transition(frm, to) -> None`.

### 9.3 `storage.py`

- `read_json(path) -> dict|list`
- `write_json_atomic(path, data) -> None`
- `ensure_registry_files(root) -> None`

### 9.4 `bundle_manager.py`

- `create_bundle(spec: dict) -> Bundle`
- `get_bundle(bundle_id: str) -> Bundle`
- `list_bundles(state: str|None = None, name: str|None = None) -> list[Bundle]`
- `transition_bundle(bundle_id: str, new_state: BundleState) -> Bundle`

### 9.5 `deployment_state_manager.py`

- `get_active(env: str) -> Deployment`
- `set_active(env: str, bundle_id: str) -> Deployment` _(used from Phase 5; fully implemented and tested in Phase 1 anyway)_
- `list_environments() -> list[str]`

### 9.6 `cli.py`

`typer` app wiring the six commands above. Formats output as tables (via `rich`) or pretty JSON.

### 9.7 Stubs (Phase 2–6)

`experiment_runner.py`, `evaluation_engine.py`, `promotion_engine.py`, `runtime_resolver.py`, and `adapters/` all exist as importable modules raising `NotImplementedError("Implemented in Phase N")`. This means the module graph is stable from day one — Phases 2–6 extend rather than restructure.

---

## 10. Testing Plan

### 10.1 Framework

`pytest` with `tmp_path` fixture to isolate each test from the real registry.

### 10.2 Required test coverage (≥ 80% on core modules)

| Test file                  | Asserts                                                                                   |
| -------------------------- | ----------------------------------------------------------------------------------------- |
| `test_models.py`           | Schema validation: required fields, enum values, semver format, id regex                  |
| `test_state_machine.py`    | All 36 transition-matrix cells (one test per cell)                                        |
| `test_bundle_manager.py`   | Create, duplicate detection, list with filters, get not-found, transition valid & invalid |
| `test_deployment_state.py` | Initial state, `get_active` for dev & prod, `set_active` updates `updated_at`             |
| `test_cli.py`              | `typer.testing.CliRunner` invokes each command; exit codes correct; init idempotency      |

### 10.3 Run

```bash
pytest -q
pytest --cov=src/workbench --cov-report=term-missing
```

---

## 11. Definition of Done

Phase 1 is complete when **all** of the following hold:

1. ✅ `workbench init` produces a valid scaffold from an empty directory.
2. ✅ `create-bundle` writes a schema-valid record to `registry/bundles.json`.
3. ✅ `list-bundles` and `show-bundle` read records back correctly.
4. ✅ Invalid state transitions (e.g. `draft → approved`) are rejected with exit code 2 and a clear error message.
5. ✅ `pytest` passes; coverage ≥ 80% on `bundle_manager.py`, `state_machine.py`, `deployment_state_manager.py`.
6. ✅ `README.md` documents: setup, the 6 commands, and the bundle schema.
7. ✅ Stubs for Phases 2–6 exist, import cleanly, and raise `NotImplementedError`.
8. ✅ `ruff check .` passes with zero errors.
9. ✅ End-to-end smoke: the "Example session" in §8.2 runs top-to-bottom on a fresh macOS checkout with no errors.

---

## 12. Design Principles — Traceability

| Principle (design §8)                 | Phase 1 implementation                                                                                                                 |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Promote bundles, not models**    | `Bundle` is the registry unit; `model` is a sub-component of `components`. The CLI and schema never treat model in isolation.          |
| **2. Evaluation before deployment**   | State machine forbids `draft → approved`, `draft → deployed`. Enforced in `state_machine.py` with tests covering every forbidden cell. |
| **3. Environment state is explicit**  | `deployments.json` always names a concrete `bundle_id` (or `null`). There is no "latest" concept anywhere in the code.                 |
| **4. Evidence is persistent**         | Every mutation updates `updated_at`; all registry files live on disk in JSON, readable by any tool.                                    |
| **5. Runtime resolves from registry** | `runtime_resolver.py` stub already takes only `env` as input — never ad-hoc bundle args. The contract is locked in Phase 1.            |

---

## 13. Phase 1 → Phase 2 Handoff

When Phase 1 is done, Phase 2 can start immediately because:

- **`Bundle.get(bundle_id)`** returns a fully-validated object the experiment runner can load.
- **`runs/`** directory exists and is empty — Phase 2 just starts writing `run_xxxx/` subfolders.
- **`db/`** exists — Phase 2 creates `workbench.duckdb` and opens it.
- **Bundle state machine** already supports `draft → evaluated`; Phase 3 will trigger it after scoring.
- **Atomic write helpers** in `storage.py` are reused for `run_artifacts` writes.

No Phase 1 module needs refactoring for Phase 2.

---

## 14. Risks & Mitigations

| Risk                                               | Likelihood    | Mitigation                                                                                         |
| -------------------------------------------------- | ------------- | -------------------------------------------------------------------------------------------------- |
| Users hand-edit `bundles.json` and corrupt it      | Medium        | Pydantic re-validates on every read; `workbench doctor` command added in Phase 7                   |
| `bundles.json` grows large (>10k bundles)          | Low (Phase 1) | Phase 7 migrates hot reads to DuckDB; JSON remains the source of truth                             |
| Schema evolves across phases, breaks older bundles | Medium        | Include `schema_version` field in `Bundle` (default `"1"`); migration helper lives in `storage.py` |
| Apple Silicon vs Intel discrepancies               | Very low      | Pure-Python deps; `duckdb` and `pydantic` ship universal wheels                                    |
| User runs commands from wrong directory            | High          | CLI walks up from `cwd` to find `registry/bundles.json`; errors with clear message if not found    |

---

## 15. Deliverables Checklist

- [ ] `pyproject.toml` with `workbench` console-script entry point
- [ ] `requirements.txt` (typer, pydantic, pyyaml, duckdb, pytest, ruff, rich)
- [ ] `.gitignore` (`.venv`, `__pycache__`, `db/*.duckdb`, `runs/run_*`, `.pytest_cache`)
- [ ] `src/workbench/` — 11 modules per §9
- [ ] `tests/` — 5 test files per §10
- [ ] `registry/` seeded files
- [ ] `configs/` seeded files
- [ ] `examples/claims_v1.json`
- [ ] `README.md`
- [ ] `docs/SPEC_phase1.md` (this file)

---

## 16. Estimated Effort

| Task                                               | Rough effort                    |
| -------------------------------------------------- | ------------------------------- |
| Project scaffold + `pyproject.toml` + `venv` setup | 0.5 h                           |
| Pydantic models                                    | 1 h                             |
| State machine + tests                              | 1 h                             |
| Storage helpers (atomic write)                     | 0.5 h                           |
| Bundle manager + tests                             | 1.5 h                           |
| Deployment state manager + tests                   | 1 h                             |
| CLI (6 commands) + tests                           | 2 h                             |
| Example bundle + README                            | 1 h                             |
| Lint pass, coverage check, smoke test              | 0.5 h                           |
| **Total**                                          | **~9 hours** (1–2 focused days) |

---

_End of SPEC — Phase 1._
