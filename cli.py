#!/usr/bin/env python3
"""
Rail Debug CLI — pipe errors in, get instant structured analysis out.

Usage:
    python cli.py < error.log
    python cli.py --file error.log
    some_command 2>&1 | python cli.py
    python cli.py --demo
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


def format_report_pretty(report) -> str:
    """Human-readable colored output."""
    severity_icons = {
        "low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"
    }
    icon = severity_icons.get(report.severity, "⚪")

    return f"""
╔══════════════════════════════════════════╗
║  🛠️  RAIL DEBUG — Analysis Report       ║
╚══════════════════════════════════════════╝

{icon} Severity:     {report.severity.upper()}
❌ Error Type:    {report.error_type}
💬 Message:       {report.error_message}
📂 File:          {report.file_path or 'N/A'}
📍 Line:          {report.line_number or 'N/A'}
🔧 Function:      {report.function_name or 'N/A'}

🧠 Root Cause:    {report.root_cause}
✅ Suggested Fix: {report.suggested_fix}
"""


def main():
    parser = argparse.ArgumentParser(
        description="Rail Debug — AI-powered error analysis"
    )
    parser.add_argument(
        "--file", "-f", type=str, help="Path to error log file"
    )
    parser.add_argument(
        "--json", "-j", action="store_true", help="Output as JSON"
    )
    parser.add_argument(
        "--demo", action="store_true", help="Run with a demo traceback"
    )
    args = parser.parse_args()

    # Get input
    if args.demo:
        traceback_text = DEMO_TRACEBACK
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
        print(analyze_to_json(traceback_text))
    else:
        report = analyze(traceback_text)
        print(format_report_pretty(report))


if __name__ == "__main__":
    main()
