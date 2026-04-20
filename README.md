# ai-workbench-controlplane

Local-first control plane for managing AI **bundle** lifecycle.

> Model alone is not the deployable unit. **Bundle** is the deployable unit.
> `bundle = model + prompt + retrieval + policy + evaluation profile`

## Phase 1 status — Core control plane skeleton

Delivers the registry abstraction, lifecycle state machine, and a CLI to
create / list / show / transition bundles. No execution, evaluation, or
promotion logic yet — those land in Phases 2–8.

## Setup

```bash
uv sync --extra dev
source .venv/bin/activate
workbench init
```

## CLI

| Command | What it does |
| --- | --- |
| `workbench init` | Seed registry + configs (idempotent; `--force` overwrites). |
| `workbench create-bundle --name X --version Y --from-file bundle.json` | Register a bundle in `draft`. |
| `workbench list-bundles [--state S] [--name N]` | List bundles (table). |
| `workbench show-bundle <bundle_id>` | Pretty-print a bundle record. |
| `workbench show-active [--env dev\|prod]` | Show active bundle per env. |
| `workbench set-state <bundle_id> <new_state>` | Gated state transition. |

### Exit codes

`0` ok · `1` generic · `2` validation / illegal transition · `3` not found · `4` duplicate.

## Bundle schema (summary)

```json
{
  "bundle_id": "claims_bundle_v1",
  "name": "claims_bundle",
  "version": "1.0.0",
  "state": "draft",
  "components": {
    "model":      { "name": "...", "provider": "...", "params": {} },
    "prompt":     { "template_ref": "...", "version": "v1" },
    "retrieval":  { "profile_ref": "...",  "version": "v1" },
    "policy":     { "pack_ref": "...",     "version": "v1" },
    "evaluation": { "profile_ref": "...",  "version": "v1" },
    "semantic_layer": { "ref": "..." },
    "signal_layer":   { "ref": "..." }
  },
  "lineage": { "parent_bundle_id": null, "notes": "..." }
}
```

- `bundle_id` format: `^[a-z0-9_]+_v[0-9]+$` (auto-generated as `{name}_v{major}` if omitted).
- `state` ∈ `draft`, `evaluated`, `candidate`, `approved`, `deployed`, `archived`.
- Phase 1: `*_ref` fields must be strings but their targets need not exist.

## Lifecycle state machine

```
draft → evaluated → candidate → approved → deployed
  │         │           │           │         │
  └─────────┴───────────┴───────────┴─────────┴───► archived (terminal)
```

See [docs/SPEC_phase1.md](docs/SPEC_phase1.md) §5 for the full transition matrix.

## Layout

```
configs/        environments.json · promotion_rules.yaml · scoring_profile.yaml
registry/       bundles.json · deployments.json · promotion_log.json
runs/           populated from Phase 2
db/             workbench.duckdb created from Phase 2
data/           eval_sets · retrieval · policies · prompts · semantic · signals
examples/       claims_v1.json
src/workbench/  models · state_machine · storage · bundle_manager
                deployment_state_manager · cli · (phase 2-6 stubs)
tests/          pytest suite
docs/           design.md · SPEC_phase1.md
```

## Testing

```bash
pytest -q
pytest --cov=src/workbench --cov-report=term-missing
ruff check .
```

## End-to-end smoke

```bash
workbench init
workbench create-bundle --name claims_bundle --version 1.0.0 \
    --from-file examples/claims_v1.json
workbench list-bundles
workbench show-active --env dev
workbench set-state claims_bundle_v1 archived
```
