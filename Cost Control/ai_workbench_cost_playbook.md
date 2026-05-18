# AI Workbench Cost Optimization Playbook

## Core Principle
Cost = Compute + Tokens + Storage + Orchestration + Human Effort

---

## 1. Infrastructure
- IaC → eliminate idle compute
- Event-driven execution → run only when needed

---

## 2. Model & Compute
- Local runtime > managed inference (reduce token cost)
- Model routing → use small/cheap models for simple tasks
- Structured outputs → reduce token usage and retries

---

## 3. Retrieval Optimization (Highest ROI)
- Semantic chunking > fixed chunking
- Hybrid search (vector + keyword) > vector-only
- Top-K minimisation (3–5 chunks)
- Optional re-ranking

---

## 4. RAG vs Fine-tuning
- RAG preferred for:
  - lower cost
  - better governance
  - easier updates
- Avoid expensive training cycles

---

## 5. Caching (Critical)
- Response cache (Q → A)
- Retrieval cache (Q → chunks)
- Embedding cache

→ Near-zero marginal cost at scale

---

## 6. Pre-computation
- Materialise semantic views
- Pre-aggregate metrics
- Pre-compute signals

→ Shift cost from runtime to batch

---

## 7. Vector Storage Strategy
### S3 + Local (Default)
- cheap storage
- load FAISS on demand
- zero idle cost

### OpenSearch (When needed)
- high concurrency
- large datasets
- advanced filtering

### Best Practice
- tiered approach (S3 → local → OpenSearch)

---

## 8. Evaluation Cost Control
- sample-based evaluation
- LLM-as-judge only for edge cases
- reuse evaluation results

---

## 9. Governance as Cost Control
- enforce policy before LLM
- reduce retries and invalid queries

---

## 10. Human-in-the-loop
- escalate only high-risk cases
- avoid automatic re-processing loops

---

## 11. Storage Lifecycle
- prune unused embeddings
- version vector indexes
- compress vectors (float16)

---

## 12. Advanced Pattern
### Cost-aware Query Planner
- estimate token + compute cost before execution
- route to cheapest viable path

---

## Final Architecture Summary

[Infrastructure]
IaC + event-driven

[Compute]
Local runtime + model routing

[Data]
RAG + semantic layer + pre-compute

[Retrieval]
Semantic chunking + hybrid search + small K

[Runtime]
Caching + adaptive retrieval

[Storage]
S3 + lifecycle management

[Control Plane]
Custom workbench > managed services

[Evaluation]
Targeted + efficient

---

## Key Takeaways
1. Retrieval optimization drives biggest savings
2. Caching eliminates marginal cost
3. Avoid always-on infrastructure
4. Shift work left (pre-compute)
5. Make system cost-aware, not just AI-powered
