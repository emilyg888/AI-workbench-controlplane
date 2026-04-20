# ai-workbench-controlplane

Local-first control plane for managing AI **bundle** lifecycle.

> Model alone is not the deployable unit. **Bundle** is the deployable unit.
> `bundle = model + prompt + retrieval + policy + evaluation profile`

All 8 phases implemented (see `docs/SPEC_phase*.md`). Runs on a laptop with zero cloud services.

## Setup

```bash
uv sync --extra dev
source .venv/bin/activate
workbench init
```

## End-to-end flow

```bash
# 1. Create a bundle
workbench create-bundle --name claims_bundle --version 1.0.0 \
    --from-file examples/claims_v1.json

# 2. Run it against an eval set (Phase 2)
workbench run-experiment --bundle claims_bundle_v1 --eval-set claims_smoke

# 3. Score the run (Phase 3)
workbench eval <run_id>

# 4. Propose promotion (Phase 4)
workbench propose-promotion <run_id>

# 5. Deploy (Phase 5)
workbench deploy-to-dev claims_bundle_v1
workbench deploy-to-prod claims_bundle_v1   # after dwell time

# 6. Serve (Phase 6)
workbench invoke --env dev --input '{"question": "..."}'
workbench serve --env dev --port 8080

# 7. Compare / roll back / evidence (Phase 7)
workbench compare-bundles --env dev --window 24
workbench rollback --env prod
workbench evidence-pack <decision_id> --output pack.zip
workbench lineage claims_bundle_v1 [--dot]
workbench doctor

# 8. UI (Phase 8)
workbench ui
```

## CLI

### Registry & lifecycle (Phase 1)

| Command | Purpose |
|---|---|
| `workbench init` | Seed registry + configs (idempotent; `--force` overwrites). |
| `workbench create-bundle --name X --version Y --from-file F` | Register a bundle in `draft`. |
| `workbench list-bundles [--state S] [--name N]` | Tabular list. |
| `workbench show-bundle <bundle_id>` | Pretty-print a bundle record. |
| `workbench show-active [--env dev\|prod]` | Show active bundle per env. |
| `workbench set-state <bundle_id> <new_state>` | Gated state transition. |

### Experiment execution (Phase 2)

| Command | Purpose |
|---|---|
| `workbench run-experiment --bundle B --eval-set E [--limit N]` | Execute bundle; writes run artifact + DuckDB row. |
| `workbench list-runs [--bundle ID] [--limit N]` | Tabular run history. |
| `workbench show-run <run_id>` | Pretty-print config + timings. |

### Evaluation (Phase 3)

| Command | Purpose |
|---|---|
| `workbench eval <run_id> [--profile N] [--baseline R]` | Score a run; writes metrics.json + scorecard.md. |
| `workbench show-scorecard <run_id>` | Render scorecard to terminal. |
| `workbench compare-runs <run> --baseline <run>` | Delta table; regression flag. |

### Promotion (Phase 4)

| Command | Purpose |
|---|---|
| `workbench propose-promotion <run_id> [--rules N]` | Run thresholds + regression; transition + log decision. |
| `workbench approve <bundle_id> [--notes "…"]` | Manual approve candidate. |
| `workbench reject <bundle_id> --reason "…"` | Force reject. |
| `workbench show-promotion-log [--bundle ID]` | Tabular history. |

### Deployment (Phase 5)

| Command | Purpose |
|---|---|
| `workbench deploy-to-dev <bundle_id> [--notes "…"]` | Activate bundle in `dev`. |
| `workbench deploy-to-prod <bundle_id> [--notes "…"]` | Activate in `prod` (preconditions enforced). |
| `workbench undeploy --env E [--reason "…"]` | Set env's active to null. |
| `workbench show-deployment-history [--env E] [--bundle B]` | Tabular history. |

### Runtime (Phase 6)

| Command | Purpose |
|---|---|
| `workbench invoke --env E --input JSON` | Single synchronous request. |
| `workbench serve --env E [--port N] [--host H]` | Run FastAPI server. |
| `workbench active-runtime [--env E]` | Print resolved adapter names + bundle. |

### Governance (Phase 7)

| Command | Purpose |
|---|---|
| `workbench rollback --env E [--to BUNDLE] [--reason "…"]` | Revert to previous/explicit bundle. |
| `workbench lineage <bundle_id> [--dot]` | ASCII tree / Graphviz DOT. |
| `workbench evidence-pack <decision_id> --output FILE.zip` | Hash-verified audit zip. |
| `workbench compare-bundles --env E [--window H] [--champion B] [--challenger B]` | Runtime stats per bundle. |
| `workbench doctor [--fix] [--yes]` | Registry integrity check. |

### UI (Phase 8)

| Command | Purpose |
|---|---|
| `workbench ui [--port N] [--host H]` | Launch Streamlit dashboard (localhost-only). |

### Exit codes

`0` ok · `1` generic · `2` validation / illegal transition · `3` not found · `4` duplicate.

## Lifecycle state machine

```
draft → evaluated → candidate → approved → deployed
                        │          ↑ │
                        └───► rejected (terminal)
  │         │           │           │         │
  └─────────┴───────────┴───────────┴─────────┴───► archived (terminal)
```

See [docs/SPEC_phase1.md](docs/SPEC_phase1.md) §5 for the full transition matrix.

## Bundle schema

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

- `bundle_id` format: `^[a-z0-9_]+_v[0-9]+$` (auto-generated as `{name}_v{major}`).
- `state` ∈ `draft`, `evaluated`, `candidate`, `approved`, `deployed`, `archived`, `rejected`.

## Adapter model

- **Model**: `stub` (deterministic echo), `ollama` (HTTP → local Ollama). Register your own via `adapters.registry.register_model_adapter`.
- **Retrieval**: `stub` (empty), `file` (substring over JSONL corpus), `chroma` (ChromaDB, lazy-imported).
- **Policy**: YAML rule packs — `regex_block` (block/redact) + `keyword_block`. Applied pre- and post-model.

## Testing

```bash
pytest -q                                # 154 tests
pytest --cov=src/workbench --cov-report=term-missing
ruff check .
```

## Layout

```
configs/        environments.json · promotion_rules.yaml · scoring_profile.yaml
registry/       bundles.json · deployments.json · deployment_history.json · promotion_log.json
runs/           run_<ts>_<bundle_id>/ { config,inputs,predictions,timings,run.log,metrics,scorecard,promotion_decision,promotion_report }
db/             workbench.duckdb (runs + inference_requests tables)
data/           eval_sets · retrieval · policies · prompts · semantic · signals
examples/       claims_v1.json
src/workbench/
  models · state_machine · storage · bundle_manager
  deployment_state_manager · environments · rollback · lineage · doctor
  experiment_runner · evaluation_engine · promotion_engine · promotion_rules
  runtime_resolver · runtime_compare · comparison · evidence_pack
  scoring_profile · cli
  adapters/   (base · model_stub · model_ollama · retrieval_stub · retrieval_file · retrieval_chroma · registry)
  scorers/    (base · exact_match · substring · passage_overlap · policy_check · refusal · latency · non_empty)
  policy/     (enforcer)
  serving/    (invoke · http)
  ui/         (app · data · pages/{home,bundles,runs,deployments,promotions,compare})
tests/          full pytest suite
docs/           design.md · SPEC_phase1..8.md
```

## Optional heavy adapters

- **Ollama**: `brew install ollama && ollama pull llama3.1:8b`. Set `OLLAMA_HOST` if non-default.
- **ChromaDB + embeddings**: `uv add chromadb sentence-transformers` (~90 MB). Adapter lazy-imports; nothing else breaks without it.
