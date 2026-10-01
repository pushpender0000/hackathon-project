# Synthetic Bank Triage Standard Operating Procedure (SOP)

> [BENCHMARK SPECIFICATION]: This document contains synthetic benchmark dispute policies created exclusively for the BC-AAIE-HACK-03 hackathon. It does not represent official or proprietary card-network operating regulations.

## 1. Scope & Purpose
This document governs deterministic automated triage for cardholder dispute claims filed through the synthetic banking copilot system.

## 2. Synthetic Benchmark Triage Thresholds
The triage engine enforces the following deterministic decision rules:
- **Fast-Track Provisional Credit**: Allowed only when `disputed_amount <= $150.00` AND `fraud_score < 30.0` AND the dispute is filed within the network maximum filing days.
- **Mandatory High-Value Escalation**: Any transaction with `disputed_amount > $1,000.00` MUST be flagged for human investigation (`investigate`) regardless of customer history.
- **Mandatory High-Risk Fraud Escalation**: Any claim resulting in a deterministic `fraud_score >= 80.0` MUST be escalated to the Human Fraud Operations team.
- **Chronic Dispute Escalation**: Customers with `prior_disputes > 5` are disqualified from automated provisional credit and must undergo manual investigation.
- **Time-Limit Policy Expiration**: Claims exceeding `max_filing_days` (120 days for general fraud/merchandise, 90 days for duplicate billing) are automatically marked as `deny` unless high-value escalation takes precedence.

## 3. Mandatory Audit Logging
Every action must append an audit record to the machine-generated ledger citing the governing synthetic rule ID and decision rationale.
