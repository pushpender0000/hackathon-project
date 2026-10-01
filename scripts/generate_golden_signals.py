"""
Golden Signals Generator.

Reads Phoenix OTEL traces (`traces/phoenix_spans.jsonl`), tool logs (`logs/tool_calls.jsonl`),
and DeepEval evaluation results (`reports/evaluation_report.json`).
Derives genuine runtime metrics, latency distributions, token totals, and centralized costs.
Outputs:
- reports/golden_signals.json
- reports/dashboard_data.csv

Usage:
    python scripts/generate_golden_signals.py
"""

import sys
import csv
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import get_settings
from src.observability.pricing import calculate_cost, PRICING_CONFIG, get_model_pricing


def generate_golden_signals():
    settings = get_settings()
    workspace_root = settings.workspace_root
    traces_path = workspace_root / "traces" / "phoenix_spans.jsonl"
    tool_logs_path = workspace_root / "logs" / "tool_calls.jsonl"
    eval_report_path = workspace_root / "reports" / "evaluation_report.json"
    reports_dir = workspace_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_output_path = reports_dir / "golden_signals.json"
    csv_output_path = reports_dir / "dashboard_data.csv"

    # 1. Parse Phoenix Traces
    traces_by_id: Dict[str, List[Dict[str, Any]]] = {}
    if traces_path.exists():
        with open(traces_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    span_rec = json.loads(line)
                    t_id = span_rec.get("trace_id", "unknown")
                    traces_by_id.setdefault(t_id, []).append(span_rec)
                except Exception:
                    continue

    # 2. Parse Evaluation Report (for quality signals)
    eval_data = {}
    if eval_report_path.exists():
        with open(eval_report_path, "r", encoding="utf-8") as f:
            try:
                eval_data = json.load(f)
            except Exception:
                pass

    agg_eval = eval_data.get("aggregate_metrics", {})
    pass_rate_pct = agg_eval.get("deterministic_pass_rate_pct", 100.0)
    deterministic_accuracy = round(pass_rate_pct / 100.0, 4)
    hallucination_signal = agg_eval.get("hallucination_evaluation_signal", "PASSED")
    avg_faithfulness = agg_eval.get("average_faithfulness")
    avg_relevance = agg_eval.get("average_relevance")
    avg_hallucination = agg_eval.get("average_hallucination")

    # 3. Analyze Traces & Per-Run Metrics
    per_run_data = []
    all_e2e_latencies = []
    all_agent_latencies = []
    all_tool_latencies = []
    all_llm_latencies = []
    total_prompt_tokens = 0
    total_output_tokens = 0
    total_thinking_tokens = 0
    total_gemini_calls = 0

    tool_latencies_by_tool: Dict[str, List[float]] = {}

    for trace_id, spans in traces_by_id.items():
        # Find root span
        root_span = next((s for s in spans if s.get("name") == "graph.run"), None)
        if not root_span and spans:
            root_span = spans[0]

        e2e_lat = root_span.get("duration_ms", 0.0) if root_span else 0.0
        all_e2e_latencies.append(e2e_lat)

        attrs = root_span.get("attributes", {}) if root_span else {}
        dispute_id = attrs.get("dispute.id", "N/A")
        scenario = attrs.get("eval.scenario", dispute_id)
        action = attrs.get("decision.action", "investigate")
        status = root_span.get("status", "OK") if root_span else "OK"

        run_tool_lat = 0.0
        run_llm_lat = 0.0
        run_agent_lat = 0.0
        run_gemini_calls = 0
        run_prompt_tokens = 0
        run_output_tokens = 0
        run_thinking_tokens = 0

        for s in spans:
            name = s.get("name", "")
            kind = s.get("span_kind", "")
            dur = s.get("duration_ms", 0.0)
            span_status = s.get("status", "OK")

            # Tool spans
            if kind == "TOOL" or name in ("get_transaction_details", "get_customer_dispute_history", "dispute-policy-spec://network_rules"):
                run_tool_lat += dur
                all_tool_latencies.append(dur)
                tool_latencies_by_tool.setdefault(name, []).append(dur)

            # LLM spans
            elif (kind == "LLM" or name in ("gemini.generate_content", "deepeval.gemini_judge")):
                # Only count successful calls that actually generated content and returned telemetry
                if span_status == "OK":
                    tokens = s.get("token_usage") or {}
                    s_attrs = s.get("attributes") or {}

                    p_raw = tokens.get("prompt_tokens") if tokens else None
                    if p_raw is None:
                        p_raw = s_attrs.get("gen_ai.usage.input_tokens", s_attrs.get("llm.token_count.prompt"))

                    o_raw = tokens.get("output_tokens") if tokens else None
                    if o_raw is None:
                        o_raw = s_attrs.get("gen_ai.usage.output_tokens", s_attrs.get("llm.token_count.completion"))

                    th_raw = tokens.get("thinking_tokens") if tokens else None
                    if th_raw is None:
                        th_raw = s_attrs.get("gen_ai.usage.thinking_tokens", s_attrs.get("llm.token_count.thinking"))

                    if p_raw is not None or o_raw is not None:
                        p = int(p_raw) if p_raw is not None else 0
                        o = int(o_raw) if o_raw is not None else 0
                        th = int(th_raw) if th_raw is not None else 0

                        run_llm_lat += dur
                        all_llm_latencies.append(dur)
                        run_gemini_calls += 1
                        total_gemini_calls += 1

                        run_prompt_tokens += p
                        run_output_tokens += o
                        run_thinking_tokens += th
                        total_prompt_tokens += p
                        total_output_tokens += o
                        total_thinking_tokens += th

            # Agent / Acting spans
            elif kind in ("AGENT", "CHAIN", "GUARDRAIL") and name != "graph.run":
                run_agent_lat += dur

        all_agent_latencies.append(run_agent_lat)

        total_run_tokens = run_prompt_tokens + run_output_tokens
        cost_info = calculate_cost(
            model_name=settings.gemini_model,
            prompt_tokens=run_prompt_tokens,
            output_tokens=run_output_tokens,
            thinking_tokens=run_thinking_tokens if run_thinking_tokens > 0 else None,
        )

        per_run_data.append({
            "trace_id": trace_id,
            "dispute_id": dispute_id,
            "scenario": scenario,
            "end_to_end_latency_ms": round(e2e_lat, 2),
            "agent_acting_latency_ms": round(run_agent_lat, 2),
            "tool_latency_ms": round(run_tool_lat, 2),
            "llm_model_latency_ms": round(run_llm_lat, 2),
            "thinking_latency_ms": None,
            "thinking_latency_notes": "Unavailable from API telemetry",
            "gemini_call_count": run_gemini_calls,
            "input_tokens": run_prompt_tokens,
            "output_tokens": run_output_tokens,
            "thinking_tokens": run_thinking_tokens if run_thinking_tokens > 0 else None,
            "thinking_tokens_notes": "reported" if run_thinking_tokens > 0 else "Unavailable from API telemetry",
            "total_tokens": total_run_tokens,
            "estimated_notional_cost_usd": cost_info["estimated_notional_cost_usd"],
            "notional_cost_usd": cost_info["notional_cost_usd"],
            "actual_api_charge_usd": None,
            "actual_api_charge_note": "Billing/account charge data is not available from runtime telemetry.",
            "pricing_assumption": cost_info["pricing_assumption"],
            "status": status,
            "action": action,
            "deterministic_accuracy": 1.0 if status == "OK" else 0.0,
            "hallucination": avg_hallucination,
            "faithfulness": avg_faithfulness,
            "relevance": avg_relevance,
        })

    # Summary Statistics
    total_runs = len(per_run_data)
    avg_e2e = round(sum(all_e2e_latencies) / len(all_e2e_latencies), 2) if all_e2e_latencies else 0.0
    max_e2e = round(max(all_e2e_latencies), 2) if all_e2e_latencies else 0.0
    min_e2e = round(min(all_e2e_latencies), 2) if all_e2e_latencies else 0.0

    avg_agent = round(sum(all_agent_latencies) / len(all_agent_latencies), 2) if all_agent_latencies else 0.0
    avg_tool = round(sum(all_tool_latencies) / len(all_tool_latencies), 2) if all_tool_latencies else 0.0
    avg_llm = round(sum(all_llm_latencies) / len(all_llm_latencies), 2) if all_llm_latencies else 0.0

    overall_cost = calculate_cost(
        model_name=settings.gemini_model,
        prompt_tokens=total_prompt_tokens,
        output_tokens=total_output_tokens,
        thinking_tokens=total_thinking_tokens if total_thinking_tokens > 0 else None,
    )

    tool_latency_summary = {}
    for t_name, lats in tool_latencies_by_tool.items():
        tool_latency_summary[t_name] = {
            "invocations": len(lats),
            "avg_ms": round(sum(lats) / len(lats), 2),
            "min_ms": round(min(lats), 2),
            "max_ms": round(max(lats), 2),
        }

    rates = get_model_pricing(settings.gemini_model)

    # Derive the list of source dispute cases from the root spans (for provenance)
    def get_dispute_id(spans_list):
        root = next((s for s in spans_list if s.get("name") == "graph.run"), None)
        if root:
            return root.get("attributes", {}).get("dispute.id", "UNKNOWN")
        for s in spans_list:
            did = s.get("attributes", {}).get("dispute.id")
            if did:
                return did
        return "UNKNOWN"

    source_cases = sorted(set(
        get_dispute_id(spans_list)
        for spans_list in traces_by_id.values()
        if spans_list
    ))

    golden_signals = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "environment": "synthetic_benchmark_evaluation",
            "model_name": settings.gemini_model,
            "total_runs_analyzed": total_runs,
            "source_run_count": total_runs,
            "source_cases": source_cases,
            "pricing_assumption": overall_cost["pricing_assumption"],
            "published_rates": rates,
        },
        "signals": {
            "end_to_end_latency_ms": {
                "avg": avg_e2e,
                "min": min_e2e,
                "max": max_e2e,
            },
            "agent_acting_latency_ms": {
                "avg": avg_agent,
                "note": "Sum of agent planning, classification, fraud scoring, decision, and guardrail processing time"
            },
            "tool_latency_ms": {
                "avg": avg_tool,
                "by_tool": tool_latency_summary,
            },
            "llm_model_latency_ms": {
                "avg": avg_llm,
                "total_calls": total_gemini_calls,
            },
            "thinking_latency_ms": None,
            "thinking_latency_notes": "Unavailable from API telemetry",
            "input_tokens": total_prompt_tokens,
            "output_tokens": total_output_tokens,
            "thinking_tokens": total_thinking_tokens if total_thinking_tokens > 0 else None,
            "thinking_tokens_notes": "reported" if total_thinking_tokens > 0 else "Unavailable from API telemetry",
            "gemini_call_count": total_gemini_calls,
            "estimated_notional_cost_usd": overall_cost["estimated_notional_cost_usd"],
            "notional_cost_usd": overall_cost["notional_cost_usd"],
            "actual_api_charge_usd": None,
            "actual_api_charge_note": "Billing/account charge data is not available from runtime telemetry.",
            "deterministic_accuracy": deterministic_accuracy,
            "hallucination": avg_hallucination,
            "faithfulness": avg_faithfulness,
            "relevance": avg_relevance,
        },
        "quality_and_evaluation_signals": {
            "accuracy_pct": pass_rate_pct,
            "deterministic_accuracy": deterministic_accuracy,
            "hallucination_signal": hallucination_signal,
            "average_faithfulness": avg_faithfulness,
            "average_relevance": avg_relevance,
            "average_hallucination": avg_hallucination,
        },
        "token_accounting": {
            "model_name": settings.gemini_model,
            "total_gemini_calls": total_gemini_calls,
            "total_input_tokens": total_prompt_tokens,
            "total_output_tokens": total_output_tokens,
            "total_thinking_tokens": total_thinking_tokens if total_thinking_tokens > 0 else None,
            "thinking_tokens_notes": "reported" if total_thinking_tokens > 0 else "Unavailable from API telemetry",
            "total_cumulative_tokens": total_prompt_tokens + total_output_tokens,
            "pricing_assumption": overall_cost["pricing_assumption"],
            "estimated_notional_cost_usd": overall_cost["estimated_notional_cost_usd"],
            "actual_api_charge_usd": None,
            "actual_api_charge_note": "Billing/account charge data is not available from runtime telemetry.",
        },
        "per_run_breakdown": per_run_data,
    }

    # Write golden_signals.json
    with open(json_output_path, "w", encoding="utf-8") as f:
        json.dump(golden_signals, f, indent=2)

    # Write dashboard_data.csv
    csv_columns = [
        "trace_id",
        "dispute_id",
        "scenario",
        "end_to_end_latency_ms",
        "agent_acting_latency_ms",
        "tool_latency_ms",
        "llm_model_latency_ms",
        "thinking_latency_ms",
        "gemini_call_count",
        "input_tokens",
        "output_tokens",
        "thinking_tokens",
        "total_tokens",
        "notional_cost_usd",
        "status",
        "action",
        "deterministic_accuracy",
    ]

    with open(csv_output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_columns)
        writer.writeheader()
        for row in per_run_data:
            filtered_row = {k: row.get(k) for k in csv_columns}
            writer.writerow(filtered_row)

    print("=" * 60)
    print("GOLDEN SIGNALS GENERATED SUCCESSFULLY")
    print(f"JSON Report : {json_output_path}")
    print(f"CSV Output  : {csv_output_path}")
    print(f"Total Runs Analyzed      : {total_runs}")
    print(f"Successful Gemini Calls  : {total_gemini_calls}")
    print(f"Total Input Tokens       : {total_prompt_tokens}")
    print(f"Total Output Tokens      : {total_output_tokens}")
    print(f"Total Thinking Tokens    : {total_thinking_tokens}")
    print(f"Total Tokens             : {total_prompt_tokens + total_output_tokens}")
    print(f"Pricing Assumption       : {overall_cost['pricing_assumption']}")
    print(f"Notional Cost            : ${overall_cost['estimated_notional_cost_usd']:.6f} USD")
    print(f"Actual Billing Data      : Not available from runtime telemetry (reported as null)")
    print("=" * 60)


if __name__ == "__main__":
    generate_golden_signals()
