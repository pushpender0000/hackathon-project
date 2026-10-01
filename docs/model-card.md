# Model Card: Google Gemini Flash Lite (Dispute Triage Specialization)

**Model Architecture**: Google Gemini Flash Lite (`gemini-3.5-flash-lite`)  
**Provider**: Google Cloud GenAI SDK (`google-genai==1.59.0`)  
**Pipeline Integration**: LangGraph Multi-Agent State Machine  
**Specialized Agent Roles**:
1. Worker 1: Dispute Classification Agent (`classifier_agent_node`)
2. Resolution Formatter: Customer Communication Synthesis Agent (`synthesis_agent_node`)
3. Evaluation Harness: DeepEval LLM-as-a-Judge (`GeminiDeepEvalLLM`)

---

## 1. Intended Use & Scope

### In-Scope Uses
- Structured dispute category classification from cardholder claim narratives (unauthorized charges, goods not received, duplicate billing, incorrect amounts, canceled recurring subscriptions).
- Natural language extraction of claimed monetary amounts and merchant details.
- Polite, objective synthesis of customer-facing dispute outcome letters citing verified synthetic network operating rules.
- Automated evaluation of triage explanations against retrieved policy context using DeepEval metrics.

### Explicit Out-of-Scope Uses
- Automated debiting or crediting of customer core banking ledgers (handled strictly by human operations or banking settlement gateways).
- Final legal adjudication of dispute contracts without human oversight.
- Financial credit underwriting or creditworthiness scoring.
- Processing unmasked Primary Account Numbers (PANs), CVVs, or cardholder PINs.

---

## 2. Model Capabilities & Configuration

| Parameter | Classifier Specification | Synthesis Specification | Evaluation Judge Specification |
| :--- | :--- | :--- | :--- |
| **Model Version** | `gemini-3.5-flash-lite` | `gemini-3.5-flash-lite` | `gemini-3.5-flash-lite` |
| **Sampling Temperature** | `0.0` (Deterministic) | `0.0` (Deterministic) | `0.0` (Deterministic) |
| **Response Format** | `application/json` | `application/json` | `text/plain` or JSON schema |
| **Schema Validation** | `GeminiDisputeClassificationOutput` | `GeminiSynthesisOutput` | DeepEval schema extraction |
| **ThinkingConfig** | Omitted (model-family detection: `gemini-3-lite`) | Omitted | Default |
| **Max Output Tokens** | `300` | `500` | `350` |
| **Calls Per Dispute** | $\le 1$ | $\le 1$ (0 if escalated) | Selective (0 on escalated runs) |

---

## 3. Operational Limits & Known Failure Modes

### 1. Synthetic Data Generalization
- **Limitation**: The model is tuned on synthetic benchmark dispute claims. Real-world cardholder language may contain regional idioms, multi-lingual statements, or emotional distress not represented in the synthetic corpus.
- **Mitigation**: Ambiguous, unclear, or non-standard claims trigger `ambiguous_inquiry` classification, immediately routing to human investigation under Precedence Tier 2.

### 2. Fraud Score Uncertainty
- **Limitation**: Generative language models have no deterministic capacity to compute statistical fraud probabilities.
- **Mitigation**: Fraud scoring is **completely decoupled** from the LLM. Fraud risk metrics (0 to 100) are computed deterministically in `src/fraud/scorer.py` using rule-based feature heuristics. The LLM is strictly prohibited from altering or guessing fraud scores.

### 3. Missing Data & Tool Hallucination
- **Limitation**: When core banking data or transaction records are missing, models tend to fabricate placeholder amounts or hallucinate merchant details.
- **Mitigation**: Hardcoded state checks in `src/decision/engine.py` intercept missing data at Precedence Tier 1. The synthesis agent is bypassed entirely, and `escalation_gate_node` emits formatted text with strict `"UNAVAILABLE"` markers.

### 4. Adversarial Prompt Injection
- **Limitation**: LLMs can be vulnerable to instruction override attacks (jailbreaks) embedded in user text.
- **Mitigation**: Pre-context quarantine in XML delimiters + regex signature filtering. Blocked attacks exit the graph before invoking the model or retrieving data.

---

## 4. Latency & Token Economics

- **Pricing Basis**: Official Google AI Developer Pricing (`ai.google.dev/pricing`)
- **Active Model**: `gemini-3.5-flash-lite` (Standard tier)
  - Input Token Rate: $0.30 per 1,000,000 tokens ($0.00000030 / token).
  - Output / Thinking Token Rate: $2.50 per 1,000,000 tokens ($0.00000250 / token).
  - Free tier available within Google AI Studio quota.
- **Published Gemini 3.x Flash Rates** (`gemini-3.8-flash` / `gemini-3.6-flash`):
  - Input Token Rate: $0.75 per 1,000,000 tokens ($0.00000075 / token).
  - Output / Thinking Token Rate: $3.75 per 1,000,000 tokens ($0.00000375 / token).
- **Gemini 2.5 Flash / Gemini 3.x Flash Lite Standard Rates**:
  - Input Token Rate: $0.30 per 1,000,000 tokens ($0.00000030 / token).
  - Output / Thinking Token Rate: $2.50 per 1,000,000 tokens ($0.00000250 / token).
- **Thinking Token Accounting Rule**:
  - Google GenAI SDK `usage_metadata` exposes `prompt_token_count`, `candidates_token_count`, and optionally `thoughts_token_count`.
  - `candidates_token_count` measures text generation tokens. `thoughts_token_count` represents reasoning tokens when returned by the API.
  - Thinking-token telemetry availability depends on the model and runtime API response. It is recorded when present; represented as null when absent.
  - Google bills thinking tokens at the same rate as output tokens (output pricing is inclusive). Thinking tokens are **never double-counted** in cost calculations.
  - `gemini-3.5-flash-lite` supports thinking_level per Google documentation. ThinkingConfig is currently omitted from requests (model-family `gemini-3-lite` detection) to maintain compatibility; `thoughts_token_count` is recorded from `usage_metadata` if returned.
- **Accounting & Billing Distinction**:
  - **Actual API Charge**: `null` (Billing/account charge data is not available from runtime telemetry).
  - **Estimated / Notional Commercial Cost**: Evaluated mathematically at the published Standard rate ($0.30/1M prompt, $2.50/1M completion).
- **Typical Case Consumption**:
  - Direct Escalation (Blocked Security / Missing Data): 0 Gemini tokens ($0.000000).
  - Triage with Synthesis: 700 - 800 tokens (~$0.0009 - $0.0020 notional cost per case).

---

## 5. Model Card Governance Sign-Off

- **Lead AI Engineer**: Verified Google GenAI SDK integration with zero third-party model fallbacks.
- **Compliance Lead**: Verified absence of PII in training/evaluation datasets and deterministic oversight on all money-movement recommendations.
