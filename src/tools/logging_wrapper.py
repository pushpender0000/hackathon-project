import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Callable
from functools import wraps
from src.utils.masking import sanitize_data

LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
MCP_TRANSCRIPT_PATH = LOGS_DIR / "mcp_transcript.jsonl"
TOOL_CALLS_PATH = LOGS_DIR / "tool_calls.jsonl"

def log_mcp_event(
    method: str,
    tool_name: Optional[str] = None,
    uri: Optional[str] = None,
    args: Optional[Dict[str, Any]] = None,
    result: Optional[Any] = None,
    status: str = "SUCCESS",
    latency_ms: float = 0.0
):
    """
    Appends a machine-generated record of an MCP event to logs/mcp_transcript.jsonl.
    Masks all sensitive data before persisting.
    """
    if "PYTEST_CURRENT_TEST" in os.environ or "EVALUATION_RUN" in os.environ:
        return
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "tool_name": tool_name,
        "uri": uri,
        "args": sanitize_data(args or {}),
        "result": sanitize_data(result),
        "status": status,
        "latency_ms": round(latency_ms, 2)
    }
    with open(MCP_TRANSCRIPT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def log_tool_invocation(
    agent: str,
    tool_name: str,
    args: Dict[str, Any],
    result: Any,
    latency_ms: float,
    status: str = "SUCCESS"
):
    """
    Appends a structured tool invocation record to logs/tool_calls.jsonl.
    Masks all sensitive data before persisting.
    """
    if "PYTEST_CURRENT_TEST" in os.environ or "EVALUATION_RUN" in os.environ:
        return
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "tool_name": tool_name,
        "args": sanitize_data(args),
        "result": sanitize_data(result),
        "latency_ms": round(latency_ms, 2),
        "status": status
    }
    with open(TOOL_CALLS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def instrumented_tool(agent_name: str, tool_name: str):
    """
    Decorator to wrap any synchronous or asynchronous tool with automatic
    latency tracking, error logging, and sanitized log generation.
    """
    def decorator(func: Callable):
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            status = "SUCCESS"
            result = None
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "ERROR"
                result = {"error": type(e).__name__, "message": str(e)}
                raise
            finally:
                latency_ms = (time.perf_counter() - start) * 1000.0
                all_args = {"args": args, "kwargs": kwargs}
                log_tool_invocation(
                    agent=agent_name,
                    tool_name=tool_name,
                    args=all_args,
                    result=result,
                    latency_ms=latency_ms,
                    status=status
                )

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            status = "SUCCESS"
            result = None
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "ERROR"
                result = {"error": type(e).__name__, "message": str(e)}
                raise
            finally:
                latency_ms = (time.perf_counter() - start) * 1000.0
                all_args = {"args": args, "kwargs": kwargs}
                log_tool_invocation(
                    agent=agent_name,
                    tool_name=tool_name,
                    args=all_args,
                    result=result,
                    latency_ms=latency_ms,
                    status=status
                )

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
