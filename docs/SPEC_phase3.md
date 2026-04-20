# SPEC — Phase 3: Evaluation Engine

**Project:** AI Workbench Control Plane
**Phase:** 3 of 8
**Target environment:** Local-first on MacBook Pro, macOS 13+
**Depends on:** Phase 2 complete (runs produce `predictions.jsonl`)
**Status:** Draft specification
**Last updated:** 2026-04-20

---

## 1. Purpose & Goal

Make promotion **evidence-based**. Phase 3 scores each run consistently and produces a human-readable scorecard plus a machine-readable metrics file. These artifacts feed Phase 4's promotion engine.

### Guiding principle

> No promotion decision without measurable evidence.
> (Design §8, Principle 2: *Evaluation before deployment*.)

---

## 2. Scope

### 2.1 In scope

- `evaluation_engine.py` — consumes a run's `predictions.jsonl`, scores it, writes `metrics.json` + `scorecard.md` into the run directory
- Scoring profile schema (`configs/scoring_profile.yaml`) defining which metrics to compute and with what weights
- Six baseline metrics: `correctness`, `groundedness`, `policy_compliance`, `refusal_quality`, `latency`, `completeness`
- Pluggable **scorer** interface so additional metrics can be added without changing the engine
- Baseline comparison: `eval --baseline <run_id>` shows deltas vs a prior run
- State transition: successful eval moves bundle from `draft → evaluated`
- DuckDB `metrics` table
- New CLI commands: `eval`, `show-scorecard`, `compare-runs`
- Tests for each scorer + engine

### 2.2 Out of scope

| Deferred | Phase |
|---|---|
| Promotion rules / thresholds enforcement | Phase 4 |
| Champion vs challenger dashboards | Phase 7 |
| LLM-as-judge scorers | Phase 7 (optional) |

---

## 3. Scoring Profile

`configs/scoring_profile.yaml`:

```yaml
version: "1"
name: default
scorers:
  correctness:
    type: exact_match        # or "substring", "llm_judge" (Phase 7)
    weight: 0.35
    case_sensitive: false
  groundedness:
    type: passage_overlap
    weight: 0.25
    min_overlap: 0.3
  policy_compliance:
    type: policy_check
    weight: 0.20
    policy_pack_ref: data/policies/claims_pack.yaml
  refusal_quality:
    type: refusal_classifier
    weight: 0.05
  latency:
    type: latency_budget
    weight: 0.10
    budget_p95_ms: 2000
  completeness:
    type: non_empty
    weight: 0.05
aggregate:
  method: weighted_mean      # or "min", "harmonic_mean"
```

Multiple profiles can coexist; each bundle references one via `components.evaluation.profile_ref`.

---

## 4. Scorer Interface

Every scorer implements the same protocol:

```python
class Scorer(Protocol):
    name: str
    def score(
        self,
        predictions: list[Prediction],
        eval_set: list[EvalExample],
        profile: dict,
    ) -> ScorerResult: ...

class ScorerResult(BaseModel):
    name: str
    value: float              # 0.0–1.0 (or normalised to that range)
    per_item: list[dict]      # {"input_id": ..., "value": ..., "explanation": "..."}
    notes: str | None = None
```

Scorers are stateless and pure functions of their inputs. This makes them trivially testable and cacheable.

### 4.1 Baseline scorers (Phase 3)

| Scorer | Type | Logic |
|---|---|---|
| `ExactMatchScorer` | `exact_match` | Output string equals `expected` (normalised whitespace/case) |
| `SubstringScorer` | `substring` | `expected` is a substring of `output` |
| `PassageOverlapScorer` | `passage_overlap` | Fraction of tokens in `output` that appear in retrieved `context` |
| `PolicyCheckScorer` | `policy_check` | Loads policy pack YAML; fires regex/keyword rules; 1.0 if no violations |
| `RefusalClassifierScorer` | `refusal_classifier` | Simple heuristic: detects refusal phrases; 1.0 if refusal-correct vs expected |
| `LatencyBudgetScorer` | `latency_budget` | 1.0 if p95 under budget, linearly degrades to 0 at 2× budget |
| `NonEmptyScorer` | `non_empty` | Fraction of non-empty, non-error outputs |

All stay on-laptop with no network calls. LLM-judge scorers are deferred to Phase 7.

---

## 5. Artifacts Produced

Into the existing `runs/<run_id>/` directory (Phase 2 wrote the predictions; Phase 3 appends):

```
runs/run_20260420T101530Z_claims_bundle_v1/
├── config.json          # from Phase 2
├── inputs.jsonl         # from Phase 2
├── predictions.jsonl    # from Phase 2
├── timings.json         # from Phase 2
├── run.log              # from Phase 2
├── metrics.json         # NEW
└── scorecard.md         # NEW
```

### 5.1 `metrics.json`

```json
{
  "run_id": "run_20260420T101530Z_claims_bundle_v1",
  "bundle_id": "claims_bundle_v1",
  "scoring_profile": "default@v1",
  "scored_at": "2026-04-20T10:20:00Z",
  "scores": {
    "correctness": 0.88,
    "groundedness": 0.92,
    "policy_compliance": 1.00,
    "refusal_quality": 0.95,
    "latency": 0.98,
    "completeness": 1.00
  },
  "aggregate": 0.91,
  "per_item_path": "metrics_per_item.jsonl"
}
```

### 5.2 `scorecard.md`

Human-readable summary:

```markdown
# Scorecard — claims_bundle_v1

**Run:** run_20260420T101530Z_claims_bundle_v1
**Eval set:** claims_smoke (50 examples)
**Scored:** 2026-04-20 10:20:00 UTC

## Aggregate: **0.91**

| Metric | Score | Weight | Weighted |
|---|---|---|---|
| Correctness       | 0.88 | 0.35 | 0.308 |
| Groundedness      | 0.92 | 0.25 | 0.230 |
| Policy compliance | 1.00 | 0.20 | 0.200 |
| Refusal quality   | 0.95 | 0.05 | 0.048 |
| Latency           | 0.98 | 0.10 | 0.098 |
| Completeness      | 1.00 | 0.05 | 0.050 |

## Failures
- q_017: output missing key fact (correctness=0)
- q_033: latency 3200ms exceeded 2× budget

## Notes
Retrieval returned 0 passages for 2 inputs; see predictions.jsonl.
```

---

## 6. Baseline Comparison

```bash
workbench compare-runs <candidate_run_id> --baseline <baseline_run_id>
```

Produces a delta table + writes `runs/<candidate>/comparison_vs_<baseline>.md`. This is the input format Phase 4 expects when it checks regression.

Delta rules:
- Green: +0.02 or more
- Red: −0.02 or more (potential regression)
- Neutral: within ±0.02

---

## 7. State Transition Effect

`workbench eval <run_id>` succeeds ⇒ the engine calls
`bundle_manager.transition_bundle(bundle_id, "evaluated")`.

If the bundle is already past `draft` (e.g. re-evaluating a `candidate`), the state is left unchanged — re-eval is idempotent.

---

## 8. CLI Additions

| Command | Purpose |
|---|---|
| `workbench eval <run_id> [--profile NAME] [--baseline RUN_ID]` | Score a run; optionally compare to baseline |
| `workbench show-scorecard <run_id>` | Render `scorecard.md` to terminal |
| `workbench compare-runs <run_id> --baseline <run_id>` | Delta table |

### 8.1 Example session

```bash
$ workbench eval run_20260420T101530Z_claims_bundle_v1
✓ Loaded 50 predictions
✓ Running 6 scorers ... done
  correctness       0.88
  groundedness      0.92
  policy_compliance 1.00
  refusal_quality   0.95
  latency           0.98
  completeness      1.00
  aggregate         0.91
✓ Bundle claims_bundle_v1: draft → evaluated
✓ Wrote metrics.json and scorecard.md

$ workbench compare-runs run_20260420T104500Z_v2 --baseline run_20260420T101530Z_v1
METRIC              BASELINE  CANDIDATE   DELTA
correctness          0.88      0.91       +0.03  ↑
groundedness         0.92      0.89       -0.03  ↓ regression
...
```

---

## 9. DuckDB Additions

```sql
ALTER TABLE runs ADD COLUMN correctness DOUBLE;
ALTER TABLE runs ADD COLUMN groundedness DOUBLE;
ALTER TABLE runs ADD COLUMN policy_compliance DOUBLE;
ALTER TABLE runs ADD COLUMN refusal_quality DOUBLE;
ALTER TABLE runs ADD COLUMN latency_score DOUBLE;
ALTER TABLE runs ADD COLUMN completeness DOUBLE;
ALTER TABLE runs ADD COLUMN aggregate_score DOUBLE;
ALTER TABLE runs ADD COLUMN scoring_profile VARCHAR;
ALTER TABLE runs ADD COLUMN scored_at TIMESTAMP;
```

Migrations live in `src/workbench/migrations/` and run on engine start.

---

## 10. Module Responsibilities

### 10.1 `evaluation_engine.py` (replaces Phase 1 stub)
- `evaluate_run(run_id, profile_name=None, baseline_run_id=None) -> EvalResult`
- Loads predictions + eval set, dispatches to scorers, aggregates, writes artifacts, transitions bundle, writes DuckDB row.

### 10.2 `scorers/` (new package)
- `base.py` — Scorer protocol + registry
- `exact_match.py`, `substring.py`, `passage_overlap.py`, `policy_check.py`, `refusal.py`, `latency.py`, `non_empty.py`

### 10.3 `scoring_profile.py` (new)
- Loads and validates `configs/scoring_profile.yaml` into a pydantic model.

### 10.4 `comparison.py` (new)
- `compare(baseline_metrics, candidate_metrics) -> ComparisonReport`

---

## 11. Testing Plan

- Per-scorer unit tests with hand-crafted predictions/expected pairs
- Engine test: fixture run dir → assert `metrics.json` + `scorecard.md` + DuckDB row
- Comparison test: assert deltas and regression flags
- Idempotency test: re-running `eval` on the same run overwrites cleanly
- Coverage ≥ 80% on all scorers and engine

---

## 12. Definition of Done

1. ✅ `workbench eval <run_id>` produces `metrics.json` + `scorecard.md`.
2. ✅ All six baseline scorers implemented and tested.
3. ✅ Aggregate score computed per scoring profile's weights.
4. ✅ Bundle transitions to `evaluated` on successful scoring.
5. ✅ `compare-runs` flags regressions at ±0.02 threshold.
6. ✅ DuckDB `runs` table populated with per-metric columns.
7. ✅ Tests pass; coverage ≥ 80%.
8. ✅ Re-running `eval` is idempotent.

---

## 13. Principle Traceability

| Principle | Phase 3 implementation |
|---|---|
| 2. Evaluation before deployment | State machine enforces `draft → evaluated` before any promotion path |
| 4. Evidence is persistent | `metrics.json` + `scorecard.md` live in the run directory forever |
| 5. Runtime resolves from registry | Scoring profile referenced from the bundle, not from CLI flags |

---

## 14. Phase 3 → Phase 4 Handoff

Phase 4 reads `metrics.json` + optional `comparison_vs_<baseline>.md`, applies `promotion_rules.yaml` thresholds, and decides `candidate` / `approved` / `rejected`. No changes needed to Phase 3 artifacts.

---

## 15. Estimated Effort

| Task | Effort |
|---|---|
| Scoring profile schema + loader | 0.5 h |
| Scorer base + registry | 0.5 h |
| Six baseline scorers | 3 h |
| Engine (aggregate, artifact writing) | 1.5 h |
| Comparison module | 1 h |
| DuckDB migration | 0.5 h |
| CLI commands | 1 h |
| Tests | 2 h |
| **Total** | **~10 hours** |

---

*End of SPEC — Phase 3.*
