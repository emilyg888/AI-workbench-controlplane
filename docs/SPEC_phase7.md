# SPEC — Phase 7: Comparison & Governance Hardening

**Project:** AI Workbench Control Plane
**Phase:** 7 of 8
**Target environment:** Local-first on MacBook Pro, macOS 13+
**Depends on:** Phase 6 complete (runtime serves real traffic with logging)
**Status:** Draft specification
**Last updated:** 2026-04-20

---

## 1. Purpose & Goal

Turn the workbench into something **enterprise-worthy**. Phase 7 adds the governance features that separate a toy from a real control plane: side-by-side champion vs challenger comparison, a promotion evidence pack per decision, rollback, bundle lineage, and an optional LLM-as-judge scorer.

### Guiding principle

> Every decision must be defensible, reversible, and traceable.
> (Design §8, Principles 3, 4, 5.)

---

## 2. Scope

### 2.1 In scope

- **Champion vs challenger** at serving time: traffic split or shadow mode
- **Promotion evidence pack**: zippable bundle of all artifacts that led to an approval
- **Rollback**: one-command revert of an environment to its previous active bundle
- **Bundle lineage**: follow parent → child chains; visualise history
- **LLM-as-judge scorer** (optional, gated by config): uses a local Ollama model as judge
- **`workbench doctor`**: validates registry integrity (orphan runs, dangling references, state machine drift)
- New CLI commands: `compare-bundles`, `rollback`, `lineage`, `evidence-pack`, `doctor`
- Tests including rollback safety and shadow-mode correctness

### 2.2 Out of scope

| Deferred | Phase |
|---|---|
| UI / dashboard rendering | Phase 8 |
| Multi-tenant / user auth | beyond scope |
| Distributed deployment | N/A (local-first) |

---

## 3. Champion vs Challenger

### 3.1 Mode configuration

Extend `configs/environments.json`:

```json
{
  "dev": {
    "description": "Local development environment",
    "challenger": {
      "enabled": true,
      "bundle_id": "claims_bundle_v3",
      "mode": "shadow",           // "shadow" | "traffic_split"
      "traffic_fraction": 0.10    // only used when mode=traffic_split
    }
  }
}
```

### 3.2 Modes

**Shadow mode**
- Every request goes to the champion (the active bundle) and is returned to the user.
- The same request is also sent to the challenger asynchronously.
- Both responses are logged to DuckDB; only the champion's is served.
- Zero user-facing risk.

**Traffic split**
- Each request is routed to champion or challenger with probability `1 - traffic_fraction` / `traffic_fraction`.
- The chosen bundle's response is served.
- Deterministic routing key: `hash(trace_id) % 100` keeps any single session consistent.

### 3.3 Comparison report

`workbench compare-bundles --env dev --window 24h`:
- Pulls all `inference_requests` rows for both bundles in the window.
- For each matching input (shadow mode) or sampled set (split mode), computes:
  - Output agreement rate
  - Latency delta (p50, p95)
  - Policy-action difference rate
- Writes `runs/comparison_<champ>_vs_<chall>_<ts>/` with a report.

### 3.4 State implications

Enabling a challenger does **not** change `deployments.json` — the challenger is advisory. Promoting the challenger to champion is done via `workbench deploy-to-dev <challenger>` (existing Phase 5 command).

---

## 4. Promotion Evidence Pack

`workbench evidence-pack <promotion_decision_id> --output pack.zip`:

Produces a self-contained zip that proves why a bundle was promoted. Contents:

```
pack.zip
├── MANIFEST.json                        # versions, timestamps, checksums
├── bundle.json                          # bundle record at time of decision
├── promotion_decision.json              # the decision itself
├── promotion_report.md                  # human-readable
├── candidate_run/                       # full Phase 2 + 3 artifacts
│   ├── config.json
│   ├── inputs.jsonl
│   ├── predictions.jsonl
│   ├── timings.json
│   ├── metrics.json
│   └── scorecard.md
├── baseline_run/                        # if regression check used a baseline
│   └── ... (same structure)
├── comparison.md                        # candidate vs baseline delta table
├── scoring_profile.yaml                 # as-resolved
├── promotion_rules.yaml                 # as-resolved
├── policy_pack.yaml                     # snapshot
└── prompt_template.txt                  # snapshot
```

`MANIFEST.json` includes SHA-256 hashes of every file — tampering is detectable.

This is the artifact an auditor can open on any laptop, no tooling required, and see the full chain of evidence.

---

## 5. Rollback

`workbench rollback --env <env> [--to <bundle_id>] [--reason "..."]`

- If `--to` is given, requires that `bundle_id` to be a bundle previously active in that env (from `deployment_history.json`).
- If `--to` is omitted, reverts to the **immediately previous** active bundle per history.
- Appends a new event to `deployment_history.json` with `action: "rollback"`.
- Updates `deployments.json`.
- Does **not** revert the bundle's lifecycle state (if it was `deployed`, it stays `deployed`).
- Refuses if the target bundle has been archived since.

### 5.1 Example

```bash
$ workbench rollback --env prod --reason "groundedness regression spotted in prod logs"
✓ Current active: claims_bundle_v3 (activated 2026-04-20T12:05:00Z)
✓ Rolling back to claims_bundle_v2 (previously active 2026-04-19T15:30:00Z–2026-04-20T12:05:00Z)
✓ prod → claims_bundle_v2
✓ History entry dep_20260420T140000Z_prod written (action=rollback)
```

Runtime (Phase 6) hot-reload picks this up within 30 s — prod is back.

---

## 6. Bundle Lineage

Every bundle already carries `lineage.parent_bundle_id` (Phase 1 schema). Phase 7 adds the tooling:

### 6.1 `workbench lineage <bundle_id>`

Produces an ASCII tree:

```
claims_bundle_v1 (deployed)
├── claims_bundle_v2 (deployed)
│   └── claims_bundle_v3 (approved, rejected from prod 2026-04-20T14:00)
└── claims_bundle_v1a (archived)
```

### 6.2 `workbench lineage --dot <bundle_id>`

Emits Graphviz DOT source that Phase 8 can render. Users can pipe it to `dot -Tpng` locally.

### 6.3 `create-bundle` enhancement

Now accepts `--parent <bundle_id>` which fills `lineage.parent_bundle_id` and validates the parent exists.

---

## 7. LLM-as-Judge Scorer (Optional)

`scorers/llm_judge.py` — a new Phase 3 scorer, activated by opting in from `scoring_profile.yaml`:

```yaml
scorers:
  llm_correctness:
    type: llm_judge
    weight: 0.30
    judge_model: llama3.1-70b
    judge_provider: local-ollama
    rubric_ref: configs/rubrics/correctness_v1.md
    max_score: 5
    normalise_to_unit: true
```

- The judge is invoked once per prediction with rubric + expected + output.
- Retries once on parse failure.
- Because this can be slow, the scorer supports `--parallel N` at eval time.
- **Bounded cost**: local only. No cloud calls from the workbench, ever.

This is opt-in and not required for Phase 7 completion.

---

## 8. Registry Integrity: `workbench doctor`

Diagnostic command. Checks:

| Check | What it catches |
|---|---|
| Every `bundles.json` entry has a valid state | Hand-edited corruption |
| `deployments.json[env].active_bundle_id` exists in `bundles.json` | Dangling reference |
| Every active bundle is in state `deployed` | State machine drift |
| Every `promotion_log.json[*].bundle_id` exists | Orphaned decisions |
| Every run in `runs/` corresponds to a known bundle | Orphan run directories |
| DuckDB schema matches current migrations | Missing ALTER TABLE |
| `deployment_history.json` in chronological order | Reordered history |

Output is a report; `--fix` applies non-destructive fixes (e.g. re-deriving deployed state, running migrations). Destructive actions (archive orphans) require `--fix --yes`.

---

## 9. CLI Additions

| Command | Purpose |
|---|---|
| `workbench compare-bundles --env ENV [--window DURATION]` | Runtime comparison report (champ vs chall) |
| `workbench rollback --env ENV [--to BUNDLE_ID]` | Revert environment to previous bundle |
| `workbench lineage <bundle_id> [--dot]` | Show lineage tree |
| `workbench evidence-pack <decision_id> --output FILE.zip` | Produce self-contained audit zip |
| `workbench doctor [--fix [--yes]]` | Registry integrity check |

---

## 10. Module Responsibilities

### 10.1 `serving/http.py` + `runtime_resolver.py` updates
Resolver now returns `ResolvedRuntime` with optional `challenger`. HTTP handler routes per mode.

### 10.2 `comparison/runtime_compare.py` (new)
Pulls from DuckDB, computes agreement / latency / policy deltas.

### 10.3 `evidence_pack.py` (new)
Bundles artifacts into a zip with SHA-256 manifest.

### 10.4 `rollback.py` (new)
Thin wrapper over `deployment_state_manager.set_active` with history lookup.

### 10.5 `lineage.py` (new)
Reads `bundles.json`, builds the tree, renders ASCII / DOT.

### 10.6 `doctor.py` (new)
Independent diagnostic module — no imports from business logic to avoid circularity.

### 10.7 `scorers/llm_judge.py` (new, optional)
Phase 3 scorer; implements protocol from §4 of Phase 3 spec.

---

## 11. Testing Plan

- **Shadow mode**: every request logged twice, user gets champion output
- **Traffic split**: deterministic routing by `trace_id`, distribution within ±3% of fraction over 1000 requests
- **Rollback**: explicit target, implicit (previous), refuses when target archived
- **Evidence pack**: manifest hashes match all file contents; zip opens; all referenced files present
- **Lineage**: cycles are rejected at creation time; orphans handled gracefully
- **Doctor**: synthetic corruption fixtures — missing bundle, drifted state, orphan run
- **LLM judge**: mocked Ollama response parses correctly; malformed response retries once then fails gracefully
- Coverage ≥ 75% overall

---

## 12. Definition of Done

1. ✅ Shadow and traffic-split modes both work and log correctly.
2. ✅ `compare-bundles` produces a reliable report over a time window.
3. ✅ `rollback` reverts prod within seconds (plus runtime hot-reload).
4. ✅ `evidence-pack` produces a self-contained, hash-verified zip.
5. ✅ `lineage` renders ASCII and DOT.
6. ✅ `doctor` detects and (where safe) fixes registry drift.
7. ✅ Optional LLM-judge scorer works against local Ollama.
8. ✅ Tests pass; coverage ≥ 75%.

---

## 13. Principle Traceability

| Principle | Phase 7 implementation |
|---|---|
| 1. Promote bundles, not models | Evidence pack captures the whole bundle; lineage tracks bundle IDs |
| 2. Evaluation before deployment | LLM-judge adds higher-quality evidence; doctor catches bypasses |
| 3. Environment state is explicit | Rollback uses history — never "previous" by implication |
| 4. Evidence is persistent | Evidence pack is the culmination of this principle |
| 5. Runtime resolves from registry | Champion/challenger still both resolved through the registry |

---

## 14. Phase 7 → Phase 8 Handoff

Phase 8 is a **read-only visualisation** layer. All the data it renders is already on disk or in DuckDB. No new writing paths, no schema changes. Phase 8 wraps `list-bundles`, `list-runs`, `show-scorecard`, `show-deployment-history`, `lineage`, and `compare-bundles` in a Streamlit UI.

---

## 15. Estimated Effort

| Task | Effort |
|---|---|
| Champion/challenger routing + config | 2 h |
| Runtime comparison module | 2 h |
| Evidence pack (zip + manifest) | 2 h |
| Rollback + history lookup | 1 h |
| Lineage (tree + DOT) | 1.5 h |
| Doctor (checks + safe fixes) | 3 h |
| LLM-judge scorer (optional) | 2 h |
| CLI wiring | 1 h |
| Tests | 3.5 h |
| **Total** | **~18 hours** (2.5 focused days) |

---

*End of SPEC — Phase 7.*
