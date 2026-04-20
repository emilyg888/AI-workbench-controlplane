# SPEC — Phase 5: Environment Deployment States

**Project:** AI Workbench Control Plane
**Phase:** 5 of 8
**Target environment:** Local-first on MacBook Pro, macOS 13+
**Depends on:** Phase 4 complete (bundles can reach `approved` state)
**Status:** Draft specification
**Last updated:** 2026-04-20

---

## 1. Purpose & Goal

Make the **active bundle in each environment explicit**. Phase 5 introduces first-class deployment commands: promote an `approved` bundle into `dev`, then (separately, with its own gate) into `prod`. Every environment always names a specific bundle version — never "latest".

### Guiding principle

> Never rely on "latest".
> (Design §8, Principle 3: *Environment state is explicit*.)

---

## 2. Scope

### 2.1 In scope

- `deployment_state_manager.py` fully implemented (Phase 1 had skeleton; this phase activates it)
- Deployment history (`registry/deployment_history.json`) — append-only log of every env change
- CLI commands: `deploy-to-dev`, `deploy-to-prod`, `show-active`, `show-deployment-history`
- Enforcement: `deploy-to-prod` requires the bundle to have spent time in `dev` (configurable min dwell time)
- Soak-time / cool-off gate configurable per environment
- Bundle state transitions: `approved → deployed`
- `undeploy` command (sets an environment's active bundle to `null`)
- Tests for all deployment paths

### 2.2 Out of scope

| Deferred | Phase |
|---|---|
| Runtime execution of the deployed bundle | Phase 6 |
| Rollback to previous version | Phase 7 |
| Canary / traffic splitting | Phase 7+ (not scoped in original design) |

---

## 3. Environment Config

`configs/environments.json` extended from Phase 1:

```json
{
  "dev": {
    "description": "Local development environment",
    "requires_bundle_state": "approved",
    "min_dwell_before_next_env_hours": 0
  },
  "prod": {
    "description": "Local production-equivalent environment",
    "requires_bundle_state": "approved",
    "requires_previous_env": "dev",
    "min_dwell_before_next_env_hours": 1
  }
}
```

Rules encoded here are enforced by `deployment_state_manager.set_active()`.

### 3.1 Ordering

Phase 5 treats `dev` and `prod` as an ordered pair: `dev` is a precondition for `prod`. The order is declarative — a future env (e.g. `staging`) can be inserted by adding `requires_previous_env`.

---

## 4. Deployment State File

`registry/deployments.json`:

```json
{
  "dev": {
    "active_bundle_id": "claims_bundle_v2",
    "activated_at": "2026-04-20T11:05:00Z",
    "activated_by": "local-user",
    "promotion_decision_id": "prom_20260420T110000Z_claims_bundle_v2"
  },
  "prod": {
    "active_bundle_id": "claims_bundle_v1",
    "activated_at": "2026-04-19T15:30:00Z",
    "activated_by": "local-user",
    "promotion_decision_id": "prom_20260419T150000Z_claims_bundle_v1"
  }
}
```

Every activation links back to the promotion decision that authorised it — closing the evidence loop from Phase 4.

---

## 5. Deployment History

`registry/deployment_history.json` — append-only list of every deployment event:

```json
[
  {
    "event_id": "dep_20260420T110500Z_dev",
    "env": "dev",
    "action": "activate",
    "bundle_id": "claims_bundle_v2",
    "previous_bundle_id": "claims_bundle_v1",
    "at": "2026-04-20T11:05:00Z",
    "by": "local-user",
    "promotion_decision_id": "prom_20260420T110000Z_claims_bundle_v2",
    "notes": null
  },
  {
    "event_id": "dep_20260420T120500Z_prod",
    "env": "prod",
    "action": "activate",
    "bundle_id": "claims_bundle_v2",
    "previous_bundle_id": "claims_bundle_v1",
    "at": "2026-04-20T12:05:00Z",
    "by": "local-user",
    "promotion_decision_id": "prom_20260420T110000Z_claims_bundle_v2",
    "notes": "prod promotion after 1h dwell in dev"
  }
]
```

Phase 7 reads this file to implement rollback.

---

## 6. Preconditions for Deployment

The deployment state manager enforces, in order:

1. **Bundle exists** in `registry/bundles.json`.
2. **Bundle state is** `approved` (or `deployed` if already active in a different env).
3. **If target env requires previous env**, the bundle must be currently active in that previous env.
4. **Dwell time**: `now - previous_env.activated_at ≥ min_dwell_before_next_env_hours`.
5. **No duplicate activation**: if the bundle is already active in this env, no-op with a clear message.

Any failure → exit code 2, no change to state, no history entry.

### 6.1 State transition side effect

- When a bundle first enters `deployed`, its state becomes `deployed`.
- When that bundle is replaced (a new bundle is activated), the **old** bundle stays at `deployed` state if it's still active in any environment; if it's no longer active anywhere, it's transitioned to `approved` (not archived — it remains promotable again).

---

## 7. CLI Additions

| Command | Purpose |
|---|---|
| `workbench deploy-to-dev <bundle_id> [--notes "..."]` | Activate bundle in `dev` |
| `workbench deploy-to-prod <bundle_id> [--notes "..."]` | Activate bundle in `prod` (preconditions enforced) |
| `workbench undeploy --env <env> [--reason "..."]` | Set env's active bundle to null |
| `workbench show-active [--env ENV]` | (Already in Phase 1) now returns real values |
| `workbench show-deployment-history [--env ENV] [--bundle ID]` | Tabular history |

### 7.1 Example session

```bash
$ workbench deploy-to-dev claims_bundle_v2
✓ Bundle claims_bundle_v2 (state=approved) eligible for dev
✓ Previous dev bundle: claims_bundle_v1
✓ dev → claims_bundle_v2 (activated at 2026-04-20T11:05:00Z)
✓ History entry dep_20260420T110500Z_dev written

$ workbench deploy-to-prod claims_bundle_v2
✗ Cannot deploy to prod: dwell time 0h 12m in dev, required 1h 0m
  Try again after 2026-04-20T12:05:00Z

# ... one hour later ...

$ workbench deploy-to-prod claims_bundle_v2
✓ All preconditions satisfied
✓ prod → claims_bundle_v2 (activated at 2026-04-20T12:05:00Z)
✓ claims_bundle_v1 still active in no env; state approved → approved (unchanged)

$ workbench show-active
ENV    ACTIVE_BUNDLE_ID      ACTIVATED_AT
dev    claims_bundle_v2      2026-04-20T11:05:00Z
prod   claims_bundle_v2      2026-04-20T12:05:00Z

$ workbench show-deployment-history --env prod
EVENT_ID                              ACTION     BUNDLE              PREVIOUS             AT
dep_20260420T120500Z_prod             activate   claims_bundle_v2    claims_bundle_v1     2026-04-20 12:05
dep_20260419T153000Z_prod             activate   claims_bundle_v1    null                 2026-04-19 15:30
```

---

## 8. Module Responsibilities

### 8.1 `deployment_state_manager.py` (completing Phase 1 skeleton)
- `get_active(env) -> Deployment` (Phase 1)
- `set_active(env, bundle_id, promotion_decision_id, notes=None) -> Deployment` ← **full implementation** here
- `undeploy(env, reason) -> Deployment`
- `list_environments() -> list[str]` (Phase 1)
- `history(env=None, bundle_id=None) -> list[DeploymentEvent]`
- `check_preconditions(env, bundle_id) -> list[str]` (returns empty list if OK)

### 8.2 `environments.py` (new)
Pydantic model of `environments.json` including ordering and dwell rules.

### 8.3 CLI wiring in `cli.py`

### 8.4 Bundle state housekeeping (minor edit in `bundle_manager.py`)
Helper to downgrade `deployed → approved` when a bundle is no longer active anywhere.

---

## 9. Testing Plan

- Happy path: deploy to dev, wait mock time, deploy to prod
- Blocked: deploy to prod without dev fails with clear message
- Blocked: deploy non-approved bundle fails
- Dwell time enforcement (use `freezegun` or injected clock)
- `undeploy` leaves active_bundle_id null and writes history
- Bundle state downgrades correctly when no longer active anywhere
- History is append-only (even `undeploy` appends)
- Tests use a `tmp_path` registry — no pollution of real registry
- Coverage ≥ 80%

---

## 10. Definition of Done

1. ✅ `deploy-to-dev` and `deploy-to-prod` work with full precondition checks.
2. ✅ `deployments.json` always names a concrete `bundle_id` or `null`.
3. ✅ Every deployment event appended to `deployment_history.json`.
4. ✅ `show-active` and `show-deployment-history` produce correct output.
5. ✅ Dwell time enforcement uses a mockable clock.
6. ✅ Bundle state correctly transitions `approved → deployed` and back.
7. ✅ `undeploy` is logged and reversible.
8. ✅ Tests pass; coverage ≥ 80%.

---

## 11. Principle Traceability

| Principle | Phase 5 implementation |
|---|---|
| 1. Promote bundles, not models | Deployment activates a `bundle_id` |
| 2. Evaluation before deployment | Precondition 2: state must be `approved` (which is only reachable through Phase 3 + 4) |
| 3. Environment state is explicit | `deployments.json` always names a specific version; no "latest" anywhere |
| 4. Evidence is persistent | `deployment_history.json` is append-only and links to `promotion_decision_id` |
| 5. Runtime resolves from registry | Runtime (Phase 6) will read `deployments.json` — never CLI args |

---

## 12. Phase 5 → Phase 6 Handoff

Phase 6 implements `runtime_resolver.py`: given an `env`, load the active bundle and actually execute it. Phase 5 guarantees that `deployments.json` is always valid and references an existing bundle, so Phase 6 doesn't need defensive coding.

---

## 13. Estimated Effort

| Task | Effort |
|---|---|
| Environment config schema + loader | 0.5 h |
| Deployment state manager (full) | 2 h |
| Precondition checks + injectable clock | 1 h |
| Deployment history (append-only, atomic) | 0.5 h |
| Bundle state housekeeping | 0.5 h |
| CLI commands | 1 h |
| Tests (incl. frozen-clock tests) | 2 h |
| **Total** | **~7.5 hours** |

---

*End of SPEC — Phase 5.*
