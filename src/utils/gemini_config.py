"""
Helper module for model-specific Google Gemini generation configurations.

Handles differentiation between Gemini model families:
1. Gemini 3.x thinking family (e.g. gemini-3.6-flash, gemini-3.8-flash):
   - Uses `thinking_level` (default 'low' for quota-conscious triage).
   - Does NOT set `thinking_budget`.
   - 'low' minimizes thought generation but does NOT guarantee zero thinking tokens.
2. Gemini 2.x / 2.5 family (e.g. gemini-2.5-flash, gemini-2.0-flash):
   - Uses `thinking_budget` (default 0 for quota safety).
   - Does NOT set `thinking_level`.
3. Gemini 3.x lite / non-thinking family (e.g. gemini-3.5-flash-lite, gemini-3.1-flash-lite):
   - Does NOT support ThinkingConfig at all (returns 400 INVALID_ARGUMENT if passed).
   - thinking_config is omitted entirely from GenerateContentConfig.
"""

from typing import Any, Dict, Optional
from google.genai import types


# Models known to NOT support ThinkingConfig (return 400 if thinking_config is set)
_LITE_MODELS = {
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest",
}


def detect_model_family(model_name: str) -> str:
    """
    Classifies a Gemini model into its architectural family.
    Returns: 'gemini-3' | 'gemini-3-lite' | 'gemini-2.5'.

    - 'gemini-3-lite': lite/no-thinking models that do NOT accept ThinkingConfig.
    - 'gemini-3':      thinking-capable Gemini 3.x models (use thinking_level).
    - 'gemini-2.5':    Gemini 2.x / 2.5 family (use thinking_budget).
    """
    clean_name = model_name.strip().lower()
    if clean_name.startswith("models/"):
        clean_name = clean_name.split("/", 1)[1]

    # Check lite (no-thinking) models first
    for lite in _LITE_MODELS:
        if lite in clean_name:
            return "gemini-3-lite"

    if clean_name.startswith("gemini-3") or "3." in clean_name:
        return "gemini-3"
    return "gemini-2.5"


def get_thinking_config(
    model_name: str,
    thinking_level: Optional[str] = None,
    thinking_budget: Optional[int] = None,
) -> Optional[types.ThinkingConfig]:
    """
    Builds the model-appropriate ThinkingConfig, or None for lite models.
    Guarantees that thinking_budget and thinking_level are never passed simultaneously.

    Returns None for 'gemini-3-lite' family models that do NOT support ThinkingConfig.
    """
    family = detect_model_family(model_name)
    if family == "gemini-3-lite":
        # These models do NOT accept a thinking_config parameter at all.
        return None
    elif family == "gemini-3":
        level_str = (thinking_level or "low").strip().lower()
        level_map = {
            "minimal": types.ThinkingLevel.MINIMAL,
            "low": types.ThinkingLevel.LOW,
            "medium": types.ThinkingLevel.MEDIUM,
            "high": types.ThinkingLevel.HIGH,
        }
        selected_level = level_map.get(level_str, types.ThinkingLevel.LOW)
        return types.ThinkingConfig(thinking_level=selected_level)
    else:
        budget = 0 if thinking_budget is None else thinking_budget
        return types.ThinkingConfig(thinking_budget=budget)


def build_generate_content_config(
    model_name: str,
    temperature: float = 0.0,
    max_output_tokens: Optional[int] = None,
    response_mime_type: Optional[str] = None,
    response_schema: Optional[Any] = None,
    thinking_level: Optional[str] = None,
    thinking_budget: Optional[int] = None,
) -> types.GenerateContentConfig:
    """
    Constructs a complete GenerateContentConfig with model-specific thinking configuration.

    For 'gemini-3-lite' models (e.g. gemini-3.5-flash-lite) that do NOT support
    ThinkingConfig, thinking_config is omitted from the kwargs entirely to prevent
    400 INVALID_ARGUMENT errors.
    """
    thinking_config = get_thinking_config(
        model_name=model_name,
        thinking_level=thinking_level,
        thinking_budget=thinking_budget,
    )

    kwargs: Dict[str, Any] = {
        "temperature": temperature,
    }
    # Only set thinking_config if the model supports it (non-None return)
    if thinking_config is not None:
        kwargs["thinking_config"] = thinking_config

    if max_output_tokens is not None:
        kwargs["max_output_tokens"] = max_output_tokens
    if response_mime_type is not None:
        kwargs["response_mime_type"] = response_mime_type
    if response_schema is not None:
        kwargs["response_schema"] = response_schema

    return types.GenerateContentConfig(**kwargs)
