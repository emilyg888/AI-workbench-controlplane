1. Solution design
   Purpose

Build a real AI Workbench ControlPlane that manages the lifecycle of AI bundles from experimentation through evaluation and promotion into controlled environments.

The key principle:

Model alone is not the deployable unit
Bundle is the deployable unit

Where a bundle is:
model + prompt + retrieval + policy + evaluation profile

Local first and AWS Cloud Services later via configuration change ONLY

# High-level architecture

┌──────────────┐ ┌──────────────────────┐ ┌───────────────────┐
│ Authoring │ --> │ AI Workbench │ --> │ Runtime │
│ Notebook/CLI │ │ Control Plane │ │ Execution │
└──────────────┘ └──────────────────────┘ └───────────────────┘
│
▼
┌──────────────────────┐
│ Data + Registry │
│ + Metrics Stores │
└──────────────────────┘

## Architecture layers

### A. Authoring layer

Where engineers and data practitioners define and launch work.

Includes:

CLI
Notebook
optional lightweight UI later

### B. Control plane

This is the core of the workbench.

Responsibilities:

register bundles
run experiments
evaluate outcomes
compare challenger vs champion
approve or reject promotion
manage deployment states

### C. Runtime layer

Executes the active approved bundle.

Includes:
Semantic Layer
Signal Layer
Model inference
RAG Retrieval
Policy checks
GuardRails
Response generation
App Layer

D. Storage and evidence layer

Persists the full audit trail.

Includes:

registry
run artifacts
metrics
deployment history
promotion decisions

2. Map of solution components

Here’s the left-to-right component map.

┌──────────────────────┐
│ USERS / BUILDERS │
│ notebook • cli • ui │
└──────────┬───────────┘
│
▼
┌─────────────────────────────────────────────────────────────────┐
│ AI WORKBENCH CONTROL PLANE │
├─────────────────────────────────────────────────────────────────┤
│ 1. Bundle Manager │
│ - define bundle metadata │
│ - version prompt / retrieval / policy / model │
│ │
│ 2. Experiment Runner │
│ - execute candidate bundle │
│ - capture config, outputs, timings │
│ │
│ 3. Evaluation Engine │
│ - score correctness, groundedness, compliance │
│ - compare candidate vs active bundle │
│ │
│ 4. Promotion Engine │
│ - apply thresholds │
│ - decide candidate / approved / rejected │
│ │
│ 5. Deployment State Manager │
│ - manage active bundle in dev / prod │
│ - support rollback later │
└──────────┬──────────────────────────────────────────────────────┘
│
├──────────────────────────────┐
│ │
▼ ▼
┌──────────────────────┐ ┌────────────────────────────┐
│ STORAGE / EVIDENCE │ │ RUNTIME EXECUTION │
├──────────────────────┤ ├────────────────────────────┤
│ Bundle Registry │ │ Model Adapter │
│ Run Artifacts │ │ Retrieval Adapter │
│ Metrics Store │ │ Policy Enforcement Point │
│ Promotion Log │ │ Response Generator │
│ Deployment History │ │ Runtime Resolver │
└──────────────────────┘ └────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────┐
│ DATA / KNOWLEDGE LAYER │
├─────────────────────────────────────────────────────────────────┤
│ eval datasets • semantic context • retrieval corpora • policies │
└─────────────────────────────────────────────────────────────────┘

3. Logical solution components

1) Bundle Manager

Owns the definition of the deployable unit.

Inputs:

- semantic layer, signal layer
- model name
- prompt version
- retrieval profile
- policy pack
- evaluation profile
- Outputs
- bundle record
- bundle version/state

Why it matters

This is the registry abstraction that lifts the workbench beyond traditional “model registry”.

2. Experiment Runner

Runs a bundle against an eval set or test scenario.

Responsibilities:

- load bundle
- resolve runtime config
- execute run
- capture outputs
- store raw artifacts
- Evidence captured
- config.json
- outputs.json
- timings
- run metadata

3. Evaluation Engine

Scores each run consistently.

Example metrics

- correctness
- groundedness
- policy compliance
- refusal quality
- latency
- completeness

Output

- metrics.json
- scorecard.md
- promotion recommendation input

4. Promotion Engine

This is the gate.

Responsibilities

- load candidate results
- compare to thresholds
- compare to current prod/dev bundle
- decide:
  - reject
  - candidate
  - approved

Example rule
correctness >= 0.85
groundedness >= 0.90
policy_compliance = 1.0
no regression vs prod

5. Deployment State Manager

Controls what is active in each environment.

State example

- dev -> claims_bundle_v4
- prod -> claims_bundle_v3

Responsibilities

- assign active bundle per environment
- record change history
- enable rollback later

6. Runtime Resolver

At runtime, determines which approved bundle to execute.

Responsibilities

- read active environment state
- resolve the correct bundle
- invoke model + retrieval + policy path

7. Stores

Use simple local-first persistence.

Recommended stack

- DuckDB: run history, metrics, deployment history
- JSON/YAML: bundle registry, environment state, promotion rules
- filesystem: artifacts, outputs, scorecards

4. Suggested repo-level component layout
   ai-workbench/
   ├── configs/
   │ ├── promotion_rules.yaml
   │ ├── scoring_profile.yaml
   │ └── environments.json
   ├── registry/
   │ ├── bundles.json
   │ ├── deployments.json
   │ └── promotion_log.json
   ├── runs/
   │ └── run_xxxx/
   ├── db/
   │ └── workbench.duckdb
   ├── data/
   │ ├── eval_sets/
   │ ├── retrieval/
   │ └── policies/
   ├── src/workbench/
   │ ├── bundle_manager.py
   │ ├── experiment_runner.py
   │ ├── evaluation_engine.py
   │ ├── promotion_engine.py
   │ ├── deployment_state_manager.py
   │ ├── runtime_resolver.py
   │ ├── cli.py
   │ └── adapters/
   └── docs/

5. Build phases

The best way to build this is in tight phases so you get something working early.

# Phase 1 — Core control plane skeleton

Goal: establish the core lifecycle structure.

Deliverables

- repo scaffold
- bundle schema
- registry JSON
- deployment state JSON
- CLI skeleton
- basic lifecycle states
- Outcome

You can create/list bundles and manage state.

Example commands

- create-bundle
- list-bundles
- show-active

# Phase 2 — Experiment execution

Goal: turn bundle definitions into actual runs.

Deliverables

- experiment runner
- run artifact folders
- config capture
- sample runtime adapter
- eval dataset loader
- Outcome

You can run a bundle and produce raw outputs.

Example artifact
runs/run_001/
config.json
predictions.json

# Phase 3 — Evaluation engine

Goal: make promotion evidence-based.

Deliverables

- scoring engine integration
- metrics schema
- scorecard generation
- candidate vs baseline comparison
- Outcome

Each run gets measurable scores.

Example outputs
metrics.json
scorecard.md

# Phase 4 — Promotion workflow

Goal: introduce controlled lifecycle progression.

Deliverables

- promotion rules YAML
- promotion engine
- lifecycle transition validation
- decision logging
- Outcome

Only evaluated bundles can become approved.

Example states
draft → evaluated → candidate → approved
Phase 5 — Environment deployment states

Goal: separate dev and prod behavior.

Deliverables

- deployment state manager
- active bundle resolver
- deploy-to-dev command
- deploy-to-prod command
- Outcome

You have explicit versioned deployment states.

Example
dev -> bundle_v4
prod -> bundle_v3

# Phase 6 — Runtime integration

Goal: connect the workbench to real execution.

Deliverables
local model adapter
retrieval adapter
policy enforcement integration
environment-aware runtime resolution
Outcome

The runtime executes the approved active bundle, not ad hoc configs.

# Phase 7 — Comparison and governance hardening

Goal: make it enterprise-worthy.

Deliverables

- challenger vs champion comparison
- promotion evidence pack
- deployment history
- rollback support
- bundle lineage view
- Outcome

You now have a strong architecture story for interviews and demos.

# Phase 8 — Thin UI / dashboard

Goal: make the system easier to demo.

Deliverables

- Streamlit or lightweight web UI
- bundle list
- run history
- scorecards
- active deployments
- Outcome

Much stronger demonstration value.

6. Recommended phase plan in table form
   PHASE FOCUS MAIN OUTPUT

---

1 Foundation registry + lifecycle skeleton
2 Execution experiment runner + run artifacts
3 Evaluation metrics + scorecards
4 Promotion rules + approval logic
5 Deployment states dev/prod active bundle control
6 Runtime integration real model/retrieval/policy execution
7 Governance hardening rollback + champion/challenger
8 Demo layer UI/dashboard

7. MVP scope

For a first real version, keep it tight.

MVP

- 2 bundles
- 1 eval set
- 1 runtime adapter
- 1 scoring profile
- 2 environments: dev, prod
- CLI only
- local JSON + DuckDB

That is enough to prove the architecture.

8. Strong design principles

Use these as guardrails while building.

- Principle 1: Promote bundles, not models
  - This is the most important one.

- Principle 2: Evaluation before deployment
  - No direct draft-to-prod path.

- Principle 3: Environment state is explicit
  - Never rely on “latest”.

- Principle 4: Evidence is persistent
  - Every decision should leave artifacts.

- Principle 5: Runtime is controlled by registry state
  - Runtime should resolve from active deployment state, not from ad hoc arguments.

9. Best executive summary

We're building the solution like this:

The AI Workbench is a local-first control plane for managing AI bundle lifecycle. It provides versioned bundle registration, experiment execution, evaluation-driven promotion, and explicit deployment state management across dev and prod. The workbench sits above runtime execution and ensures only approved configurations are activated.

10. Simple end-to-end flow
    Define Bundle
    ↓
    Run Experiment
    ↓
    Evaluate Results
    ↓
    Approve / Reject
    ↓
    Deploy to Dev
    ↓
    Promote to Prod
    ↓
    Runtime resolves active approved bundle

11. Best next build order

If you want the most efficient coding order:

1. bundle_manager.py
2. experiment_runner.py
3. evaluation_engine.py
4. promotion_engine.py
5. deployment_state_manager.py
6. runtime_resolver.py
7. cli.py

That order keeps dependencies simple and gets you to a working MVP fastest.

Summary
PR: emilyg888/AI-workbench-controlplane#1 — 9 commits (one per phase + cleanup)

Phase	Delivered
1	Registry + state machine + 6 CLI cmds
2	experiment_runner + adapter protocol + stubs + DuckDB runs, 3 cmds
3	6 scorers + scorecard + comparison + auto-transition to evaluated, 3 cmds
4	Promotion engine + rejected state + append-only log + per-run evidence, 4 cmds
5	Full deployment manager + preconditions + dwell + history + injectable clock, 4 cmds
6	Runtime resolver + Ollama (respx-mocked) + Chroma (lazy) + policy enforcer + FastAPI, 3 cmds
7	Shadow/traffic-split + rollback + lineage + evidence pack + doctor + runtime compare, 5 cmds
8	Streamlit UI (6 pages) + workbench ui + AppTest + no-logic-leak assertion
154 tests pass · ruff clean · 75% overall coverage (80–100% on core).

Claude Code - Honest calibration from this session:

Phase 1 (spec said 9 h, human dev time) — I finished it in maybe 15–20 min wall-clock.
Phase 6 (spec said 15.5 h, heaviest phase) — maybe 25–35 min wall-clock.
Whole series (phases 1–8, spec total ~95 h) was a single session, probably 2–3 hours of real wall-clock and low six-figures of tokens (rough guess — 200–400k).
So re-scaled to agent units, the proposed fixes are roughly:

Patching Wall clock	Rough token budget
3.1 snapshot-on-approval	15–30 min	~30–60k
3.3 policy-based promotion	8–15 min	~15–30k
3.2 prod eval loop	15–30 min	~30–60k
3.4 plane split (refactor)	20–40 min	~40–80k
3.5 LLM contract	5–10 min	~10–20k