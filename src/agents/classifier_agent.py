"""
Worker 1: Dispute Classification Agent.

Performs structured dispute classification using Google Gemini.
Executes exactly ONE generation request under normal operation.
Instruments execution with OpenTelemetry spans and token telemetry.
"""

from typing import Any, Dict, Optional
from google import genai
from google.genai import errors as genai_errors
from openinference.semconv.trace import SpanAttributes

from src.config.settings import get_settings
from src.schemas.gemini_schemas import GeminiDisputeClassificationOutput
from src.utils.gemini_config import build_generate_content_config
from src.observability.tracing import trace_span


CLASSIFIER_PROMPT = """You are a certified banking dispute intake specialist.
Analyze the quarantined cardholder claim below in the context of the basic transaction record.

Transaction ID: {tx_id}
Merchant: {merchant}
Amount: ${amount:.2f}

{quarantined_claim}

Classify into exactly one dispute category:
- fraudulent_transaction: unauthorized charge, stolen card, card-absent fraud
- merchandise_not_received: goods or services paid for but never delivered, canceled travel/events where merchant refused refund
- duplicate_processing: multiple charges for the same transaction
- incorrect_amount: billed amount differs from authorized receipt
- canceled_service: recurring subscription or membership billed after cancellation
- ambiguous_inquiry: unclear claim, general inquiry, or missing dispute details

Extract the customer intent, disputed amount if explicitly stated, a concise claim summary, and set requires_human_triage to true only if the customer's claim is completely ambiguous or incomprehensible."""


async def classifier_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node for Worker 1: Gemini Dispute Classification."""
    with trace_span(
        name="classifier",
        span_kind="AGENT",
        agent="classifier",
        attributes={"agent.role": "dispute_classifier"},
    ) as agent_span:
        settings = get_settings()

        tx = state.get("transaction") or {}
        tx_id = tx.get("transaction_id", state.get("transaction_id", "N/A"))
        merchant = tx.get("merchant", "Unknown Merchant")
        amount = float(tx.get("amount", 0.0))
        quarantined = state.get("quarantined_text") or state.get("raw_customer_input", "")

        # Safety check on cumulative token budget
        current_tokens = state.get("cumulative_tokens", 0)
        if current_tokens >= settings.max_cumulative_tokens:
            agent_span.set_attribute("decision.interrupted", "token_budget_exceeded")
            return {
                "dispute_category": "ambiguous_inquiry",
                "customer_intent": "Budget ceiling reached; deferred to human triage",
                "claim_summary": "Token ceiling exceeded",
                "escalation_required": True,
                "escalation_reason": "Cumulative token safety ceiling reached before classification",
                "recommended_action": "investigate",
                "precedence_level": 1,
                "execution_errors": state.get("execution_errors", []) + ["Cumulative token budget exceeded"],
            }

        if not settings.gemini_api_key:
            agent_span.set_attribute("decision.interrupted", "missing_api_key")
            return {
                "dispute_category": "ambiguous_inquiry",
                "customer_intent": "Gemini API key missing; manual triage required",
                "claim_summary": "Manual intake fallback",
                "escalation_required": True,
                "escalation_reason": "GEMINI_API_KEY not configured",
                "recommended_action": "investigate",
                "precedence_level": 1,
            }

        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = CLASSIFIER_PROMPT.format(
            tx_id=tx_id,
            merchant=merchant,
            amount=amount,
            quarantined_claim=quarantined,
        )

        config = build_generate_content_config(
            model_name=settings.gemini_model,
            temperature=0.0,
            max_output_tokens=settings.classifier_max_output_tokens,
            response_mime_type="application/json",
            response_schema=GeminiDisputeClassificationOutput,
            thinking_level=settings.gemini_thinking_level,
            thinking_budget=settings.gemini_thinking_budget,
        )

        # Attempt generation with bounded retry for transient 5xx/timeout
        last_error: Optional[str] = None
        response = None

        with trace_span(
            name="gemini.generate_content",
            span_kind="LLM",
            agent="classifier",
            attributes={
                "llm.model_name": settings.gemini_model,
                SpanAttributes.INPUT_VALUE: prompt[:500],
            },
        ) as llm_span:
            import asyncio
            for attempt in range(2):
                try:
                    response = await asyncio.wait_for(
                        client.aio.models.generate_content(
                            model=settings.gemini_model,
                            contents=prompt,
                            config=config,
                        ),
                        timeout=25.0,
                    )
                    break
                except asyncio.TimeoutError:
                    last_error = "Gemini API request timed out after 25s"
                    if attempt == 0:
                        await asyncio.sleep(2.0)
                        continue
                except genai_errors.APIError as e:
                    if getattr(e, "code", 0) == 429:
                        # 429: Zero retries per architecture specification
                        llm_span.set_status(Status(StatusCode.ERROR, f"Gemini 429 Rate Limit: {str(e)}"))
                        return {
                            "dispute_category": "ambiguous_inquiry",
                            "escalation_required": True,
                            "escalation_reason": f"Gemini 429 Rate Limit encountered: {str(e)}",
                            "recommended_action": "investigate",
                            "precedence_level": 1,
                            "execution_errors": state.get("execution_errors", []) + ["Gemini 429 Rate Limit"],
                        }
                    last_error = f"API Error: {str(e)}"
                    if attempt == 0:
                        await asyncio.sleep(2.0)
                        continue  # 1 retry for transient errors
                except Exception as e:
                    last_error = f"Generation Error: {str(e)}"
                    if attempt == 0:
                        await asyncio.sleep(2.0)
                        continue

            if response and response.usage_metadata:
                usage = response.usage_metadata
                p_tokens = getattr(usage, "prompt_token_count", None)
                o_tokens = getattr(usage, "candidates_token_count", None)
                th_tokens = getattr(usage, "thoughts_token_count", None)
                tot_tokens = getattr(usage, "total_token_count", None)

                llm_span.set_attribute("gen_ai.system", "Google Gemini")
                llm_span.set_attribute("gen_ai.request.model", settings.gemini_model)
                if p_tokens is not None:
                    llm_span.set_attribute("gen_ai.usage.input_tokens", p_tokens)
                    llm_span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_PROMPT, p_tokens)
                    llm_span.set_attribute("llm.token_count.prompt", p_tokens)
                if o_tokens is not None:
                    llm_span.set_attribute("gen_ai.usage.output_tokens", o_tokens)
                    llm_span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, o_tokens)
                    llm_span.set_attribute("llm.token_count.completion", o_tokens)
                if tot_tokens is not None:
                    llm_span.set_attribute("gen_ai.usage.total_tokens", tot_tokens)
                    llm_span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_TOTAL, tot_tokens)
                    llm_span.set_attribute("llm.token_count.total", tot_tokens)
                if th_tokens is not None:
                    llm_span.set_attribute("gen_ai.usage.thinking_tokens", th_tokens)
                    llm_span.set_attribute("llm.token_count.thinking", th_tokens)

        if not response or not response.parsed:
            return {
                "dispute_category": "ambiguous_inquiry",
                "customer_intent": "LLM classification failed",
                "claim_summary": "Unparseable customer statement",
                "escalation_required": True,
                "escalation_reason": f"Classifier failed: {last_error}",
                "recommended_action": "investigate",
                "precedence_level": 1,
                "execution_errors": state.get("execution_errors", []) + [str(last_error)],
            }

        parsed: GeminiDisputeClassificationOutput = response.parsed

        # Telemetry tracking
        usage = response.usage_metadata
        total_tokens = getattr(usage, "total_token_count", 0)

        call_count = state.get("gemini_call_count", 0) + 1
        new_cumulative = current_tokens + total_tokens

        agent_span.set_attribute("dispute.category", parsed.dispute_category)
        agent_span.set_attribute("dispute.intent", parsed.customer_intent)

        updates: Dict[str, Any] = {
            "dispute_category": parsed.dispute_category,
            "customer_intent": parsed.customer_intent,
            "extracted_amount": parsed.extracted_amount,
            "claim_summary": parsed.claim_summary,
            "requires_human_triage": parsed.requires_human_triage,
            "gemini_call_count": call_count,
            "cumulative_tokens": new_cumulative,
        }

        return updates
