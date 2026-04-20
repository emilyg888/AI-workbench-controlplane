# SPEC — Phase 8: Thin UI / Dashboard

**Project:** AI Workbench Control Plane
**Phase:** 8 of 8
**Target environment:** Local-first on MacBook Pro, macOS 13+
**Depends on:** Phase 7 complete (all data exists on disk + DuckDB)
**Status:** Draft specification
**Last updated:** 2026-04-20

---

## 1. Purpose & Goal

Make the system **easy to demo and operate**. Phase 8 adds a thin, read-mostly Streamlit dashboard over the existing registry and DuckDB. It does not introduce new business logic — it surfaces what Phases 1–7 already produce.

### Guiding principle

> The UI reads from the same source of truth as the CLI. Never a parallel state.

---

## 2. Scope

### 2.1 In scope

- Streamlit app (`src/workbench/ui/app.py`) launchable via `workbench ui`
- Read-only views for:
  - Bundle list + detail
  - Run history + scorecard viewer
  - Deployments (dev / prod) + history
  - Promotion log + decision detail
  - Lineage graph (rendered from Phase 7 DOT output)
  - Champion vs challenger comparison
- A **small number** of write actions, each reusing existing business logic functions (not duplicating logic):
  - Deploy to dev (calls `deployment_state_manager.set_active`)
  - Deploy to prod (same, with preconditions)
  - Rollback (calls `rollback.rollback`)
  - Approve / reject candidate (calls `promotion_engine.approve` / `reject`)
- Auth stub: localhost-only binding by default; optional shared-secret header for "don't surprise yourself" safety
- Tests for the dashboard layer via Streamlit's `AppTest` runner

### 2.2 Out of scope

| Deferred / explicitly not doing | Reason |
|---|---|
| Multi-user auth, SSO | Local-first scope |
| Real-time websockets | Streamlit reruns are sufficient for this use case |
| Mobile optimisation | Demo tool; desktop only |
| Write flows that duplicate CLI logic | Violates "same source of truth" principle |

---

## 3. Technology Choice

| Concern | Choice | Reason |
|---|---|---|
| Framework | **Streamlit** | Matches design §5 Phase 8; fast to build; pure Python |
| Run command | `workbench ui` → `streamlit run src/workbench/ui/app.py` | Packaged with the CLI |
| Charts | `altair` (ships with Streamlit) | No extra deps |
| Graphs | `graphviz` (via Streamlit's built-in `st.graphviz_chart`) | For lineage |
| Data source | DuckDB + the same JSON registry files | No parallel store |
| Auth | `st.secrets` optional shared secret; default: bind `127.0.0.1` only | Laptop-friendly |

### 3.1 Alternative considered

A React SPA + FastAPI: rejected for Phase 8. Streamlit keeps us under 1500 lines and demo-ready in a day.

---

## 4. Information Architecture

Single-page app with sidebar navigation. Six pages:

```
┌──────────────────────────────────────────────────┐
│  AI Workbench                                    │
├──────────┬───────────────────────────────────────┤
│ Sidebar  │  Main area                            │
│          │                                       │
│ ▸ Home   │  [selected page content]              │
│ ▸ Bundles│                                       │
│ ▸ Runs   │                                       │
│ ▸ Deploy │                                       │
│ ▸ Promot.│                                       │
│ ▸ Compare│                                       │
│          │                                       │
│ env: dev │  [env switcher at bottom]             │
└──────────┴───────────────────────────────────────┘
```

### 4.1 Home

- Current active bundle per environment (badges: dev / prod)
- Last 5 runs with aggregate score
- Last 5 promotion decisions
- Red banner if `workbench doctor` reports issues

### 4.2 Bundles

- Filterable table: name, version, state, created_at, lineage parent
- Click row → detail panel: full bundle JSON, state history, runs executed against it, promotion decisions
- "Archive" action (state → archived) with confirm dialog

### 4.3 Runs

- Filterable table by bundle / eval set / date / status
- Click run → tabs:
  - **Scorecard** (rendered `scorecard.md`)
  - **Metrics** (bar chart of the 6 scorer values)
  - **Predictions** (paginated table of `predictions.jsonl`)
  - **Config** (raw `config.json`)
  - **Timings** (p50/p95 chart)

### 4.4 Deployments

- Two-column layout: dev / prod, each showing the active bundle card (id, activated_at, promotion_decision link)
- "Deploy bundle to env" form (select approved bundle) with preconditions shown inline
- "Rollback" button with confirmation — shows previous bundle explicitly
- Below: deployment history table

### 4.5 Promotions

- Promotion log table, newest first
- Click row → detail: decision JSON, thresholds check table, regression violations list, link to evidence pack download (calls `evidence_pack.build` on demand)
- Pending `candidate` bundles get a highlighted section with "Approve" and "Reject" buttons

### 4.6 Compare

- Pick two bundles (champion, challenger)
- Pick time window
- Renders the Phase 7 comparison report inline: agreement rate, latency delta, policy deltas, sample of diverging outputs
- If a runtime challenger is configured for the current env, shows it pre-filled

### 4.7 Lineage (accessible from Bundles → detail)

- Renders the DOT graph from Phase 7 via `st.graphviz_chart`

---

## 5. Write Actions — Strict Rules

To preserve "same source of truth":

1. Every write action calls an existing Python function (no UI-only code paths).
2. Every write produces the same artifacts as the CLI (promotion log entry, history entry, state transition).
3. Every write requires an explicit confirm click — no drag-to-delete, no swipe-to-archive.
4. Errors from the underlying layer surface as Streamlit error banners, unmodified.

If a future phase adds a new governance check, the UI inherits it automatically because the UI just calls the same function.

---

## 6. Launch & Config

```bash
$ workbench ui
✓ Starting Streamlit on http://127.0.0.1:8501
  Workbench root: /Users/me/projects/ai-workbench
  Bound: 127.0.0.1 only (set WORKBENCH_UI_HOST=0.0.0.0 to expose)
```

### 6.1 Configuration

Env vars, all optional:

| Var | Default | Purpose |
|---|---|---|
| `WORKBENCH_ROOT` | `cwd` | Registry + DuckDB location |
| `WORKBENCH_UI_HOST` | `127.0.0.1` | Bind address |
| `WORKBENCH_UI_PORT` | `8501` | Port |
| `WORKBENCH_UI_TOKEN` | unset | If set, requires `?token=...` in URL |

### 6.2 Session state

Streamlit `st.session_state` holds the currently-selected env. It is read from `configs/environments.json` on every rerun — no stale config.

---

## 7. Module Layout

```
src/workbench/ui/
├── __init__.py
├── app.py                # entry point, sidebar, routing
├── pages/
│   ├── home.py
│   ├── bundles.py
│   ├── runs.py
│   ├── deployments.py
│   ├── promotions.py
│   ├── compare.py
│   └── lineage.py
├── components/
│   ├── bundle_card.py
│   ├── metrics_chart.py
│   ├── confirm_dialog.py
│   └── env_switcher.py
└── data.py               # thin readers that reuse bundle_manager, db, etc.
```

`data.py` **must not** reimplement any logic — only adapt return types for Streamlit rendering.

---

## 8. CLI Addition

| Command | Purpose |
|---|---|
| `workbench ui [--port N] [--host H]` | Launch Streamlit UI |

Implemented as `subprocess.run(["streamlit", "run", ...])`. No CLI-level option parsing beyond host/port — Streamlit owns the rest.

---

## 9. Testing Plan

- **Smoke test**: `streamlit run` starts without error on a fresh Phase 7 registry.
- **AppTest**: use `streamlit.testing.AppTest.from_file` to:
  - Load the bundles page, assert a known bundle appears
  - Navigate to its detail, assert metrics render
  - Click "Approve" on a candidate bundle, assert state transitioned
- **No-logic-leak test**: `grep -r "bundles.json" src/workbench/ui` returns nothing; UI only reaches data through `data.py`.
- **Localhost bind test**: default start does not bind `0.0.0.0` (verify via socket probe in test).

Coverage ≥ 60% on UI (lower target — Streamlit UI coverage is inherently harder).

---

## 10. Definition of Done

1. ✅ `workbench ui` launches Streamlit and loads all six pages without errors.
2. ✅ Home shows current dev + prod active bundles and recent activity.
3. ✅ Scorecard rendering matches the terminal output of Phase 3.
4. ✅ Deploy-to-dev, deploy-to-prod, rollback, approve, reject all work from the UI and produce identical artifacts to the CLI.
5. ✅ Lineage renders as a Graphviz chart.
6. ✅ UI binds localhost-only by default.
7. ✅ No UI module reads registry files directly — only via `data.py` which uses existing business logic.
8. ✅ Tests pass; coverage ≥ 60% on UI.

---

## 11. Principle Traceability

| Principle | Phase 8 implementation |
|---|---|
| 1. Promote bundles, not models | UI surfaces bundles everywhere; model is a sub-field |
| 2. Evaluation before deployment | Deploy form preconditions mirror CLI; cannot deploy non-approved |
| 3. Environment state is explicit | Env switcher shows the active bundle id prominently |
| 4. Evidence is persistent | Evidence-pack download button pulls from Phase 7 artifacts |
| 5. Runtime resolves from registry | UI never calls the runtime with ad-hoc bundle ids |

---

## 12. Post-Phase-8 Possibilities (Not in Scope)

Things the workbench is now ready for but this project is not delivering:

- Swap file-backed registry for S3/DynamoDB via adapter (AWS by config-change only, per design §1 line 14)
- Replace Ollama adapter with Bedrock adapter
- Add multi-tenant auth + RBAC
- Horizontal API deployment (Cloud Run / EKS)
- Event bus for change notifications

Each of these is a drop-in change at an adapter boundary established in Phases 1–7. None requires rewriting core logic.

---

## 13. Estimated Effort

| Task | Effort |
|---|---|
| App skeleton + sidebar + routing | 1 h |
| Home page | 1 h |
| Bundles page + detail | 2 h |
| Runs page + scorecard rendering | 2 h |
| Deployments page + forms | 2 h |
| Promotions page + approve/reject flows | 2 h |
| Compare page | 1.5 h |
| Lineage Graphviz rendering | 0.5 h |
| `workbench ui` CLI wrapper | 0.5 h |
| AppTest-based tests | 2 h |
| Polish, theming, demo script | 1.5 h |
| **Total** | **~16 hours** (2 focused days) |

---

## 14. Phase 8 Outcome — The Full Picture

After Phase 8 the workbench delivers, end-to-end:

> A local-first AI control plane, accessible from CLI or a dashboard, where engineers can register bundles (model + prompt + retrieval + policy + evaluation), run them against eval sets, score them with measurable metrics, promote them via auditable rules, deploy them to explicit environments with history and rollback, serve live traffic through a resolver that honours deployment state, and inspect the whole lifecycle through a browser — all on a MacBook Pro with zero cloud services.

That is the design principle from §1 of `design.md` made real:

> **Bundle is the deployable unit. Local first. AWS Cloud Services later via configuration change only.**

---

*End of SPEC — Phase 8. Series complete.*
