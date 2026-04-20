# SPEC — Phase 4: Promotion Workflow

**Project:** AI Workbench Control Plane
**Phase:** 4 of 8
**Target environment:** Local-first on MacBook Pro, macOS 13+
**Depends on:** Phase 3 complete (runs have `metrics.json`)
**Status:** Draft specification
**Last updated:** 2026-04-20

---

## 1. Purpose & Goal

Introduce **controlled lifecycle progression**. Phase 4 turns measured evidence into automated, auditable promotion decisions: given a scored run, does this bundle clear the bar to become a `candidate`, then `approved`?

The promotion engine is the **gate** between experimentation and deployment.

### Guiding principle

> Only evaluated bundles can become approved — and only via rules that leave a record.
> (Design §8, Principles 2 & 4.)

---

## 2. Scope

### 2.1 In scope

- `promotion_engine.py` — loads a run's metrics, applies thresholds, compares to baseline, emits a decision
- `configs/promotion_rules.yaml` — declarative thresholds + regression rules
- Promotion log (`registry/promotion_log.json`) — append-only record of every decision
- Lifecycle transitions: `evaluated → candidate → approved` (and `→ rejected` as a terminal state)
- Optional human-in-the-loop approval step for the `candidate → approved` transition
- New CLI commands: `propose-promotion`, `approve`, `reject`, `show-promotion-log`
- Tests for rule evaluation, baseline regression, and the full flow

### 2.2 Out of scope

| Deferred | Phase |
|---|---|
| Actual deployment to dev/prod | Phase 5 |
| Champion vs challenger side-by-side | Phase 7 |
| Rollback | Phase 7 |
| UI approval workflow | Phase 8 |

---

## 3. Promotion Rules Schema

`configs/promotion_rules.yaml`:

```yaml
version: "1"
name: default
thresholds:
  correctness: 0.85
  groundedness: 0.90
  policy_compliance: 1.00
  refusal_quality: 0.80
  latency: 0.70
  completeness: 0.95
  aggregate: 0.85

regression_checks:
  enabled: true
  baseline: prod                 # "prod" | "dev" | run_id
  max_absolute_drop: 0.02        # per-metric
  strict_metrics:                # any drop fails, even <0.02
    - policy_compliance

approval:
  candidate_requires_all_thresholds: true
  approved_requires:
    mode: auto                   # "auto" | "manual"
    # If mode=manual, a human runs `workbench approve <bundle_id>`
```

### 3.1 Rule evaluation order

1. Load candidate's `metrics.json`.
2. Check every `thresholds.<metric>` — any fail ⇒ **rejected**.
3. If `regression_checks.enabled`, load baseline (see §3.2). Any violation ⇒ **rejected**.
4. If all pass ⇒ **candidate**.
5. If `approval.approved_requires.mode == auto` ⇒ immediately → **approved**.
6. If `manual`, remain `candidate` until a human runs `workbench approve`.

### 3.2 Baseline resolution

- `baseline: prod` — use the current active bundle in prod (from `deployments.json`). If prod is empty, no regression check.
- `baseline: dev` — same for dev.
- `baseline: <run_id>` — explicit prior run.

If the baseline bundle has no `metrics.json` for any metric, that metric's regression check is skipped (with a log warning).

---

## 4. Promotion Decision Object

```json
{
  "decision_id": "prom_20260420T110000Z_claims_bundle_v2",
  "bundle_id": "claims_bundle_v2",
  "run_id": "run_20260420T104500Z_claims_bundle_v2",
  "decided_at": "2026-04-20T11:00:00Z",
  "rules_profile": "default@v1",
  "result": "approved",
  "checks": {
    "thresholds": {
      "correctness": {"value": 0.91, "threshold": 0.85, "pass": true},
      "groundedness": {"value": 0.92, "threshold": 0.90, "pass": true},
      "policy_compliance": {"value": 1.00, "threshold": 1.00, "pass": true},
      "refusal_quality": {"value": 0.88, "threshold": 0.80, "pass": true},
      "latency": {"value": 0.97, "threshold": 0.70, "pass": true},
      "completeness": {"value": 1.00, "threshold": 0.95, "pass": true},
      "aggregate": {"value": 0.92, "threshold": 0.85, "pass": true}
    },
    "regression": {
      "baseline_bundle_id": "claims_bundle_v1",
      "baseline_run_id": "run_20260420T101530Z_claims_bundle_v1",
      "violations": []
    }
  },
  "approver": "auto",
  "notes": null
}
```

Every decision — approve **or** reject — appends one record to `registry/promotion_log.json` (atomic write).

---

## 5. Artifacts

### 5.1 `registry/promotion_log.json`

Append-only array of decisions. Never edited; rejected bundles stay in the log for audit.

### 5.2 Per-run evidence pack

Into `runs/<run_id>/`:

```
runs/run_20260420T104500Z_claims_bundle_v2/
├── ...                           # Phase 2 + 3 artifacts
├── promotion_decision.json       # NEW — copy of the decision for this run
└── promotion_report.md           # NEW — human-readable summary
```

`promotion_report.md` renders the decision as:

```markdown
# Promotion Decision — claims_bundle_v2

**Result:** ✅ approved (auto)
**Rules profile:** default@v1
**Baseline:** claims_bundle_v1 (prod)
**Run:** run_20260420T104500Z_claims_bundle_v2

## Thresholds — all pass
| Metric | Value | Threshold |
|---|---|---|
| correctness | 0.91 | ≥ 0.85 ✓ |
| groundedness | 0.92 | ≥ 0.90 ✓ |
| ...

## Regression vs prod (claims_bundle_v1)
No violations.
```

---

## 6. State Machine Enforcement

The state machine (from Phase 1) is the single source of truth. Phase 4 adds enforcement hooks:

- `evaluated → candidate` **only** via `promotion_engine.propose(run_id)` after thresholds pass
- `candidate → approved` **only** via `promotion_engine.approve(bundle_id, approver)` (auto or manual)
- Any state → `rejected` (terminal) via `promotion_engine.reject(bundle_id, reason)`

A `rejected` state is added to the state machine in this phase.

### 6.1 Updated state diagram

```
draft → evaluated → candidate → approved → deployed
                        │
                        └────► rejected
```

---

## 7. CLI Additions

| Command | Purpose |
|---|---|
| `workbench propose-promotion <run_id> [--rules NAME]` | Run the promotion engine; may transition to `candidate` or `rejected`. Auto-approves if rules say so. |
| `workbench approve <bundle_id> [--notes "..."]` | Manual approval: `candidate → approved` |
| `workbench reject <bundle_id> --reason "..."` | Force reject |
| `workbench show-promotion-log [--bundle ID]` | Tabular history |

### 7.1 Example session

```bash
$ workbench propose-promotion run_20260420T104500Z_claims_bundle_v2
✓ Loaded metrics.json (aggregate 0.92)
✓ Thresholds: 7/7 pass
✓ Regression vs prod (claims_bundle_v1): 0 violations
✓ claims_bundle_v2: evaluated → candidate
✓ approval.mode=auto → candidate → approved
✓ Decision logged: prom_20260420T110000Z_claims_bundle_v2

$ workbench show-promotion-log
DECISION_ID                                   BUNDLE             RESULT     APPROVER   AT
prom_20260420T110000Z_claims_bundle_v2        claims_bundle_v2   approved   auto       2026-04-20 11:00
prom_20260419T150000Z_claims_bundle_v1        claims_bundle_v1   approved   manual     2026-04-19 15:00
```

---

## 8. Module Responsibilities

### 8.1 `promotion_engine.py` (replaces Phase 1 stub)
- `propose(run_id, rules_profile=None) -> PromotionDecision`
- `approve(bundle_id, approver, notes=None) -> PromotionDecision`
- `reject(bundle_id, reason) -> PromotionDecision`
- `load_rules(name) -> PromotionRules`

### 8.2 `promotion_rules.py` (new)
Pydantic model of the rules YAML.

### 8.3 `state_machine.py` updates
- Add `rejected` state (terminal)
- Add transition: any → `rejected`

### 8.4 `deployment_state_manager.py` additions
- `get_active_bundle(env) -> Bundle | None` (used for baseline resolution)

---

## 9. Testing Plan

- Threshold pass/fail matrix tests (parameterised)
- Regression check: baseline missing metric, baseline below candidate, baseline above candidate
- Strict metric drop (e.g. `policy_compliance`) fails even with tiny delta
- `approval.mode=manual` leaves state at `candidate`
- `approval.mode=auto` transitions to `approved`
- Reject transition from any state writes log entry
- `promotion_log.json` is append-only (never shrinks)
- Coverage ≥ 80% on `promotion_engine.py`, `promotion_rules.py`

---

## 10. Definition of Done

1. ✅ `propose-promotion` reads metrics, applies rules, writes decision, transitions state.
2. ✅ Rejected bundles are logged but never auto-retried.
3. ✅ Regression checks correctly reference the active bundle in `deployments.json`.
4. ✅ `approve` and `reject` commands work with audit trail.
5. ✅ `promotion_log.json` is append-only and atomic-write-safe.
6. ✅ State machine includes `rejected` terminal state.
7. ✅ Tests pass; coverage ≥ 80%.
8. ✅ `promotion_decision.json` + `promotion_report.md` land in the run directory.

---

## 11. Principle Traceability

| Principle | Phase 4 implementation |
|---|---|
| 1. Promote bundles, not models | Promotion operates on `bundle_id`, never on model names |
| 2. Evaluation before deployment | Engine refuses to promote runs without `metrics.json` |
| 4. Evidence is persistent | Every decision persisted in `promotion_log.json` + per-run report |
| 5. Runtime resolves from registry | No deployment happens here — that's Phase 5's concern |

---

## 12. Phase 4 → Phase 5 Handoff

Phase 5 adds `deploy-to-dev` and `deploy-to-prod` commands that refuse to run unless the bundle state is `approved`. The promotion log gives Phase 5 the evidence trail it needs to answer *"why was this bundle deployed?"*.

---

## 13. Estimated Effort

| Task | Effort |
|---|---|
| Promotion rules schema + loader | 1 h |
| Promotion engine (propose/approve/reject) | 2.5 h |
| State machine additions | 0.5 h |
| Promotion log writer (atomic, append-only) | 0.5 h |
| Per-run evidence artifacts | 1 h |
| CLI commands | 1.5 h |
| Tests | 2.5 h |
| **Total** | **~9.5 hours** |

---

*End of SPEC — Phase 4.*
