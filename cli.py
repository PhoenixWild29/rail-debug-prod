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
    python cli.py --project ./myapp --file e.log  # Project-aware analysis
    python cli.py --scan ./myapp                # Scan project profile
    python cli.py --file error.log --chain      # Chained exception analysis
    python cli.py --batch errors.log            # Multi-error batch analysis
    python cli.py --batch errors.log --deep     # Batch + deep analysis
    python cli.py --file error.log --no-git     # Skip git blame/diff context
    python cli.py --demo --lang go              # Go panic demo
    python cli.py --demo --lang java            # Java/Kotlin NPE demo
    python cli.py --demo --lang solidity        # Solidity revert demo
    python cli.py --serve                       # Launch API server (port 8000)
    python cli.py --serve --port 9000           # API server on custom port
"""

import argparse
import sys
from core.analyzer import analyze, analyze_to_json, analyze_chained


DEMO_TRACEBACK = """Traceback (most recent call last):
  File "app.py", line 42, in main
    from blockchain import verify_hash
  File "blockchain.py", line 5, in <module>
    import solana
ModuleNotFoundError: No module named 'solana'"""

DEMO_CHAINED_TRACEBACK = """Traceback (most recent call last):
  File "db/connection.py", line 23, in connect
    conn = psycopg2.connect(host=db_host, port=5432)
  File "psycopg2/__init__.py", line 122, in connect
    conn = _connect(dsn, connection_factory=connection_factory)
ConnectionRefusedError: [Errno 111] Connection refused

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "api/routes.py", line 45, in get_user
    user = await db.fetch_user(user_id)
  File "services/user_service.py", line 67, in fetch_user
    raise DatabaseError("Failed to fetch user") from e
DatabaseError: Failed to fetch user

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "api/middleware.py", line 12, in error_handler
    response = await handler(request)
  File "api/routes.py", line 48, in get_user
    raise HTTPException(status_code=503, detail="Service unavailable")
HTTPException: 503 Service Unavailable"""

DEMO_DEEP_TRACEBACK = """Traceback (most recent call last):
  File "api/routes.py", line 156, in process_transaction
    result = await escrow.release_milestone(tx_id, amount)
  File "services/escrow.py", line 89, in release_milestone
    sig = self.solana_client.send_transaction(txn, opts)
  File "solana/rpc/api.py", line 234, in send_transaction
    resp = self._provider.make_request(body, commitment)
RuntimeError: Transaction simulation failed: insufficient funds for rent"""

DEMO_GO_TRACEBACK = """panic: runtime error: integer divide by zero

goroutine 1 [running]:
main.divide(...)
\t/home/user/myapp/main.go:15 +0x18
main.main()
\t/home/user/myapp/main.go:22 +0x2f
exit status 2"""

DEMO_JAVA_TRACEBACK = """Exception in thread "main" java.lang.NullPointerException: Cannot invoke "String.length()" because "str" is null
\tat com.example.UserService.processName(UserService.java:42)
\tat com.example.UserService.createUser(UserService.java:28)
\tat com.example.Main.main(Main.java:10)"""

DEMO_SOLIDITY_TRACEBACK = """Error: VM Exception while processing transaction: reverted with reason string 'Insufficient balance'
    at Context.<anonymous> (test/EscrowTest.js:54:7)
    at processTicksAndRejections (node:internal/process/task_queues:95:5)
--> contracts/Escrow.sol:87:9"""

DEMO_LANG_MAP = {
    "go": DEMO_GO_TRACEBACK,
    "java": DEMO_JAVA_TRACEBACK,
    "kotlin": DEMO_JAVA_TRACEBACK,
    "solidity": DEMO_SOLIDITY_TRACEBACK,
}

TIER_LABELS = {
    0: "⚠️  OFFLINE (no LLM)",
    1: "⚡ TIER 1 — Regex (instant/free)",
    2: "🚀 TIER 2 — Grok Fast (default)",
    3: "🧠 TIER 3 — Claude Haiku 4.5 (mid-tier)",
    4: "🔬 TIER 4 — Claude Sonnet 4.6 (deep reasoning)",
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

    if report.git_blame:
        output += f"\n👤 Git Blame:    {report.git_blame}\n"

    if report.git_context_raw:
        for gc in report.git_context_raw:
            cli_fmt = gc.format_for_cli()
            if cli_fmt:
                output += f"\n{cli_fmt}\n"

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
    parser.add_argument(
        "--project", "-p", type=str, metavar="PATH",
        help="Project-Aware Mode: path to project root for dependency/framework context"
    )
    parser.add_argument(
        "--scan", "-s", type=str, metavar="PATH",
        help="Scan a project directory and display its profile (no error analysis)"
    )
    parser.add_argument(
        "--chain", "-c", action="store_true",
        help="Chain-aware analysis: detect and trace exception chains"
    )
    parser.add_argument(
        "--batch", "-b", type=str, metavar="LOGFILE",
        help="Batch mode: extract and analyze all errors in a log file"
    )
    parser.add_argument(
        "--no-git", action="store_true",
        help="Disable git blame/diff context injection"
    )
    parser.add_argument(
        "--lang", "-l", type=str, choices=["go", "java", "kotlin", "solidity"],
        help="Language for --demo: go | java | kotlin | solidity"
    )
    parser.add_argument(
        "--serve", action="store_true",
        help="Launch the Rail Debug API server (FastAPI + Uvicorn)"
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Port for --serve mode (default: 8000)"
    )
    parser.add_argument('--memory', default=True, help='Enable learning loop SQLite memory/pattern recall (default: True)')\n    parser.add_argument('--no-memory', dest='memory', action='store_false')\n    args = parser.parse_args()

    # Set git disable flag if requested
    if args.no_git:
        import os
        os.environ["RAIL_NO_GIT"] = "1"

    # SERVER MODE — launch FastAPI
    if args.serve:
        import uvicorn
        print(f"""
╔══════════════════════════════════════════════╗
║  🚀 RAIL DEBUG API SERVER                     ║
║  Port: {args.port:<38}║
║  Docs: http://localhost:{args.port}/docs{' ' * (27 - len(str(args.port)))}║
╚══════════════════════════════════════════════╝
""")
        uvicorn.run("server:app", host="0.0.0.0", port=args.port, reload=False)
        sys.exit(0)

    # SCAN MODE — display project profile and exit
    if args.scan:
        from core.project import scan_project
        profile = scan_project(args.scan)
        print(f"""
╔══════════════════════════════════════════════╗
║  📦 RAIL DEBUG — Project Profile             ║
╚══════════════════════════════════════════════╝

{profile.format_for_prompt()}
""")
        return

    # BATCH MODE — analyze all errors in a log file
    if args.batch:
        from core.batch import analyze_batch
        with open(args.batch, "r") as f:
            content = f.read()
        project = args.project if args.project else None
        result = analyze_batch(content, deep=args.deep, haiku=args.haiku, project_path=project)

        if result.total_errors == 0:
            print("\n✅ No tracebacks found in the file.")
            return

        if args.json:
            import json
            out = {
                "total_errors": result.total_errors,
                "severity_counts": result.severity_counts,
                "elapsed_seconds": round(result.elapsed_seconds, 2),
                "errors": [],
            }
            for r in result.reports:
                from dataclasses import asdict
                d = asdict(r)
                d.pop("raw_traceback")
                out["errors"].append(d)
            print(json.dumps(out, indent=2))
        else:
            for i, report in enumerate(result.reports, 1):
                print(f"\n{'═' * 50}")
                print(f"  Error {i}/{result.total_errors}")
                print(format_report_pretty(report))
            print(result.format_summary())
        return

    # SENTINEL MODE
    if args.watch:
        from core.watcher import Sentinel
        sentinel = Sentinel(
            filepath=args.watch,
            deep=args.deep,
            haiku=args.haiku,
            json_output=args.json,
            project_path=args.project if args.project else None,
        )
        sentinel.start()
        return

    # SINGLE ANALYSIS MODE
    if args.demo:
        if args.lang and args.lang in DEMO_LANG_MAP:
            traceback_text = DEMO_LANG_MAP[args.lang]
        elif args.chain:
            traceback_text = DEMO_CHAINED_TRACEBACK
        elif args.deep:
            traceback_text = DEMO_DEEP_TRACEBACK
        else:
            traceback_text = DEMO_TRACEBACK
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
    project = args.project if args.project else None

    # CHAIN MODE — detect and trace exception chains
    if args.chain:
        from core.chaining import is_chained_traceback
        chained_report = analyze_chained(traceback_text, deep=args.deep, haiku=args.haiku, project_path=project, use_memory=args.memory)

        if args.json:
            print(chained_report.to_json())
        else:
            if chained_report.is_chained:
                print(f"\n{chained_report.chain_summary}")
            if project:
                from core.project import get_project_profile
                proj = get_project_profile(project)
                print(f"\n📦 Project: {proj.name} | {', '.join(proj.languages)} | {', '.join(proj.frameworks[:5])}")
            for i, report in enumerate(chained_report.reports):
                if chained_report.is_chained:
                    label = "🔗 ROOT CAUSE" if i == 0 else f"🔗 Chain Link {i + 1}"
                    print(f"\n{'─' * 40}\n  {label}")
                print(format_report_pretty(report))
        return

    if args.json:
        print(analyze_to_json(traceback_text, deep=args.deep, haiku=args.haiku, project_path=project, use_memory=args.memory))
    else:
        report = analyze(traceback_text, deep=args.deep, haiku=args.haiku, project_path=project, use_memory=args.memory)
        if project:
            from core.project import get_project_profile
            proj = get_project_profile(project)
            print(f"\n📦 Project: {proj.name} | {', '.join(proj.languages)} | {', '.join(proj.frameworks[:5])}")
        print(format_report_pretty(report))


if __name__ == "__main__":
    main()
