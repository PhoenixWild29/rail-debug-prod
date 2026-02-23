"""
Core error analyzer — parses tracebacks and returns structured debug reports.
Lightweight. No external AI API calls yet (Phase 1 = pattern matching).
Phase 2 will add LLM-powered root cause analysis.
"""

import re
import json
import sys
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class DebugReport:
    error_type: str
    error_message: str
    file_path: Optional[str]
    line_number: Optional[int]
    function_name: Optional[str]
    root_cause: str
    suggested_fix: str
    severity: str  # low | medium | high | critical
    raw_traceback: str


# Common Python error patterns → quick diagnosis
KNOWN_PATTERNS = {
    r"ModuleNotFoundError: No module named '(\S+)'": {
        "root_cause": "Missing dependency: {m1}",
        "suggested_fix": "Run: pip install {m1}",
        "severity": "high",
    },
    r"ImportError: cannot import name '(\S+)' from '(\S+)'": {
        "root_cause": "Bad import — '{m1}' doesn't exist in '{m2}' (version mismatch or typo)",
        "suggested_fix": "Check package version or fix import name",
        "severity": "high",
    },
    r"KeyError: (.+)": {
        "root_cause": "Accessed missing dict key: {m1}",
        "suggested_fix": "Use .get({m1}, default) or check key existence first",
        "severity": "medium",
    },
    r"TypeError: (.+) got an unexpected keyword argument '(\S+)'": {
        "root_cause": "Function {m1} doesn't accept kwarg '{m2}'",
        "suggested_fix": "Check function signature — likely API change or typo",
        "severity": "medium",
    },
    r"FileNotFoundError: \[Errno 2\] No such file or directory: '(.+)'": {
        "root_cause": "Missing file: {m1}",
        "suggested_fix": "Verify path exists or create the file/directory",
        "severity": "high",
    },
    r"ConnectionRefusedError": {
        "root_cause": "Service unreachable — connection refused",
        "suggested_fix": "Check if the target service is running and port is correct",
        "severity": "critical",
    },
    r"PermissionError": {
        "root_cause": "Insufficient file/process permissions",
        "suggested_fix": "Check file ownership and permissions (chmod/chown)",
        "severity": "critical",
    },
    r"ZeroDivisionError": {
        "root_cause": "Division by zero",
        "suggested_fix": "Add guard: check denominator != 0 before dividing",
        "severity": "medium",
    },
    r"AttributeError: '(\S+)' object has no attribute '(\S+)'": {
        "root_cause": "'{m1}' has no attribute '{m2}' — likely None or wrong type",
        "suggested_fix": "Add type check or verify object initialization",
        "severity": "medium",
    },
}


def _extract_location(traceback_text: str) -> tuple:
    """Pull the last file/line/function from a Python traceback."""
    matches = re.findall(
        r'File "(.+?)", line (\d+), in (.+)', traceback_text
    )
    if matches:
        last = matches[-1]
        return last[0], int(last[1]), last[2]
    return None, None, None


def _match_pattern(error_line: str) -> Optional[dict]:
    """Match error line against known patterns."""
    for pattern, template in KNOWN_PATTERNS.items():
        m = re.search(pattern, error_line)
        if m:
            groups = {f"m{i+1}": g for i, g in enumerate(m.groups())}
            return {
                "root_cause": template["root_cause"].format(**groups) if groups else template["root_cause"],
                "suggested_fix": template["suggested_fix"].format(**groups) if groups else template["suggested_fix"],
                "severity": template["severity"],
            }
    return None


def analyze(traceback_text: str) -> DebugReport:
    """Analyze a traceback string and return a structured DebugReport."""
    lines = traceback_text.strip().splitlines()

    # Extract error type and message from last line
    error_line = lines[-1] if lines else ""
    if ":" in error_line:
        error_type, _, error_message = error_line.partition(":")
        error_type = error_type.strip()
        error_message = error_message.strip()
    else:
        error_type = error_line.strip()
        error_message = ""

    file_path, line_number, function_name = _extract_location(traceback_text)
    matched = _match_pattern(error_line)

    if matched:
        root_cause = matched["root_cause"]
        suggested_fix = matched["suggested_fix"]
        severity = matched["severity"]
    else:
        root_cause = f"Unrecognized error: {error_type}"
        suggested_fix = "Inspect the traceback manually or escalate to Phase 2 (LLM analysis)"
        severity = "medium"

    return DebugReport(
        error_type=error_type,
        error_message=error_message,
        file_path=file_path,
        line_number=line_number,
        function_name=function_name,
        root_cause=root_cause,
        suggested_fix=suggested_fix,
        severity=severity,
        raw_traceback=traceback_text,
    )


def analyze_to_json(traceback_text: str) -> str:
    """Analyze and return JSON string."""
    report = analyze(traceback_text)
    d = asdict(report)
    d.pop("raw_traceback")  # Keep output clean
    return json.dumps(d, indent=2)
