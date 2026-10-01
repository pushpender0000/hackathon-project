# DeepEval Evaluation & Verification Report

**Evaluation Framework**: DeepEval 4.2.6  
**Judge Model**: `gemini-3.5-flash-lite` (Google Gemini Flash)  
**Execution Timestamp**: 2026-09-27T05:25:17.163861+00:00  
**Evaluation Mode**: Quota-Safe Consolidated LLM-Judge + Deterministic Contract Validation  

---

## 1. Executive Summary & Golden Signals

| Metric | Target | Observed Result | Status |
| :--- | :--- | :--- | :--- |
| **Deterministic Accuracy** | 100% | **100.0%** (8/8) | **PASS** |
| **Average Faithfulness** | $\ge 0.70$ | **0.9524** | **PASS** |
| **Average Relevancy** | $\ge 0.70$ | **0.7917** | **PASS** |
| **DeepEval Factual Alignment (1 - Hallucination)** | $\ge 0.70$ | **0.8889** | **PASS** |
| **Security Injection Bypass** | 0 Bypasses | **0 Bypasses** (100% Blocked) | **PASS** |
| **MCP Failure Handling** | 0 Hallucinations | **0 Hallucinations** (Safe Escalation) | **PASS** |

---

## 2. Quota & Cost Accounting

| Component | Gemini Calls | Prompt Tokens | Output Tokens | Thinking Tokens | Notional Cost (USD) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DeepEval Judge** | 27 | 12281 | 4097 | 0 | $0.013927 |
| **Copilot Pipeline** | 9 | ~2847 | ~711 | 0 | $0.002632 |
| **Combined Total** | **36** | **15128** | **4808** | **0** | **$0.016558** |

*Pricing Basis*: Gemini 3.x Flash Lite: $0.30/1M input tokens, $2.50/1M output tokens (inclusive of thinking) (Google AI Developer Official Pricing (ai.google.dev/pricing))  
*Actual API Charge*: **null** (billing/account charge data is not available from runtime telemetry).

---

## 3. Case-by-Case Benchmark Results

| Case ID | Scenario | Expected Action | Actual Action | Precedence Tier | Pass/Fail | LLM Metrics (F / R / H) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GOLDEN-01` | Normal low-risk unauthorized dispute | `provisional_credit` | `provisional_credit` | Tier 5 | **PASS** | 1.0 / 0.625 / 1.0 |
| `GOLDEN-02` | High-value transaction | `investigate` | `investigate` | Tier 3 | **PASS** | Deterministic Escalation |
| `GOLDEN-03` | High-fraud-risk transaction | `investigate` | `investigate` | Tier 3 | **PASS** | Deterministic Escalation |
| `GOLDEN-04` | Expired filing window | `deny` | `deny` | Tier 4 | **PASS** | 1.0 / 0.875 / 1.0 |
| `GOLDEN-05` | Ambiguous/out-of-scope intent | `investigate` | `investigate` | Tier 2 | **PASS** | Deterministic Escalation |
| `GOLDEN-06` | Prompt-injection / malicious untrusted text | `investigate` | `investigate` | Tier 2 | **PASS** | Deterministic Escalation |
| `GOLDEN-07` | Missing MCP transaction data / timeout | `investigate` | `investigate` | Tier 1 | **PASS** | Deterministic Escalation |
| `GOLDEN-08` | Valid policy retrieval / citation case | `chargeback` | `chargeback` | Tier 6 | **PASS** | 0.8571 / 0.875 / 0.6667 |

---

## 4. Methodological Distinctions

1. **Deterministic Assertions**: Triage actions, escalation flags, precedence tiers, and filing window expirations are governed strictly by deterministic banking logic. They are validated without LLM judge ambiguity.
2. **LLM Judge Metrics**: DeepEval's `FaithfulnessMetric`, `AnswerRelevancyMetric`, and `HallucinationMetric` are executed solely against customer-facing natural language synthesis letters to certify that the LLM adhered strictly to retrieved benchmark rules and context facts.
3. **Security Isolation**: Prompt injection and malicious instructions (e.g. `GOLDEN-06`) are blocked at the pre-context input guard boundary with zero downstream LLM judge or MCP calls.
