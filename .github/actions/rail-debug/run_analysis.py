#!/usr/bin/env python3
"""
Rail Debug GitHub Action entrypoint.

Reads a traceback from env vars or a file, runs the Quad-Tier analyzer
(Tier 1 regex runs fully offline — no API key required for common patterns),
and writes analysis results to GITHUB_OUTPUT.

Environment variables (set by action.yml):
  RAIL_DEBUG_TRACEBACK        Raw traceback string
  RAIL_DEBUG_TRACEBACK_FILE   Path to a file containing the traceback
  RAIL_DEBUG_MODE             auto | haiku | deep
  RAIL_DEBUG_FAIL_ON_CRITICAL true | false
  PYTHONPATH                  Must include repo root (set by action.yml)
"""
import os
import sys


def write_output(key: str, value: str) -> None:
    """Write a key=value pair to GITHUB_OUTPUT using the EOF delimiter format."""
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if not github_output:
        # Fallback for local testing
        print(f"::set-output name={key}::{value}")
        return
    delimiter = "EOF_RAIL_DEBUG"
    with open(github_output, "a") as f:
        f.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def tier_label(tier: int) -> str:
    return {1: "Regex (offline)", 2: "Grok Fast", 3: "Claude Haiku 4.5", 4: "Claude Sonnet 4.6"}.get(tier, "Unknown")


def main() -> None:
    traceback = os.environ.get("RAIL_DEBUG_TRACEBACK", "")
    traceback_file = os.environ.get("RAIL_DEBUG_TRACEBACK_FILE", "")
    mode = os.environ.get("RAIL_DEBUG_MODE", "auto")
    fail_on_critical = os.environ.get("RAIL_DEBUG_FAIL_ON_CRITICAL", "false").lower() == "true"

    # Prefer file if provided
    if traceback_file:
        if not os.path.isfile(traceback_file):
            print(f"::error::Rail Debug: traceback_file not found: {traceback_file}")
            sys.exit(1)
        with open(traceback_file) as fh:
            traceback = fh.read()

    if not traceback.strip():
        print("::warning::Rail Debug: no traceback provided — skipping analysis")
        write_output("severity", "")
        write_output("tier", "")
        write_output("root_cause", "no traceback provided")
        write_output("suggested_fix", "")
        sys.exit(0)

    # Import analyzer (PYTHONPATH must include repo root)
    try:
        from core.analyzer import analyze
    except ImportError as exc:
        print(f"::error::Rail Debug: failed to import core.analyzer — {exc}")
        print("::error::Ensure PYTHONPATH includes the rail-debug-prod repo root")
        sys.exit(1)

    deep = mode == "deep"
    haiku = mode == "haiku"

    try:
        report = analyze(traceback_text=traceback, deep=deep, haiku=haiku, no_git=True)
    except Exception as exc:
        print(f"::error::Rail Debug analysis failed: {exc}")
        sys.exit(1)

    severity = (report.severity or "unknown").upper()
    tier = report.tier
    root_cause = report.root_cause or ""
    suggested_fix = report.suggested_fix or ""

    # Write action outputs
    write_output("severity", severity)
    write_output("tier", str(tier))
    write_output("root_cause", root_cause)
    write_output("suggested_fix", suggested_fix)

    # Print human-readable summary
    print()
    print("=" * 60)
    print("  Rail Debug — AI Error Analysis")
    print("=" * 60)
    print(f"  Severity:      {severity}")
    print(f"  Tier:          {tier} — {tier_label(tier)}")
    if report.model:
        print(f"  Model:         {report.model}")
    print(f"  Error type:    {report.error_type}")
    print(f"  Location:      {report.file_path}:{report.line_number}" if report.file_path else "  Location:      unknown")
    print("-" * 60)
    print(f"  Root cause:    {root_cause}")
    print(f"  Suggested fix: {suggested_fix}")
    print("=" * 60)
    print()

    if fail_on_critical and severity == "CRITICAL":
        print("::error::Rail Debug: CRITICAL severity error detected — failing workflow step")
        sys.exit(1)


if __name__ == "__main__":
    main()
