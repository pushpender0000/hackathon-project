# Transaction Dispute & Fraud-Triage Copilot (BC-AAIE-HACK-03)

**Phase 3 Implementation**: Multi-Agent Agentic Core + Arize Phoenix / OpenTelemetry Observability + DeepEval Evaluation + Enterprise Governance Pack.

---

### Critical Disclaimers & Compliance Statements

1. **Synthetic Data Only**: All transactions, customer records, dispute claims, chargeback rules, and bank operating procedures contained in this repository are **100% synthetic benchmark data** created solely for the `BC-AAIE-HACK-03` hackathon. They do NOT contain real customer accounts, real PANs, proprietary bank data, or official card network regulations.
2. **Sole LLM Provider**: **Google Gemini is the sole LLM provider** across this entire system. No external commercial LLMs (OpenAI, Anthropic, Groq, Ollama, etc.) or external embedding APIs are utilized. Quota safety is strictly governed using thinking parameters (`thinking_level="minimal"` for Gemini 3.x; `thinking_budget=0` for Gemini 2.x) and hard token ceilings.
3. **No Docker / No External Database**: Operates entirely within a local Python virtual environment using SQLite checkpointers, ChromaDB vector search, and stdio MCP transport.

---

## Reproducible Command Reference

All system workflows are 100% reproducible using scripts and synthetic benchmark cases present in repository / ready for submission.

### 1. Execute Dispute Copilot CLI

Run the multi-agent dispute copilot on any synthetic dispute ID:

```powershell
# Fast-track low-risk dispute (provisional credit)
python run.py --dispute-id DISP-001

# High-value transaction ($2,499) -> Tier 3 human escalation
python run.py --dispute-id DISP-003

# Expired filing window (195 days) -> Tier 4 compliance denial
python run.py --dispute-id DISP-005

# Adversarial prompt injection -> Pre-context blocked at input guard
python run.py --dispute-id DISP-013

# Core banking MCP gateway timeout -> Tier 1 safe escalation with UNAVAILABLE fields
python run.py --dispute-id DISP-MCP-FAIL
```

### 2. Generate Live Observability Traces

Executes representative live cases to record OpenTelemetry spans and machine-generated transcripts:

```powershell
python scripts/generate_observability.py
```
*Generated Artifacts*:
- `traces/phoenix_spans.jsonl` (Genuine OpenTelemetry spans conforming to OpenInference semantic conventions)
- `logs/tool_calls.jsonl` (Audited record of MCP tool invocations with latency and status)
- `logs/agent_actions.jsonl` (Audited record of guardrail decisions: BLOCKED, MASKED, ALLOWED)

### 3. Generate Golden Signals & Dashboard Data

Parses Phoenix traces, tool call logs, and evaluation reports present in repository / ready for submission to derive genuine golden signals:

```powershell
python scripts/generate_golden_signals.py
```
*Generated Artifacts*:
- `reports/golden_signals.json` (Latency distributions, token totals, itemized costs, quality signals)
- `reports/dashboard_data.csv` (Per-run tabular metrics)

### 4. Render Observability Dashboard PNG

Generates a multi-panel visual dashboard directly from `reports/dashboard_data.csv`:

```powershell
python scripts/generate_dashboard.py
```
*Generated Artifact*:
- `reports/dashboard.png` (4-panel high-resolution dashboard: Latency breakdown, Token usage, Cost accounting, Governance scorecard)

### 5. Run DeepEval Evaluation Suite

Executes the DeepEval benchmark using Google Gemini as the sole judge model over the golden dataset:

```powershell
python scripts/run_evaluation.py
```
*Generated Artifacts*:
- `reports/evaluation_report.json`
- `reports/evaluation_report.md`

### 6. Run Complete Repository Pytest Suite

Executes all 54 contract, routing, loop termination, fraud scoring, RAG calibration, memory persistence, and schema tests:

```powershell
.venv\Scripts\pytest -v tests/
```

### 7. Run Evidence Integrity & Governance Audit Suite

Audits failure analysis resolvability, token accounting reconciliation, centralized pricing formulas, and secret hygiene:

```powershell
.venv\Scripts\python scripts/verify_evidence_integrity.py
```

---

## Golden Dataset & Evaluation Matrix

The evaluation suite operates on synthetic cases present in repository / ready for submission in `data/eval/golden_cases.json`:

| Case ID | Dispute ID | Scenario | Expected Action | Precedence Tier | Escalation Required | Gemini Expected |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GOLDEN-01` | `DISP-001` | Normal low-risk unauthorized dispute | `provisional_credit` | Tier 5 | No | Yes |
| `GOLDEN-02` | `DISP-003` | High-value transaction ($2,499.00) | `investigate` | Tier 3 | Yes | Yes (Classifier only) |
| `GOLDEN-03` | `DISP-010` | High-fraud-risk transaction (score $\ge 80$) | `investigate` | Tier 3 | Yes | Yes (Classifier only) |
| `GOLDEN-04` | `DISP-005` | Expired filing window (195 days $> 120$) | `deny` | Tier 4 | No | Yes |
| `GOLDEN-05` | `DISP-012` | Ambiguous / out-of-scope customer intent | `investigate` | Tier 2 | Yes | Yes (Classifier only) |
| `GOLDEN-06` | `DISP-013` | Prompt-injection / malicious instruction | `investigate` | Tier 2 | Yes | **No (0 calls, pre-context blocked)** |
| `GOLDEN-07` | `DISP-MCP-FAIL` | Missing MCP transaction data / 504 timeout | `investigate` | Tier 1 | Yes | **No (0 calls, Tier 1 safe escalation)** |
| `GOLDEN-08` | `DISP-007` | Valid policy retrieval / citation case | `chargeback` | Tier 6 | No | Yes |

---

## Governance & Compliance Pack

Comprehensive enterprise governance documentation is located in `docs/`:

- **[docs/failure-analysis.md](file:///c:/Users/jhapr/Downloads/virtusa-hack/docs/failure-analysis.md)**: 3 real, observed runtime failures with root cause, fixes, resolvable trace IDs, and log paths.
- **[docs/governance/risk-register.md](file:///c:/Users/jhapr/Downloads/virtusa-hack/docs/governance/risk-register.md)**: Comprehensive AI risk register covering adversarial injection, PII leakage, data integrity, and operational quota risks.
- **[docs/governance/model-card.md](file:///c:/Users/jhapr/Downloads/virtusa-hack/docs/governance/model-card.md)**: Specifications, limitations, and operational bounds for Google Gemini Flash.
- **[docs/governance/system-card.md](file:///c:/Users/jhapr/Downloads/virtusa-hack/docs/governance/system-card.md)**: Architectural blueprint, agent roles, LangGraph state topology, and MCP tool boundaries.
- **[docs/governance/compliance-mapping.md](file:///c:/Users/jhapr/Downloads/virtusa-hack/docs/governance/compliance-mapping.md)**: Engineering control mappings for EU AI Act, NIST AI RMF, and India DPDP Act.
- **[docs/governance/output-risk-classification.md](file:///c:/Users/jhapr/Downloads/virtusa-hack/docs/governance/output-risk-classification.md)**: Governance criteria for LOW, MEDIUM, and HIGH (Human Review Required) triage decisions.

---

## Repository Structure

```
virtusa-hack/
├── .env.example
├── .gitignore
├── README.md
├── pyproject.toml
├── run.py
│
├── data/
│   ├── synthetic_transactions.json
│   ├── synthetic_customers.json
│   ├── synthetic_disputes.json
│   ├── eval/
│   │   └── golden_cases.json
│   └── policy_corpus/
│       ├── synthetic_chargeback_rules.json
│       ├── synthetic_bank_triage_sop.md
│       └── synthetic_metadata.json
│
├── mcp_server/
│   ├── server.py
│   ├── schemas.py
│   └── data_access.py
│
├── src/
│   ├── config/settings.py
│   ├── schemas/gemini_schemas.py
│   ├── state.py
│   ├── graph.py
│   ├── agents/
│   │   ├── supervisor.py
│   │   ├── classifier_agent.py
│   │   ├── fraud_agent.py
│   │   ├── chargeback_retriever.py
│   │   └── synthesis_agent.py
│   ├── context/
│   │   └── context_manager.py
│   ├── memory/
│   │   ├── short_term.py
│   │   ├── long_term.py
│   │   └── tiered_memory.py
│   ├── decision/engine.py
│   ├── fraud/scorer.py
│   ├── guardrails/
│   │   ├── input_guard.py
│   │   ├── output_guard.py
│   │   └── action_logger.py
│   ├── observability/
│   │   ├── tracing.py
│   │   ├── pricing.py
│   │   └── evaluation.py
│   ├── tools/
│   │   ├── mcp_client.py
│   │   └── rag_tool.py
│   └── utils/
│       ├── masking.py
│       └── gemini_config.py
│
├── scripts/
│   ├── verify_environment.py
│   ├── generate_synthetic_data.py
│   ├── generate_observability.py
│   ├── generate_golden_signals.py
│   ├── generate_dashboard.py
│   ├── run_evaluation.py
│   └── verify_evidence_integrity.py
│
├── reports/
│   ├── golden_signals.json
│   ├── dashboard_data.csv
│   ├── dashboard.png
│   ├── evaluation_report.json
│   └── evaluation_report.md
│
├── traces/
│   └── phoenix_spans.jsonl
│
├── logs/
│   ├── mcp_transcript.jsonl
│   ├── tool_calls.jsonl
│   ├── agent_actions.jsonl
│   └── memory_test.log
│
├── docs/
│   ├── failure-analysis.md
│   ├── risk-register.md
│   ├── model-card.md
│   ├── system-card.md
│   ├── compliance.md
│   ├── output-risk.md
│   └── governance/
│       ├── risk-register.md
│       ├── model-card.md
│       ├── system-card.md
│       ├── compliance-mapping.md
│       └── output-risk-classification.md
│
└── tests/
    ├── test_decision_engine.py
    ├── test_fraud_scorer.py
    ├── test_graph_smoke.py
    ├── test_loops.py
    ├── test_memory_persistence.py
    ├── test_rag_retrieval.py
    ├── test_routing.py
    ├── test_schemas.py
    ├── test_token_accounting.py
    └── test_tool_contracts.py
```
