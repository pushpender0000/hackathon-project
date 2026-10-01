"""
Observability Trace Generator.

Executes representative live dispute triage cases to generate comprehensive
runtime traces (`traces/phoenix_spans.jsonl`), tool call transcripts (`logs/tool_calls.jsonl`),
and guardrail actions (`logs/agent_actions.jsonl`).

Usage:
    python scripts/generate_observability.py
    python scripts/generate_observability.py --cases DISP-001 DISP-003 DISP-005 DISP-013 DISP-MCP-FAIL
"""

import sys
import asyncio
import argparse
from pathlib import Path
from typing import List

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import get_settings
from run import run_dispute_triage

DEFAULT_CASES = [
    "DISP-001",      # Normal low-risk dispute (provisional credit)
    "DISP-003",      # High value ($2499) -> Tier 3 escalation
    "DISP-005",      # Expired filing window (195 days) -> deny
    "DISP-013",      # Prompt injection attack -> pre-context blocked
    "DISP-MCP-FAIL",  # MCP gateway timeout -> Tier 1 safe escalation
]


async def run_observability_pipeline(cases: List[str], clean: bool = False):
    settings = get_settings()
    root = settings.workspace_root

    traces_file = root / "traces" / "phoenix_spans.jsonl"
    tool_file = root / "logs" / "tool_calls.jsonl"
    action_file = root / "logs" / "agent_actions.jsonl"

    if clean:
        print(">>> Cleaning previous trace and log files for fresh evidence generation...")
        for p in [traces_file, tool_file, action_file]:
            if p.exists():
                p.unlink()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()

    print("=" * 70)
    print(f"GENERATING OBSERVABILITY TRACES FOR {len(cases)} LIVE CASES")
    print(f"Target Cases: {cases}")
    print(f"Clean Mode  : {clean}")
    print("=" * 70)

    for idx, case_id in enumerate(cases, 1):
        print(f"\n>>> [{idx}/{len(cases)}] Executing live case: {case_id}")
        try:
            await run_dispute_triage(case_id)
        except Exception as e:
            print(f"Error executing {case_id}: {e}")
        await asyncio.sleep(2.0)

    print("\n" + "=" * 70)
    print("OBSERVABILITY RUN COMPLETED")
    print("Spans written to : traces/phoenix_spans.jsonl")
    print("Tool calls logged: logs/tool_calls.jsonl")
    print("Actions logged   : logs/agent_actions.jsonl")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Generate live observability trace evidence")
    parser.add_argument(
        "--cases",
        nargs="+",
        default=DEFAULT_CASES,
        help="List of dispute IDs to execute for trace generation",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=False,
        help="Reset/truncate output log and trace files before running to prevent historical contamination",
    )
    args = parser.parse_args()
    asyncio.run(run_observability_pipeline(args.cases, clean=args.clean))


if __name__ == "__main__":
    main()

