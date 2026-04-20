# SPEC — Phase 2: Experiment Execution

**Project:** AI Workbench Control Plane
**Phase:** 2 of 8
**Target environment:** Local-first on MacBook Pro (Apple Silicon or Intel), macOS 13+
**Depends on:** Phase 1 complete (bundle registry + state machine + CLI skeleton)
**Status:** Draft specification
**Last updated:** 2026-04-20

---

## 1. Purpose & Goal

Turn bundle definitions into **actual runs**. Phase 2 makes a bundle executable: given a `bundle_id` and an eval dataset, the workbench loads the bundle, resolves its runtime config, executes it against each input, and persists the raw outputs + metadata as a durable **run artifact**.

Phase 2 delivers **execution and evidence capture only** — no scoring yet. A run produces `predictions.json`, `config.json`, and `timings.json`. Phase 3 turns those into metrics.

### Guiding principle

> Every run is reproducible and leaves a complete evidence trail.
> (Design §8, Principle 4: *Evidence is persistent*.)

---

## 2. Scope

### 2.1 In scope

- `experiment_runner.py` — loads a bundle, runs it against an eval dataset, captures artifacts
- One working **runtime adapter** (local stub or Ollama) behind a stable interface
- One working **retrieval adapter** (stub returning empty context, or a simple file-based retriever)
- Eval dataset loader (JSONL format)
- Run artifact layout: `runs/run_<ts>_<bundle_id>/` with `config.json`, `inputs.jsonl`, `predictions.jsonl`, `timings.json`, `run.log`
- DuckDB `workbench.duckdb` created; `runs` table populated per run
- New CLI commands: `run-experiment`, `list-runs`, `show-run`
- Unit tests + one integration test running end-to-end against the stub adapter

### 2.2 Out of scope

| Deferred | Phase |
|---|---|
| Scoring / metrics / scorecards | Phase 3 |
| Promotion rules | Phase 4 |
| Real policy enforcement | Phase 6 |
| Champion vs challenger comparison | Phase 7 |

---

## 3. Local-First Stack Additions

| New dependency | Reason |
|---|---|
| `duckdb` (already installed in Phase 1) | Run history & timings table |
| `httpx` | Optional: Ollama HTTP calls from the local adapter |
| `jsonlines` | Stream read/write of eval sets and predictions |
| `python-dotenv` | Load optional local env overrides (e.g. `OLLAMA_HOST`) |

All still runs on a laptop with no cloud services. Ollama (if used) runs locally via `brew install ollama`.

---

## 4. Run Artifact Layout

Every run creates a directory:

```
runs/run_20260420T101530Z_claims_bundle_v1/
├── config.json        # resolved bundle + runtime config snapshot
├── inputs.jsonl       # copy of the eval set used (for reproducibility)
├── predictions.jsonl  # one JSON object per input, with output + metadata
├── timings.json       # per-request + aggregate timing stats
└── run.log            # plain-text log of the run
```

### 4.1 `config.json`

Complete snapshot — bundle record, adapter names, eval dataset path + hash, git SHA if available, Python version, timestamp. Enough to reproduce the run byte-for-byte (minus model non-determinism).

### 4.2 `predictions.jsonl`

One line per input:
```json
{"input_id": "q_001", "input": {...}, "output": "...", "context": [...], "latency_ms": 842, "error": null}
```

`context` is the retrieved passages (empty list if retrieval stub). `error` is non-null if this single input failed — failures do not abort the run.

### 4.3 `timings.json`

```json
{
  "run_id": "run_20260420T101530Z_claims_bundle_v1",
  "started_at": "2026-04-20T10:15:30Z",
  "finished_at": "2026-04-20T10:17:02Z",
  "total_inputs": 50,
  "succeeded": 49,
  "failed": 1,
  "p50_latency_ms": 780,
  "p95_latency_ms": 1420,
  "total_wall_ms": 92000
}
```

---

## 5. Adapter Interfaces

Adapters are the boundary between the control plane and the actual model/retrieval. Phase 2 defines the **contract**; only stubs and one real implementation are needed.

### 5.1 `ModelAdapter` protocol

```python
class ModelAdapter(Protocol):
    name: str
    def generate(self, prompt: str, params: dict) -> ModelResult: ...

class ModelResult(BaseModel):
    text: str
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: int
    raw: dict  # adapter-specific payload
```

### 5.2 `RetrievalAdapter` protocol

```python
class RetrievalAdapter(Protocol):
    name: str
    def retrieve(self, query: str, profile: dict) -> list[Passage]: ...

class Passage(BaseModel):
    id: str
    text: str
    score: float
    metadata: dict
```

### 5.3 Phase 2 deliverables

- `adapters/model_stub.py` — deterministic echo adapter for tests
- `adapters/model_ollama.py` — calls local Ollama via `httpx` (optional if Ollama isn't installed)
- `adapters/retrieval_stub.py` — returns empty list
- `adapters/retrieval_file.py` — simple BM25-free retriever: loads documents from `data/retrieval/<profile>.jsonl`, returns top-k by substring match (placeholder; Phase 6 swaps for a real vector store)

Adapter selection is driven by `bundle.components.model.provider` and `bundle.components.retrieval.profile_ref`. An adapter registry maps provider strings to classes.

---

## 6. Eval Dataset Format

JSONL, one example per line:

```json
{"input_id": "q_001", "input": {"question": "What is...?"}, "expected": "...", "tags": ["easy"]}
```

Loader: `data/eval_sets/<name>.jsonl`. Phase 2 ships with `data/eval_sets/claims_smoke.jsonl` containing 5 examples for the smoke test.

---

## 7. DuckDB Schema

Created on first run in `db/workbench.duckdb`.

```sql
CREATE TABLE IF NOT EXISTS runs (
  run_id        VARCHAR PRIMARY KEY,
  bundle_id     VARCHAR NOT NULL,
  eval_set      VARCHAR NOT NULL,
  started_at    TIMESTAMP NOT NULL,
  finished_at   TIMESTAMP,
  total_inputs  INTEGER,
  succeeded     INTEGER,
  failed        INTEGER,
  p50_latency_ms INTEGER,
  p95_latency_ms INTEGER,
  status        VARCHAR  -- 'running'|'completed'|'failed'
);
```

JSON files remain the source of truth. DuckDB is an **index** for fast queries — `list-runs`, filtering by bundle, etc.

---

## 8. CLI Additions

| Command | Purpose |
|---|---|
| `workbench run-experiment --bundle <id> --eval-set <name> [--limit N]` | Execute a bundle against an eval set; writes run artifact + DuckDB row |
| `workbench list-runs [--bundle ID] [--limit N]` | Table of recent runs |
| `workbench show-run <run_id>` | Pretty-print `config.json` + summary of `timings.json` |

### 8.1 Example session

```bash
$ workbench run-experiment --bundle claims_bundle_v1 --eval-set claims_smoke
✓ Loaded bundle claims_bundle_v1 (state=draft)
✓ Loaded eval set claims_smoke (5 examples)
✓ Using adapters: model=stub retrieval=stub
  [1/5] q_001 ... 812ms ✓
  [2/5] q_002 ... 790ms ✓
  ...
✓ Run complete: run_20260420T101530Z_claims_bundle_v1
  5 succeeded, 0 failed, p50=792ms, p95=1120ms
  Artifacts: runs/run_20260420T101530Z_claims_bundle_v1/

$ workbench list-runs
RUN_ID                                              BUNDLE              EVAL_SET        STATUS     P50
run_20260420T101530Z_claims_bundle_v1               claims_bundle_v1    claims_smoke    completed  792
```

---

## 9. Module Responsibilities

### 9.1 `experiment_runner.py` (replaces Phase 1 stub)
- `run_experiment(bundle_id, eval_set, limit=None) -> RunResult`
- Resolves adapters, iterates over eval set, catches per-input errors, writes artifacts.

### 9.2 `adapters/registry.py` (new)
- `get_model_adapter(provider: str) -> ModelAdapter`
- `get_retrieval_adapter(profile_ref: str) -> RetrievalAdapter`

### 9.3 `adapters/model_stub.py`, `adapters/model_ollama.py`, `adapters/retrieval_stub.py`, `adapters/retrieval_file.py` (new)

### 9.4 `storage.py` additions
- `new_run_dir(bundle_id: str) -> Path`
- `write_jsonl(path, records)` / `read_jsonl(path)`

### 9.5 `db.py` (new)
- Thin DuckDB wrapper: `connect()`, `ensure_schema()`, `insert_run()`, `update_run()`, `list_runs(filters)`.

---

## 10. Error Handling

| Failure mode | Behaviour |
|---|---|
| Single input errors (adapter timeout, parse error) | Logged, `error` field in `predictions.jsonl`, run continues |
| Adapter unavailable (e.g. Ollama not running) | Run fails fast before starting; clear message; no artifact directory created |
| Bundle not found | Exit code 3 |
| Eval set not found | Exit code 3 |
| Partial run interrupted (Ctrl+C) | `status='failed'` in DuckDB; partial artifacts preserved for debugging |

---

## 11. Testing Plan

### 11.1 Unit tests
- `test_experiment_runner.py` — stub adapters, mock eval set, assert artifact structure
- `test_adapters_registry.py` — provider → class mapping
- `test_db.py` — DuckDB schema creation, insert, list

### 11.2 Integration test
- `test_e2e_stub_run.py` — creates a bundle, runs it against a fixture eval set, asserts 5 predictions written and DuckDB row inserted

### 11.3 Coverage target
≥ 80% on `experiment_runner.py`, `adapters/*`, `db.py`.

---

## 12. Definition of Done

1. ✅ `workbench run-experiment --bundle X --eval-set Y` produces a run artifact directory and a DuckDB row.
2. ✅ `config.json` contains enough info to reproduce the run.
3. ✅ `predictions.jsonl` has one line per input (including failures).
4. ✅ `timings.json` includes p50/p95 latency.
5. ✅ `list-runs` and `show-run` work.
6. ✅ Runs never silently succeed: any setup failure (missing bundle, missing eval set, adapter unavailable) exits non-zero with a clear message.
7. ✅ Tests pass; coverage ≥ 80% on new modules.
8. ✅ Works end-to-end with the stub adapter on a fresh venv.

---

## 13. Principle Traceability

| Principle | Phase 2 implementation |
|---|---|
| 1. Promote bundles, not models | Runner takes a `bundle_id`, never a raw model name |
| 2. Evaluation before deployment | Runs produce evidence; Phase 3 turns it into scores before any promotion |
| 3. Environment state is explicit | Runs are independent of `deployments.json`; an experiment is pre-deployment evidence |
| 4. Evidence is persistent | Every run leaves `config.json`, `predictions.jsonl`, `timings.json`, `run.log` on disk |
| 5. Runtime resolves from registry | Adapters resolve from `bundle.components`, not CLI flags |

---

## 14. Phase 2 → Phase 3 Handoff

Phase 3 reads `runs/<run_id>/predictions.jsonl` + the eval set's `expected` field to compute scores. It writes `metrics.json` and `scorecard.md` **into the same run directory** without modifying existing files. The `runs` DuckDB table gains extra columns in Phase 3 (`correctness`, `groundedness`, etc.) via `ALTER TABLE`.

---

## 15. Estimated Effort

| Task | Effort |
|---|---|
| Experiment runner + artifact writer | 2 h |
| Stub adapters + registry | 1 h |
| Ollama adapter (optional) | 1 h |
| Simple file retrieval adapter | 1 h |
| DuckDB wrapper + schema | 1 h |
| CLI commands + output formatting | 1.5 h |
| Tests + fixtures | 2 h |
| **Total** | **~9.5 hours** |

---

*End of SPEC — Phase 2.*
