---
marp: true
theme: default
paginate: true
class: invert
---

# AI Workbench
## Cost Optimisation Playbook

From $$$ GenAI → Cost-Intelligent AI Systems

---

# 1. The Problem

AI cost is not just model cost

**Total Cost =**
- Compute
- Tokens
- Storage
- Orchestration
- Human effort

---

# 2. The Strategy

Shift from:

❌ Always-on + model-heavy  
➡️  

✅ On-demand + retrieval-optimised + governed

---

# 3. Core Principle

> “Move work out of runtime wherever possible”

- Pre-compute > real-time compute  
- Retrieve > generate  
- Cache > recompute  

---

# 4. Architecture View

IaC → Local Runtime → RAG → Control Plane → Apps  
↓  
Cost Optimisation Layer (every step)

---

# 5. Key Levers (Executive Summary)

1. Zero idle infrastructure (IaC)
2. Retrieval efficiency (biggest ROI)
3. Caching (near-zero marginal cost)
4. Model routing (right-size intelligence)
5. Pre-computation (shift left)

---

# 6. Outcome

Traditional: High cost per query  
Optimised: Low cost per query → near-zero at scale  

---

# --- TECH SECTION ---

# 7. Infrastructure Optimisation

IaC → deploy on demand → destroy after use  

- No idle clusters  
- Event-driven execution  

---

# 8. Local Runtime > Managed Services

- Local LLM (LM Studio / Ollama)  
- DuckDB + FAISS  

---

# 9. Model Routing

Simple → small model  
SQL → medium model  
Narrative → strong model  

---

# 10. Retrieval = Cost Engine

More chunks → more tokens → more cost  

---

# 11. Semantic Chunking

Fixed chunks ❌  
Meaning-based chunks ✅  

---

# 12. Hybrid Search

Vector + Keyword → precision + meaning  

---

# 13. Top-K Optimisation

Before: K=10 → high tokens  
After: K=3 → low tokens  

---

# 14. Caching Layer

Q→A, Q→retrieval, embedding cache  

---

# 15. Pre-Computation

Compute once → reuse forever  

---

# 16. RAG > Fine-Tuning

Lower cost, better governance  

---

# 17. Vector Storage Strategy

S3 → FAISS (on demand)  

---

# 18. When to Use OpenSearch

- high concurrency  
- large datasets  
- filtering  

---

# 19. Tiered Vector Architecture

S3 → FAISS → OpenSearch  

---

# 20. Evaluation Cost Control

Sample, target, reuse  

---

# 21. Governance = Cost Control

Policy before LLM  

---

# 22. Storage Lifecycle

Prune, version, compress  

---

# 23. Event-Driven Execution

No query → no compute  

---

# 24. Human-in-the-loop

Targeted escalation only  

---

# 25. Advanced Pattern

Cost-aware query planner  

---

# 26. Final Architecture

Infra → IaC  
Compute → Local + dynamic routing  
Data → RAG  
Retrieval → Optimised  
Runtime → Cache  
Storage → S3  
Control → Workbench  
Evaluation → Targeted  

---

# 27. Key Takeaways

- Retrieval drives savings  
- Cache eliminates marginal cost  
- Avoid always-on infra  
- Shift work left  
- Be cost-aware  

---

# 28. Closing

Cost-intelligent AI systems
