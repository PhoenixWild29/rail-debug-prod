#!/usr/bin/env python3
"""
Rail Debug CLI — Quad-Tier AI Error Analysis Engine.

Usage:
    python cli.py --demo                        # Tier 1 regex demo
    python cli.py --demo --haiku                # Tier 3 Haiku analysis demo
    python cli.py --demo --deep                 # Tier 4 deep analysis demo
    python cli.py --file error.log              # Analyze log file (Grok default)
    python cli.py --file error.log --haiku      # Haiku analysis on log file
    python cli.py --file error.log --deep       # Deep analysis on log file
    python cli.py --watch app.log               # Sentinel mode (real-time)
    python cli.py --watch app.log --deep        # Sentinel + deep analysis
    some_command 2>&1 | python cli.py           # Pipe stderr
    python cli.py --json                        # JSON output
"""

import argparse
import sys
from core.analyzer import analyze, analyze_to_json


DEMO_TRACEBACK = """Traceback (most recent call last):
  File "app.py", line 42, in main
    from blockchain import verify_hash
  File "blockchain.py", line 5, in <module>
    import solana
ModuleNotFoundError: No module named 'solana'"""

DEMO_DEEP_TRACEBACK = """Traceback (most recent call last):
  File "api/routes.py", line 156, in process_transaction
    result = await escrow.release_milestone(tx_id, amount)
  File "services/escrow.py", line 89, in release_milestone
    sig = self.solana_client.send_transaction(txn, opts)
  File "solana/rpc/api.py", line 234, in send_transaction
    resp = self._provider.make_request(body, commitment)
RuntimeError: Transaction simulation failed: insufficient funds for rent"""


TIER_LABELS = {
    0: "⚠️  OFFLINE (no LLM)",
    1: "⚡ TIER 1 — Regex (instant/free)",
    2: "🚀 TIER 2 — Grok Fast (default)",
    3: "🧠 TIER 3 — Claude 3.5 Haiku (mid-tier)",
    4: "🔬 TIER 4 — Claude 3.7 Sonnet (deep reasoning)",
}


def format_report_pretty(report) -> str:
    """Human-readable output."""
    severity_icons = {
        "low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"
    }
    icon = severity_icons.get(report.severity, "⚪")
    tier_label = TIER_LABELS.get(report.tier, f"Tier {report.tier}")

    output = f"""
╔══════════════════════════════════════════════╗
║  🛠️  RAIL DEBUG — Analysis Report            ║
╚══════════════════════════════════════════════╝

🏷️  Engine:       {tier_label}
{f'🤖 Model:        {report.model}' if report.model else ''}
{icon} Severity:     {report.severity.upper()}
❌ Error Type:    {report.error_type}
💬 Message:       {report.error_message}
📂 File:          {report.file_path or 'N/A'}
📍 Line:          {report.line_number or 'N/A'}
🔧 Function:      {report.function_name or 'N/A'}

🧠 Root Cause:    {report.root_cause}
✅ Suggested Fix: {report.suggested_fix}
"""

    if report.architecture_notes:
        output += f"\n🏗️  Architecture:  {report.architecture_notes}\n"

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Rail Debug — Quad-Tier AI Error Analysis Engine"
    )
    parser.add_argument(
        "--file", "-f", type=str, help="Path to error log file"
    )
    parser.add_argument(
        "--json", "-j", action="store_true", help="Output as JSON"
    )
    parser.add_argument(
        "--haiku", action="store_true",
        help="Tier 3: Mid-tier analysis via Claude 3.5 Haiku"
    )
    parser.add_argument(
        "--deep", "-d", action="store_true",
        help="Tier 4: Deep analysis via Claude 3.7 Sonnet"
    )
    parser.add_argument(
        "--demo", action="store_true", help="Run with a demo traceback"
    )
    parser.add_argument(
        "--watch", "-w", type=str, metavar="LOGFILE",
        help="Sentinel mode: watch a log file for errors in real-time"
    )
    args = parser.parse_args()

    # SENTINEL MODE
    if args.watch:
        from core.watcher import Sentinel
        sentinel = Sentinel(
            filepath=args.watch,
            deep=args.deep,
            haiku=args.haiku,
            json_output=args.json,
        )
        sentinel.start()
        return

    # SINGLE ANALYSIS MODE
    if args.demo:
        traceback_text = DEMO_DEEP_TRACEBACK if args.deep else DEMO_TRACEBACK
    elif args.file:
        with open(args.file, "r") as f:
            traceback_text = f.read()
    elif not sys.stdin.isatty():
        traceback_text = sys.stdin.read()
    else:
        parser.print_help()
        print("\n⚠️  No input. Use --file, --demo, --watch, or pipe stderr into Rail Debug.")
        sys.exit(1)

    if not traceback_text.strip():
        print("⚠️  Empty input. Nothing to analyze.")
        sys.exit(1)

    # Analyze
    if args.json:
        print(analyze_to_json(traceback_text, deep=args.deep, haiku=args.haiku))
    else:
        report = analyze(traceback_text, deep=args.deep, haiku=args.haiku)
        print(format_report_pretty(report))


if __name__ == "__main__":
    main()
