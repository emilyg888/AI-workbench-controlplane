# SPEC — Phase 6: Runtime Integration

**Project:** AI Workbench Control Plane
**Phase:** 6 of 8
**Target environment:** Local-first on MacBook Pro, macOS 13+
**Depends on:** Phase 5 complete (environments always name a concrete `bundle_id`)
**Status:** Draft specification
**Last updated:** 2026-04-20

---

## 1. Purpose & Goal

Connect the workbench to **real execution**. Until now, execution only happened inside `run-experiment` against eval sets. Phase 6 wires up a production-shaped runtime: the workbench resolves the currently-active bundle for an environment and serves requests against it, with proper model invocation, retrieval, and policy enforcement.

### Guiding principle

> The runtime executes the approved active bundle, not ad-hoc configs.
> (Design §8, Principle 5.)

---

## 2. Scope

### 2.1 In scope

- `runtime_resolver.py` fully implemented (Phase 1 had a stub; this phase makes it real)
- Production-grade adapters (upgrades to Phase 2 stubs):
  - **Model adapter**: local Ollama integration with retry + timeout
  - **Retrieval adapter**: vector-based using `chromadb` (embedded, local file-backed)
  - **Policy enforcement point**: real rule engine reading the bundle's policy pack
- A minimal **local serving layer**: either a CLI command (`workbench serve`) that runs a FastAPI server, or a synchronous `invoke` CLI command — both read the active bundle from `deployments.json`
- Environment-aware resolution: same code serves `dev` and `prod` by reading `--env` or `WORKBENCH_ENV`
- Request/response logging: every served request writes a row to DuckDB `inference_requests` table
- Tests for resolver, adapters, and end-to-end invocation

### 2.2 Out of scope

| Deferred | Phase |
|---|---|
| Champion vs challenger routing | Phase 7 |
| Rollback | Phase 7 |
| Multi-user auth / API keys | beyond scope |
| Horizontal scaling | N/A (local-first) |

---

## 3. Runtime Architecture

```
                 ┌──────────────────────┐
 User request -> │   workbench invoke   │
                 │        or            │
                 │   POST /v1/invoke    │
                 └──────────┬───────────┘
                            │
                            ▼
              ┌──────────────────────────┐
              │    runtime_resolver       │
              │  (reads deployments.json) │
              └──────────┬────────────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
       ┌────────────┐ ┌──────────┐ ┌──────────────┐
       │ Retrieval  │ │  Model   │ │    Policy    │
       │  Adapter   │ │ Adapter  │ │ Enforcement  │
       │ (chromadb) │ │ (ollama) │ │     Point    │
       └────────────┘ └──────────┘ └──────────────┘
              │
              ▼
       ┌────────────────────┐
       │ Response Generator │
       └─────────┬──────────┘
                 │
                 ▼
         ┌───────────────┐
         │ DuckDB: log   │
         └───────────────┘
```

### 3.1 Request lifecycle

1. `runtime_resolver.resolve(env)` reads `deployments.json`, loads the active bundle.
2. Retrieval adapter fetches context using `bundle.components.retrieval`.
3. Prompt is rendered from `bundle.components.prompt.template_ref` with input + context.
4. Policy enforcement point checks the prompt pre-model (input filters) and the output post-model (output filters).
5. Model adapter generates.
6. Response generator assembles the final response object.
7. Request + response + timing + bundle_id is logged to DuckDB.

Any policy violation at input stage → short-circuit refusal; at output stage → substitution with a safe message. Both are logged.

---

## 4. Adapter Upgrades

### 4.1 Model adapter: Ollama

`adapters/model_ollama.py` (upgraded from Phase 2 stub):
- Calls `http://localhost:11434/api/generate` via `httpx`
- Retries on transient errors (3 attempts, exponential backoff)
- Hard timeout from `bundle.components.model.params.timeout_seconds` (default 30)
- Streams if requested; assembles full text before returning
- Returns `ModelResult` per Phase 2 protocol

### 4.2 Retrieval adapter: ChromaDB

`adapters/retrieval_chroma.py` (new, replaces Phase 2 `retrieval_file`):
- Embedded ChromaDB client, persistence dir `data/retrieval/<profile>/chroma/`
- Uses `sentence-transformers` (`all-MiniLM-L6-v2`) for embeddings — ~90 MB, runs fine on MBP
- Retrieval profile YAML defines: collection name, top-k, metadata filters
- `workbench retrieval index --profile <name> --input <jsonl>` populates the collection
- Returns list of `Passage` per Phase 2 protocol

### 4.3 Policy enforcement point

`policy/enforcer.py` (new):
- Loads policy pack YAML (`data/policies/<pack>.yaml`)
- Pack schema:
  ```yaml
  version: "1"
  input_rules:
    - id: no_pii_email
      type: regex_block
      pattern: "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b"
      action: redact           # "block" | "redact"
      message: "Email addresses are redacted."
  output_rules:
    - id: no_financial_advice
      type: keyword_block
      keywords: ["buy this stock", "guaranteed return"]
      action: block
      replacement: "I can't give financial advice."
  ```
- Enforcer returns a `PolicyResult` with `allowed` and `transformed_text` fields.

All three adapters run fully offline on the laptop.

---

## 5. Runtime Resolver

`runtime_resolver.py`:

```python
def resolve(env: str) -> ResolvedRuntime:
    deployment = deployment_state_manager.get_active(env)
    if deployment.active_bundle_id is None:
        raise NoActiveBundleError(env)
    bundle = bundle_manager.get_bundle(deployment.active_bundle_id)
    return ResolvedRuntime(
        env=env,
        bundle=bundle,
        model=adapter_registry.get_model_adapter(bundle.components.model.provider),
        retrieval=adapter_registry.get_retrieval_adapter(bundle.components.retrieval.profile_ref),
        policy=PolicyEnforcer(bundle.components.policy.pack_ref),
        prompt_template=load_prompt(bundle.components.prompt.template_ref),
    )

def invoke(env: str, user_input: dict) -> InvokeResult: ...
```

The resolver is **the only** path through which serving code loads bundles. No ad-hoc loading — Principle 5 enforced in code.

---

## 6. Serving Modes

Two modes, same underlying resolver.

### 6.1 CLI: `workbench invoke`

```bash
$ workbench invoke --env dev --input '{"question": "What is my deductible?"}'
```

Synchronous, writes to stdout, single shot. Useful for scripting and tests.

### 6.2 HTTP: `workbench serve`

```bash
$ workbench serve --env dev --port 8080
✓ Resolving active bundle for env=dev
✓ Active: claims_bundle_v2 (activated 2026-04-20T11:05:00Z)
✓ Model adapter: ollama (model=llama3.1-8b)
✓ Retrieval adapter: chroma (profile=claims_v1, collection=claims)
✓ Policy enforcer: claims_pack (6 rules)
✓ Listening on http://127.0.0.1:8080
```

Endpoints:

| Method + Path | Purpose |
|---|---|
| `POST /v1/invoke` | `{ "input": {...} } → { "output": "...", "context": [...], "bundle_id": "...", "trace_id": "..." }` |
| `GET /v1/active` | Returns resolved bundle metadata |
| `GET /healthz` | Liveness |

FastAPI + Uvicorn. Stays single-process, single-worker — this is a laptop.

### 6.3 Hot reload

The resolver caches the `ResolvedRuntime` keyed by `(env, bundle_id, activated_at)`. Every N seconds (default 30), or on a SIGHUP, it re-checks `deployments.json`. If the active bundle has changed, the runtime reloads without restarting the process.

This makes `deploy-to-dev` take effect live during demos.

---

## 7. Request Logging

New DuckDB table:

```sql
CREATE TABLE IF NOT EXISTS inference_requests (
  trace_id      VARCHAR PRIMARY KEY,
  env           VARCHAR NOT NULL,
  bundle_id     VARCHAR NOT NULL,
  at            TIMESTAMP NOT NULL,
  input         JSON,
  output        JSON,
  latency_ms    INTEGER,
  policy_action VARCHAR,   -- 'allow' | 'input_redact' | 'input_block' | 'output_block'
  error         VARCHAR
);
```

Every served request writes one row. Indexed by `bundle_id` and `env` for Phase 7 dashboards.

---

## 8. CLI Additions

| Command | Purpose |
|---|---|
| `workbench invoke --env ENV --input JSON` | Single request against the resolved runtime |
| `workbench serve --env ENV [--port N]` | Run local HTTP server |
| `workbench retrieval index --profile NAME --input FILE.jsonl` | Populate a Chroma collection |
| `workbench active-runtime [--env ENV]` | Print resolved adapter names + bundle |

### 8.1 Example session

```bash
$ workbench retrieval index --profile claims_v1 --input data/retrieval/claims_docs.jsonl
✓ Indexed 1024 documents into collection 'claims'

$ workbench invoke --env dev --input '{"question": "What does my policy cover?"}'
{
  "output": "Your policy covers ...",
  "context": [{"id": "doc_44", "score": 0.82}, ...],
  "bundle_id": "claims_bundle_v2",
  "trace_id": "inv_20260420T120700Z_a1b2c3",
  "latency_ms": 912,
  "policy_action": "allow"
}
```

---

## 9. Module Responsibilities

### 9.1 `runtime_resolver.py` (replaces Phase 1 stub)
Full implementation as in §5. Adds caching with version key.

### 9.2 `adapters/model_ollama.py` (upgrade)
Production-shaped: retries, timeouts, streaming assembly.

### 9.3 `adapters/retrieval_chroma.py` (new)
Chroma-backed retriever with local embeddings.

### 9.4 `policy/enforcer.py` (new)
Input + output rule application.

### 9.5 `serving/http.py` (new)
FastAPI app, hot-reload loop.

### 9.6 `serving/invoke.py` (new)
Synchronous single-shot entry point used by both CLI and HTTP.

### 9.7 `db.py` additions
`inference_requests` table + insert helper.

### 9.8 Updated `experiment_runner.py` (Phase 2)
Now routes through the same adapter registry — stubs can still be selected via bundle provider string, but Ollama + Chroma are available once installed.

---

## 10. Testing Plan

- `test_runtime_resolver.py` — resolves for dev/prod, raises when no active bundle
- `test_policy_enforcer.py` — input redaction, input block, output substitution
- `test_model_ollama.py` — retry on 503, timeout honoured (use `respx` to mock)
- `test_retrieval_chroma.py` — index + retrieve round-trip on a small corpus
- `test_serve_integration.py` — spawns FastAPI test client, POSTs `/v1/invoke`, asserts bundle_id in response and DuckDB row exists
- `test_hot_reload.py` — changes `deployments.json` during serving, assert next request uses new bundle
- Coverage ≥ 75% on runtime + adapters (slightly lower target than earlier phases due to integration nature)

---

## 11. Definition of Done

1. ✅ `workbench invoke --env dev` serves a real request end-to-end using Ollama + Chroma.
2. ✅ `workbench serve` runs a FastAPI server; `POST /v1/invoke` works.
3. ✅ Policy enforcement executes both pre- and post-model; violations logged.
4. ✅ Every request logged to DuckDB `inference_requests` with bundle_id.
5. ✅ Hot reload picks up deployment changes within 30s.
6. ✅ `experiment_runner` (Phase 2) can select real adapters, not just stubs.
7. ✅ Tests pass; coverage ≥ 75% on runtime + adapters.
8. ✅ Works on Apple Silicon with Ollama installed via `brew install ollama`.

---

## 12. Principle Traceability

| Principle | Phase 6 implementation |
|---|---|
| 1. Promote bundles, not models | Serving loads a bundle; the model is one component |
| 2. Evaluation before deployment | Serving only possible because the active bundle went through Phase 3 + 4 |
| 3. Environment state is explicit | Resolver reads `env`, not bundle id |
| 4. Evidence is persistent | Every inference logged to DuckDB |
| 5. Runtime resolves from registry | This phase is the implementation of Principle 5 |

---

## 13. Phase 6 → Phase 7 Handoff

Phase 7 adds champion-vs-challenger: the resolver can return **two** bundles, and the serving layer routes a fraction of traffic to each. The request log table already has `bundle_id`, so per-bundle metrics work for free. Rollback is `deployment_state_manager.set_active(env, previous_bundle_id)` — the primitive already exists in Phase 5.

---

## 14. Estimated Effort

| Task | Effort |
|---|---|
| Runtime resolver + cache | 1.5 h |
| Ollama adapter upgrade | 2 h |
| Chroma retrieval adapter + indexer | 2.5 h |
| Policy enforcer + pack loader | 2 h |
| FastAPI serving layer | 2 h |
| Hot reload loop | 1 h |
| DuckDB request logging | 0.5 h |
| CLI commands | 1 h |
| Tests | 3 h |
| **Total** | **~15.5 hours** (2 focused days) |

---

*End of SPEC — Phase 6.*
