#!/usr/bin/env python3
"""
Rail Debug CLI — Tri-State AI Error Analysis Engine.

Usage:
    python cli.py --demo                  # Tier 1 regex demo
    python cli.py --demo --deep           # Tier 3 deep analysis demo
    python cli.py --file error.log        # Analyze log file
    python cli.py --file error.log --deep # Deep analysis on log file
    some_command 2>&1 | python cli.py     # Pipe stderr
    python cli.py --json                  # JSON output
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
    2: "🧠 TIER 2 — Claude 4.5 Haiku (fast)",
    3: "🔬 TIER 3 — Claude 4.6 Deep Analysis",
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
        description="Rail Debug — Tri-State AI Error Analysis Engine"
    )
    parser.add_argument(
        "--file", "-f", type=str, help="Path to error log file"
    )
    parser.add_argument(
        "--json", "-j", action="store_true", help="Output as JSON"
    )
    parser.add_argument(
        "--deep", "-d", action="store_true",
        help="Tier 3: Deep analysis via Claude 4.6 Sonnet/Opus"
    )
    parser.add_argument(
        "--demo", action="store_true", help="Run with a demo traceback"
    )
    args = parser.parse_args()

    # Get input
    if args.demo:
        traceback_text = DEMO_DEEP_TRACEBACK if args.deep else DEMO_TRACEBACK
    elif args.file:
        with open(args.file, "r") as f:
            traceback_text = f.read()
    elif not sys.stdin.isatty():
        traceback_text = sys.stdin.read()
    else:
        parser.print_help()
        print("\n⚠️  No input. Use --file, --demo, or pipe stderr into Rail Debug.")
        sys.exit(1)

    if not traceback_text.strip():
        print("⚠️  Empty input. Nothing to analyze.")
        sys.exit(1)

    # Analyze
    if args.json:
        print(analyze_to_json(traceback_text, deep=args.deep))
    else:
        report = analyze(traceback_text, deep=args.deep)
        print(format_report_pretty(report))


if __name__ == "__main__":
    main()
