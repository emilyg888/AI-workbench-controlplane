---
marp: true
theme: default
paginate: true
class: invert
---


# Airlines AI Platform — Engineering Brief

## 1. Objective

## 2. System Overview

## 3. Layer Responsibilities

## 4. Control Contracts

## 5. Data & Interface Contracts

## 6. RAG Execution Contract

## 7. Evaluation & Promotion

## 8. Non-Functional Requirements

## 9. Definition of Done

---

## 1. Objective

Build a governed enterprise AI platform where:

- All AI operates on certified data only
- Policy enforcement occurs before LLM access (PEP)
- Outputs are validated and auditable
- System is continuously evaluated and improved

---

## 2. System Overview

Pipeline:

Data → Platform → Governance → Semantic → Signal → Workbench → GenAI → Applications

Key constraint:
👉 LLM is a bounded component inside a controlled system

---

## 3. Layer Responsibilities

### Data Platform

- Ingest batch + streaming data
- Store in S3 + Snowflake

### Governance

- Enforce data quality
- Maintain lineage
- Apply access control

### Semantic Layer

- Expose certified views only
- No raw table access allowed

### Signal Layer

- Generate ML + rule-based signals

### Workbench

- Experiment and evaluate signals
- Promote validated patterns

### GenAI Platform

- Execute RAG pipeline
- Apply guardrails and routing

### Applications

- Consume validated outputs only

---

## 4. Control Contracts

| Layer     | Rule                                 |
| --------- | ------------------------------------ |
| Ingestion | All data must pass schema validation |
| Semantic  | Only certified views exposed         |
| Retrieval | Must enforce policy filtering        |
| LLM       | No direct data access                |
| Output    | Must pass validation before use      |

👉 These rules must not be bypassed

---

## 5. Data & Interface Contracts

### Semantic Layer Contract

- Input: curated tables
- Output: certified views
- Guarantee: consistent business definitions

### GenAI Input Contract

- Query
- Retrieved context (filtered)
- Metadata (user, policy)

### GenAI Output Contract

- Structured response (JSON)
- Confidence score
- Explanation trace

---

## 6. RAG Execution Contract

1. Accept user query
2. Retrieve context from:
   - semantic views
   - knowledge base
3. Apply policy filters (PEP)
4. Pass to LLM
5. Generate response

Rules:

- No raw data exposure
- No bypass of retrieval layer
- All responses must be grounded

---

## 7. Evaluation & Promotion

Loop:

Generate → Retrieve → Evaluate → Score → Promote

Requirements:

- Maintain test question bank
- Score accuracy and grounding
- Track performance over time

Promotion:

- Only high-confidence patterns move to production

---

## 8. Non-Functional Requirements

- Observability (logs, traces)
- Auditability (lineage + decisions)
- Security (RBAC / ABAC)
- Performance (latency thresholds)
- Cost control (model routing)

---

## 9. Definition of Done

A feature is complete when:

- Uses certified semantic views
- Passes policy enforcement
- Produces structured outputs
- Passes evaluation tests
- Is observable and logged
