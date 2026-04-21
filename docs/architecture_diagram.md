                         ┌──────────────────────────────┐
                         │        USERS / BUILDERS      │
                         │   CLI • Notebook • UI        │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    AI WORKBENCH CONTROL PLANE                        │
├──────────────────────────────────────────────────────────────────────┤
│ 1. Bundle Manager                                                    │
│    - Defines bundle (model + prompt + retrieval + policy + eval)     │
│                                                                      │
│ 2. Experiment Runner                                                 │
│    - Executes bundle → captures outputs + timings                    │
│                                                                      │
│ 3. Evaluation Engine                                                 │
│    - Scores correctness, groundedness, compliance                    │
│                                                                      │
│ 4. Promotion Engine                                                  │
│    - Applies policy rules → candidate / approved / rejected          │
│                                                                      │
│ 5. Deployment State Manager                                          │
│    - Controls active bundle per env (dev / prod)                     │
└──────────────┬───────────────────────────────────────────────────────┘
               │
       ┌───────┴───────────────┐
       │                       │
       ▼                       ▼
┌──────────────────────┐   ┌──────────────────────────────────────────┐
│ STORAGE / EVIDENCE   │   │         RUNTIME EXECUTION                │
├──────────────────────┤   ├──────────────────────────────────────────┤
│ bundles.json         │   │ Runtime Resolver (env → bundle)          │
│ runs/ (artifacts)    │   │                                          │
│ metrics.json         │   │ Retrieval Adapter (RAG)                  │
│ promotion_log.json   │   │ Model Adapter (LLM)                      │
│ deployment_history   │   │ Policy Enforcement Point                 │
│ DuckDB (runs + logs) │   │ Response Generator                       │
└──────────────┬───────┘   └──────────────┬───────────────────────────┘
               │                          │
               ▼                          ▼
        ┌──────────────────────────────────────────────┐
        │           DATA / KNOWLEDGE LAYER             │
        │ eval sets • retrieval corpora • policies     │
        │ semantic layer • signal layer                │
        └──────────────────────────────────────────────┘
