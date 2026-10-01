"""
DeepEval Evaluation Framework with Gemini-Only Judge.

Provides:
1. GeminiDeepEvalLLM: Strict implementation of DeepEvalBaseLLM using Google GenAI SDK.
2. Quota-safe evaluation loop over committed synthetic golden cases.
3. Separation of deterministic pass/fail assertions from LLM-as-a-judge metrics.
4. Token and cost accounting derived from real Gemini usage metadata.
"""

import os
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from google import genai
from google.genai import types as genai_types
from google.genai import errors as genai_errors
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    FaithfulnessMetric,
    AnswerRelevancyMetric,
    HallucinationMetric,
)

from src.config.settings import get_settings
from src.observability.pricing import calculate_cost, PRICING_CONFIG
from src.observability.tracing import trace_span
from src.graph import create_dispute_graph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


class GeminiDeepEvalLLM(DeepEvalBaseLLM):
    """
    Certified DeepEval LLM wrapper for Google Gemini.
    Enforces quota safety, zero third-party fallbacks, and real token accounting.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        max_judge_budget: int = 15,
        *args,
        **kwargs,
    ):
        settings = get_settings()
        self.model_name = model_name or settings.gemini_model
        self.max_judge_budget = max_judge_budget
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.judge_call_count = 0
        self.prompt_tokens = 0
        self.output_tokens = 0
        self.thinking_tokens = 0
        super().__init__(model=self.model_name, *args, **kwargs)

    def load_model(self) -> Any:
        return self.client

    def get_model_name(self, *args, **kwargs) -> str:
        return self.model_name

    def _check_budget(self) -> None:
        if self.judge_call_count >= self.max_judge_budget:
            raise RuntimeError(
                f"DeepEval judge budget ceiling exceeded! Limit: {self.max_judge_budget} calls."
            )

    def generate(self, prompt: str, schema: Optional[Any] = None, *args, **kwargs) -> str:
        """Synchronous generation using Google GenAI SDK."""
        self._check_budget()
        self.judge_call_count += 1

        config = genai_types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=1024,
        )
        if schema is not None:
            config.response_mime_type = "application/json"
            try:
                config.response_schema = schema
            except Exception:
                pass

        with trace_span(
            name="deepeval.gemini_judge",
            span_kind="LLM",
            agent="deepeval_judge",
            attributes={"llm.model_name": self.model_name, "prompt_excerpt": prompt[:200]},
        ) as span:
            response = None
            for attempt in range(3):
                try:
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=prompt,
                        config=config,
                    )
                    break
                except (genai_errors.ServerError, genai_errors.APIError) as e:
                    if getattr(e, "code", 0) in (500, 502, 503, 504) or "503" in str(e):
                        if attempt < 2:
                            import time
                            time.sleep(2.5 * (attempt + 1))
                            continue
                    raise

            if response and response.usage_metadata:
                p = getattr(response.usage_metadata, "prompt_token_count", None)
                o = getattr(response.usage_metadata, "candidates_token_count", None)
                th = getattr(response.usage_metadata, "thoughts_token_count", None)
                tot = getattr(response.usage_metadata, "total_token_count", None)
                if p is not None:
                    self.prompt_tokens += p
                    span.set_attribute("gen_ai.usage.input_tokens", p)
                    span.set_attribute("llm.token_count.prompt", p)
                if o is not None:
                    self.output_tokens += o
                    span.set_attribute("gen_ai.usage.output_tokens", o)
                    span.set_attribute("llm.token_count.completion", o)
                if th is not None:
                    self.thinking_tokens += th
                    span.set_attribute("gen_ai.usage.thinking_tokens", th)
                    span.set_attribute("llm.token_count.thinking", th)
                if tot is not None:
                    span.set_attribute("gen_ai.usage.total_tokens", tot)
                    span.set_attribute("llm.token_count.total", tot)
                span.set_attribute("gen_ai.system", "Google Gemini")
                span.set_attribute("gen_ai.request.model", self.model_name)

            return (response.text if response else "") or ""

    async def a_generate(self, prompt: str, schema: Optional[Any] = None, *args, **kwargs) -> str:
        """Asynchronous generation using Google GenAI SDK with transient retry."""
        self._check_budget()
        self.judge_call_count += 1

        config = genai_types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=1024,
        )
        if schema is not None:
            config.response_mime_type = "application/json"
            try:
                config.response_schema = schema
            except Exception:
                pass

        with trace_span(
            name="deepeval.gemini_judge",
            span_kind="LLM",
            agent="deepeval_judge",
            attributes={"llm.model_name": self.model_name, "prompt_excerpt": prompt[:200]},
        ) as span:
            response = None
            for attempt in range(3):
                try:
                    response = await self.client.aio.models.generate_content(
                        model=self.model_name,
                        contents=prompt,
                        config=config,
                    )
                    break
                except (genai_errors.ServerError, genai_errors.APIError) as e:
                    if getattr(e, "code", 0) in (500, 502, 503, 504) or "503" in str(e):
                        if attempt < 2:
                            await asyncio.sleep(2.5 * (attempt + 1))
                            continue
                    raise

            if response and response.usage_metadata:
                p = getattr(response.usage_metadata, "prompt_token_count", None)
                o = getattr(response.usage_metadata, "candidates_token_count", None)
                th = getattr(response.usage_metadata, "thoughts_token_count", None)
                tot = getattr(response.usage_metadata, "total_token_count", None)
                if p is not None:
                    self.prompt_tokens += p
                    span.set_attribute("gen_ai.usage.input_tokens", p)
                    span.set_attribute("llm.token_count.prompt", p)
                if o is not None:
                    self.output_tokens += o
                    span.set_attribute("gen_ai.usage.output_tokens", o)
                    span.set_attribute("llm.token_count.completion", o)
                if th is not None:
                    self.thinking_tokens += th
                    span.set_attribute("gen_ai.usage.thinking_tokens", th)
                    span.set_attribute("llm.token_count.thinking", th)
                if tot is not None:
                    span.set_attribute("gen_ai.usage.total_tokens", tot)
                    span.set_attribute("llm.token_count.total", tot)
                span.set_attribute("gen_ai.system", "Google Gemini")
                span.set_attribute("gen_ai.request.model", self.model_name)

            await asyncio.sleep(1.0)
            return (response.text if response else "") or ""




async def run_single_evaluation_case(
    case_def: Dict[str, Any],
    judge_llm: GeminiDeepEvalLLM,
    saver: AsyncSqliteSaver,
) -> Dict[str, Any]:
    """
    Executes a single golden case through the LangGraph copilot, performs deterministic assertions,
    and selectively invokes DeepEval metrics if the case produces an LLM customer resolution.
    """
    settings = get_settings()
    dispute_id = case_def["dispute_id"]
    thread_id = f"eval-thread-{dispute_id}-{datetime.now(timezone.utc).strftime('%H%M%S')}"

    initial_state = {
        "raw_customer_input": case_def["claim_text"],
        "quarantined_text": "",
        "customer_id": case_def["customer_id"],
        "transaction_id": case_def["transaction_id"],
        "session_id": f"eval-session-{dispute_id}",
        "transaction": None,
        "customer_history": None,
        "dispute_category": None,
        "customer_intent": None,
        "extracted_amount": None,
        "claim_summary": None,
        "fraud_score": None,
        "risk_level": None,
        "top_risk_factors": [],
        "fraud_features": {},
        "selected_rule_id": None,
        "rule_title": None,
        "max_filing_days": None,
        "evidence_required": [],
        "synthetic_citation": None,
        "retrieval_score": None,
        "policy_retrieval_failed": False,
        "recommended_action": None,
        "escalation_required": False,
        "escalation_reason": None,
        "precedence_level": None,
        "iteration_count": 0,
        "execution_errors": [],
        "data_unavailable": False,
        "guardrail_flags": [],
        "next_worker": None,
        "gemini_call_count": 0,
        "cumulative_tokens": 0,
        "synthesis_result": None,
        "final_response": None,
        "run_id": f"eval-run-{dispute_id}",
        "timestamps": {"started_at": datetime.now(timezone.utc).isoformat()},
        "audit_metadata": {
            "dispute_id": dispute_id,
            "days_elapsed": case_def.get("days_elapsed", 0),
            "expected_action": case_def.get("expected_action"),
            "expected_rule": case_def.get("expected_rule"),
        },
    }

    app = create_dispute_graph(checkpointer=saver)
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}

    with trace_span(
        name="graph.run",
        span_kind="CHAIN",
        agent="dispute_copilot",
        attributes={
            "dispute.id": dispute_id,
            "eval.case_id": case_def["case_id"],
            "eval.scenario": case_def["scenario"],
        },
    ):
        final_state = await app.ainvoke(initial_state, config=config)

    # 1. Deterministic Pass/Fail Assertions
    action_match = final_state.get("recommended_action") == case_def["expected_action"]
    escalation_match = bool(final_state.get("escalation_required")) == bool(case_def["escalation_expected"])
    precedence_match = final_state.get("precedence_level") == case_def["precedence_tier"]

    # Rule match check: if expected_rule is defined, verify match
    rule_match = True
    if case_def.get("expected_rule"):
        rule_match = final_state.get("selected_rule_id") == case_def["expected_rule"]

    deterministic_pass = action_match and escalation_match and precedence_match and rule_match

    case_result = {
        "case_id": case_def["case_id"],
        "dispute_id": dispute_id,
        "scenario": case_def["scenario"],
        "claim_text": case_def["claim_text"],
        "expected_action": case_def["expected_action"],
        "actual_action": final_state.get("recommended_action"),
        "expected_escalation": case_def["escalation_expected"],
        "actual_escalation": bool(final_state.get("escalation_required")),
        "expected_precedence": case_def["precedence_tier"],
        "actual_precedence": final_state.get("precedence_level"),
        "selected_rule_id": final_state.get("selected_rule_id"),
        "copilot_gemini_calls": final_state.get("gemini_call_count", 0),
        "copilot_tokens": final_state.get("cumulative_tokens", 0),
        "guardrail_flags": final_state.get("guardrail_flags", []),
        "deterministic_pass": deterministic_pass,
        "evaluation_metrics": {},
    }

    # 2. DeepEval LLM-as-a-Judge Evaluation
    # Only run LLM judge on cases that generate natural language synthesis customer communication
    # (Quota-safe design: avoids evaluating deterministic escalation receipts or blocked attacks)
    synthesis_text = final_state.get("synthesis_result")
    if synthesis_text and not final_state.get("escalation_required") and case_def.get("gemini_call_expected"):
        context = [
            f"Dispute Category: {final_state.get('dispute_category')}",
            f"Recommended Action: {final_state.get('recommended_action')}",
            f"Policy Rule: {final_state.get('selected_rule_id')} - {final_state.get('rule_title')}",
            f"Filing Window: {final_state.get('max_filing_days')} days",
            f"Required Evidence: {', '.join(final_state.get('evidence_required', []))}",
            f"Synthetic Regulation: {final_state.get('synthetic_citation')}",
        ]
        retrieval_context = [
            f"Dispute Category: {final_state.get('dispute_category')}",
            f"Recommended Action: {final_state.get('recommended_action')}",
            f"Policy Rule: {final_state.get('selected_rule_id')} - {final_state.get('rule_title')}",
            f"Filing Window: {final_state.get('max_filing_days')} days",
            f"Required Evidence: {', '.join(final_state.get('evidence_required', []))}",
            f"Synthetic Regulation: {final_state.get('synthetic_citation')}",
            f"Benchmark Policy Description: {final_state.get('rule_title')}",
        ]

        test_case = LLMTestCase(
            input=case_def["claim_text"],
            actual_output=synthesis_text,
            context=context,
            retrieval_context=retrieval_context,
        )

        # Measure DeepEval Faithfulness
        faith_metric = FaithfulnessMetric(threshold=0.5, model=judge_llm)
        await faith_metric.a_measure(test_case)

        # Measure DeepEval Answer Relevancy
        relevancy_metric = AnswerRelevancyMetric(threshold=0.5, model=judge_llm)
        await relevancy_metric.a_measure(test_case)

        # Measure DeepEval Hallucination
        hallucination_metric = HallucinationMetric(threshold=0.5, model=judge_llm)
        await hallucination_metric.a_measure(test_case)

        case_result["evaluation_metrics"] = {
            "faithfulness": {
                "score": round(float(faith_metric.score), 4),
                "passed": faith_metric.is_successful(),
                "reason": faith_metric.reason,
            },
            "relevance": {
                "score": round(float(relevancy_metric.score), 4),
                "passed": relevancy_metric.is_successful(),
                "reason": relevancy_metric.reason,
            },
            "hallucination": {
                "score": round(float(hallucination_metric.score), 4),
                "passed": hallucination_metric.is_successful(),
                "reason": hallucination_metric.reason,
            },
        }

    return case_result
