"""
Multi-Error Batch Analysis — Process Multiple Errors in One Pass.

Scans a log file (or stdin) for multiple tracebacks, extracts each one,
and runs them through the Quad-Tier analyzer independently. Produces
a unified batch report with per-error results and an aggregate summary.

Supports:
  - Python tracebacks (Traceback most recent call last)
  - Node.js stack traces (Error: ... at ...)
  - Rust panics (thread 'x' panicked at ...)
  - Mixed-language log files
"""

import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

from core.analyzer import DebugReport, analyze
from core.context import detect_language


# ── Traceback Boundary Detection ─────────────────────────────────

# Python traceback start
PY_TB_START = re.compile(r"^Traceback \(most recent call last\):", re.MULTILINE)

# Python chaining separators (should NOT split — they're part of one chained error)
PY_CHAIN_SEP = re.compile(
    r"^\s*(?:The above exception was the direct cause|During handling of the above exception)",
    re.MULTILINE,
)

# Node.js error start: lines like "Error: ...", "TypeError: ...", etc. followed by "    at ..."
NODE_ERROR_START = re.compile(
    r"^([A-Z]\w*(?:Error|Exception)): .+\n\s+at\s",
    re.MULTILINE,
)

# Rust panic start
RUST_PANIC_START = re.compile(r"^thread '.*' panicked at", re.MULTILINE)

# Generic error line (for end-of-traceback detection)
ERROR_LINE = re.compile(r"^[A-Za-z][\w.]*(?:Error|Exception|Warning|Exit).*:")


@dataclass
class BatchResult:
    """Results from a multi-error batch analysis."""
    reports: List[DebugReport] = field(default_factory=list)
    total_errors: int = 0
    severity_counts: dict = field(default_factory=lambda: {
        "critical": 0, "high": 0, "medium": 0, "low": 0,
    })
    elapsed_seconds: float = 0.0

    @property
    def has_critical(self) -> bool:
        return self.severity_counts["critical"] > 0

    def format_summary(self) -> str:
        """Format a batch summary for CLI output."""
        sev = self.severity_counts
        icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}

        lines = [
            f"\n╔══════════════════════════════════════════════╗",
            f"║  📊 RAIL DEBUG — Batch Summary                ║",
            f"╚══════════════════════════════════════════════╝\n",
            f"  Total Errors:  {self.total_errors}",
            f"  ⏱️  Elapsed:    {self.elapsed_seconds:.1f}s",
            f"",
        ]

        for level in ["critical", "high", "medium", "low"]:
            count = sev[level]
            if count > 0:
                lines.append(f"  {icons[level]} {level.upper()}: {count}")

        if self.has_critical:
            lines.append(f"\n  ⚠️  CRITICAL ERRORS DETECTED — immediate attention required")

        return "\n".join(lines)


def extract_tracebacks(text: str) -> List[str]:
    """
    Extract all individual tracebacks from a log file or text blob.

    Handles:
    - Multiple Python tracebacks (preserving chained ones as single units)
    - Node.js stack traces
    - Rust panic outputs
    - Interleaved log lines between errors

    Returns a list of raw traceback strings, each representing one error
    (chained Python tracebacks stay as one unit).
    """
    tracebacks = []

    # Strategy: find all Python traceback starts, then extract each block
    # accounting for chaining (don't split chained tracebacks)
    py_starts = [m.start() for m in PY_TB_START.finditer(text)]

    if py_starts:
        tracebacks.extend(_extract_python_blocks(text, py_starts))
    else:
        # Try Node.js
        node_starts = [m.start() for m in NODE_ERROR_START.finditer(text)]
        if node_starts:
            tracebacks.extend(_extract_generic_blocks(text, node_starts))
        else:
            # Try Rust
            rust_starts = [m.start() for m in RUST_PANIC_START.finditer(text)]
            if rust_starts:
                tracebacks.extend(_extract_generic_blocks(text, rust_starts))

    return tracebacks


def _extract_python_blocks(text: str, starts: List[int]) -> List[str]:
    """
    Extract Python traceback blocks, merging chained exceptions.

    When we find a chain separator between two traceback starts,
    they're part of the same error — merge them into one block.
    """
    if not starts:
        return []

    # Group starts that are part of the same chained exception
    groups = []  # List of (start, end) for each independent error
    current_start = starts[0]

    for i in range(1, len(starts)):
        # Check if there's a chain separator between this start and the previous
        between = text[starts[i - 1]:starts[i]]
        if PY_CHAIN_SEP.search(between):
            # Part of the same chain — continue
            continue
        else:
            # New independent error — close previous group
            groups.append((current_start, starts[i]))
            current_start = starts[i]

    # Close final group
    groups.append((current_start, len(text)))

    # Extract each group's text, trimming trailing non-traceback lines
    blocks = []
    for start, end in groups:
        block = text[start:end].strip()
        block = _trim_trailing_noise(block)
        if block:
            blocks.append(block)

    return blocks


def _extract_generic_blocks(text: str, starts: List[int]) -> List[str]:
    """Extract non-Python error blocks using start positions."""
    blocks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = text[start:end].strip()
        block = _trim_trailing_noise(block)
        if block:
            blocks.append(block)
    return blocks


def _trim_trailing_noise(block: str) -> str:
    """
    Trim trailing lines that aren't part of the traceback.

    After the error line, there may be log noise (timestamps, blank lines, etc.)
    that shouldn't be included in the analysis.
    """
    lines = block.splitlines()
    if not lines:
        return block

    # Find the last line that looks like an error line
    last_error_idx = len(lines) - 1
    for i in range(len(lines) - 1, -1, -1):
        stripped = lines[i].strip()
        if stripped and ERROR_LINE.match(stripped):
            last_error_idx = i
            break
        elif stripped.startswith("File ") or stripped.startswith("  "):
            # Still in traceback body
            last_error_idx = i
            break

    return "\n".join(lines[: last_error_idx + 1])


def analyze_batch(
    text: str,
    deep: bool = False,
    haiku: bool = False,
    project_path: Optional[str] = None,
) -> BatchResult:
    """
    Extract and analyze all errors in a text blob.

    Args:
        text: Raw log file content or multi-error text
        deep: Use Tier 4 deep analysis for each error
        haiku: Use Tier 3 Haiku analysis for each error
        project_path: Optional project root for project-aware analysis

    Returns:
        BatchResult with individual reports and aggregate summary
    """
    start_time = time.time()

    tracebacks = extract_tracebacks(text)
    result = BatchResult(total_errors=len(tracebacks))

    for tb in tracebacks:
        report = analyze(tb, deep=deep, haiku=haiku, project_path=project_path)
        result.reports.append(report)
        sev = report.severity
        if sev in result.severity_counts:
            result.severity_counts[sev] += 1

    result.elapsed_seconds = time.time() - start_time
    return result
