import os
import sys
import importlib
import asyncio
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# Ensure workspace root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()

# Schema with ZERO defaults for Google GenAI structured output
class SmokeTestOutput(BaseModel):
    category: str
    confidence: float

def check_local_dependencies():
    print("=" * 60)
    print("1. LOCAL DEPENDENCY & INTERFACE VERIFICATION")
    print("=" * 60)
    
    # 1. Python version
    py_ver = sys.version.split()[0]
    print(f"[*] Python Version: {py_ver}")
    assert sys.version_info >= (3, 11), f"Python 3.11+ required, found {py_ver}"
    
    packages = [
        ("google.genai", "google-genai"),
        ("langgraph", "langgraph"),
        ("langgraph.checkpoint.sqlite", "langgraph-checkpoint-sqlite"),
        ("langmem", "langmem"),
        ("langchain_mcp_adapters", "langchain-mcp-adapters"),
        ("mcp", "mcp"),
        ("chromadb", "chromadb"),
        ("sentence_transformers", "sentence-transformers"),
        ("phoenix", "arize-phoenix"),
        ("openinference.instrumentation.langchain", "openinference-instrumentation-langchain"),
        ("deepeval", "deepeval"),
        ("presidio_analyzer", "presidio-analyzer"),
        ("pydantic", "pydantic"),
        ("pytest", "pytest"),
    ]

    installed_versions = {}
    for module_name, dist_name in packages:
        try:
            mod = importlib.import_module(module_name)
            try:
                from importlib.metadata import version
                ver = version(dist_name)
            except Exception:
                ver = getattr(mod, "__version__", "unknown")
            installed_versions[dist_name] = ver
            print(f"  [OK] {dist_name:<40} : {ver}")
        except Exception as e:
            print(f"  [FAIL] {dist_name:<38} : ERROR ({e})")
            raise

    # Verify LangGraph BaseStore symbols
    from langgraph.store.base import BaseStore, GetOp, PutOp, SearchOp, ListNamespacesOp, Item, SearchItem
    print("  [OK] LangGraph BaseStore & batching operations verified")

    # Verify SQLite checkpointer
    from langgraph.checkpoint.sqlite import SqliteSaver
    print("  [OK] LangGraph SqliteSaver checkpointer verified")

    # Verify LangMem tool constructors
    from langmem import create_manage_memory_tool, create_search_memory_tool
    print("  [OK] LangMem create_manage_memory_tool & create_search_memory_tool verified")

    # Verify MCP SDK FastMCP
    from mcp.server.fastmcp import FastMCP
    print("  [OK] MCP FastMCP server verified")

    # Verify langchain-mcp-adapters
    from langchain_mcp_adapters.client import MultiServerMCPClient
    print("  [OK] langchain-mcp-adapters MultiServerMCPClient verified")

    print("\n>>> ALL LOCAL DEPENDENCIES & CORE SYMBOLS VERIFIED SUCCESSFULLY.")
    return installed_versions

async def check_gemini_api():
    print("\n" + "=" * 60)
    print("2. GOOGLE GEMINI SDK & PREFLIGHT PROBE")
    print("=" * 60)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    model_name = os.environ.get("GEMINI_MODEL", "").strip()
    thinking_level = os.environ.get("GEMINI_THINKING_LEVEL", "minimal").strip()
    thinking_budget_str = os.environ.get("GEMINI_THINKING_BUDGET", "0")
    try:
        thinking_budget = int(thinking_budget_str)
    except ValueError:
        thinking_budget = 0

    if not api_key:
        print("  [SKIP] GEMINI_API_KEY is not set in environment or .env.")
        print("         Local dependency verification passed, but live Gemini probe skipped.")
        return False

    if not model_name:
        print("  [SKIP] GEMINI_MODEL is not set in environment or .env.")
        print("         Please set GEMINI_MODEL (e.g. gemini-3.6-flash, gemini-2.5-flash).")
        return False

    from src.utils.gemini_config import (
        detect_model_family,
        get_thinking_config,
        build_generate_content_config,
    )

    family = detect_model_family(model_name)
    print(f"[*] Configured Model : {model_name} (Architecture Family: {family})")
    if family == "gemini-3":
        print(f"[*] Thinking Strategy : minimized using thinking_level='{thinking_level}'")
    else:
        print(f"[*] Thinking Strategy : disabled using thinking_budget={thinking_budget}")

    from google import genai

    # Initialize client
    client = genai.Client(api_key=api_key)

    # 1. Models List Probe (Runs once at preflight)
    print("  [*] Querying client.models.list()...")
    try:
        model_objs = client.models.list()
        accessible_models = [m.name for m in model_objs]
        clean_names = [m.split("/")[-1] for m in accessible_models]
        if model_name not in clean_names and model_name not in accessible_models:
            print(f"  [WARN] Model '{model_name}' not explicitly listed. Accessible: {clean_names[:5]}...")
        else:
            print(f"  [OK] Model '{model_name}' confirmed in accessible models catalog.")
    except Exception as e:
        print(f"  [FAIL] Failed to list models via API: {e}")
        return False

    # 2. Single Structured-Output Smoke Test Call using model-specific config
    print(f"  [*] Executing ONE-TIME structured-output smoke test on {model_name}...")
    try:
        config = build_generate_content_config(
            model_name=model_name,
            temperature=0.0,
            max_output_tokens=150,
            response_mime_type="application/json",
            response_schema=SmokeTestOutput,
            thinking_level=thinking_level,
            thinking_budget=thinking_budget,
        )

        # Verify that only the correct thinking parameter was configured
        if family == "gemini-3":
            assert config.thinking_config.thinking_budget is None, "thinking_budget must not be set for Gemini 3.x"
            assert config.thinking_config.thinking_level is not None, "thinking_level must be set for Gemini 3.x"
            print("  [OK] Verified thinking_config: thinking_level set, thinking_budget is None")
        else:
            assert config.thinking_config.thinking_level is None, "thinking_level must not be set for Gemini 2.x"
            assert config.thinking_config.thinking_budget is not None, "thinking_budget must be set for Gemini 2.x"
            print("  [OK] Verified thinking_config: thinking_budget set, thinking_level is None")

        response = await client.aio.models.generate_content(
            model=model_name,
            contents="Classify this synthetic transaction note: 'Unauthorized Uber ride $35'",
            config=config,
        )

        # 3. Verify response parsing
        parsed = response.parsed
        assert isinstance(parsed, SmokeTestOutput), f"Expected SmokeTestOutput, got {type(parsed)}"
        print(f"  [OK] Structured Output Parsed Successfully: category='{parsed.category}', confidence={parsed.confidence}")

        # 4. Verify telemetry metadata
        usage = response.usage_metadata
        prompt_tokens = getattr(usage, "prompt_token_count", 0)
        output_tokens = getattr(usage, "candidates_token_count", 0)
        thoughts_tokens = getattr(usage, "thoughts_token_count", 0)
        total_tokens = getattr(usage, "total_token_count", 0)

        print("\n--- Smoke Test Telemetry Breakdown ---")
        print(f"  Model                   : {model_name}")
        print(f"  Family                  : {family}")
        print(f"  Prompt Tokens           : {prompt_tokens}")
        print(f"  Candidates Tokens       : {output_tokens}")
        print(f"  Thoughts Tokens         : {thoughts_tokens}")
        print(f"  Total Tokens            : {total_tokens}")
        if family == "gemini-3":
            print(f"  Thinking Level Setting  : {config.thinking_config.thinking_level}")
        else:
            print(f"  Thinking Budget Setting : {config.thinking_config.thinking_budget}")

        assert total_tokens > 0, "usage_metadata did not return token counts"
        print("  [OK] Model-specific thinking governance and usage_metadata verified.")
        print("\n>>> GEMINI PREFLIGHT SMOKE TEST PASSED CLEANLY.")
        return True

    except Exception as e:
        print(f"  [FAIL] Gemini smoke test failed: {e}")
        return False

async def main():
    check_local_dependencies()
    await check_gemini_api()

if __name__ == "__main__":
    asyncio.run(main())
