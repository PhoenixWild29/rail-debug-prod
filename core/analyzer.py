"""
Core error analyzer — Quad-Tier Cascading Engine.

Tier 1: 9-pattern regex (instant/free)
Tier 2: xAI Grok Fast (cheap/fast default LLM)
Tier 3: Anthropic Claude 3.5 Haiku (mid-tier via --haiku)
Tier 4: Anthropic Claude 3.7 Sonnet (deep reasoning via --deep)
"""

import re
import json
from dataclasses import dataclass, asdict, field
from typing import Optional

from core.llm import analyze_with_llm


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
    tier: int = 1  # 1=regex, 2=grok, 3=haiku, 4=sonnet
    model: Optional[str] = None
    architecture_notes: Optional[str] = None


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


def _build_report_from_llm(llm_result: dict, error_type: str, error_message: str,
                           file_path, line_number, function_name, traceback_text: str) -> DebugReport:
    """Build a DebugReport from LLM analysis results."""
    return DebugReport(
        error_type=llm_result.get("error_type", error_type),
        error_message=llm_result.get("error_message", error_message),
        file_path=llm_result.get("file_path", file_path),
        line_number=llm_result.get("line_number", line_number),
        function_name=llm_result.get("function_name", function_name),
        root_cause=llm_result["root_cause"],
        suggested_fix=llm_result.get("suggested_fix", ""),
        severity=llm_result.get("severity", "medium"),
        raw_traceback=traceback_text,
        tier=llm_result.get("_tier", 2),
        model=llm_result.get("_model"),
        architecture_notes=llm_result.get("architecture_notes"),
    )


def analyze(traceback_text: str, deep: bool = False, haiku: bool = False) -> DebugReport:
    """
    Quad-Tier Cascading Analysis.

    1. Regex match (Tier 1 — free/instant)
    2. If miss + default → xAI Grok Fast (Tier 2)
    3. If --haiku → Claude 3.5 Haiku (Tier 3)
    4. If --deep → Claude 3.7 Sonnet (Tier 4)
    """
    lines = traceback_text.strip().splitlines()
    error_line = lines[-1] if lines else ""

    if ":" in error_line:
        error_type, _, error_message = error_line.partition(":")
        error_type = error_type.strip()
        error_message = error_message.strip()
    else:
        error_type = error_line.strip()
        error_message = ""

    file_path, line_number, function_name = _extract_location(traceback_text)

    # TIER 4: Deep flag bypasses regex entirely
    if deep:
        llm_result = analyze_with_llm(traceback_text, deep=True)
        if llm_result and "root_cause" in llm_result:
            return _build_report_from_llm(
                llm_result, error_type, error_message,
                file_path, line_number, function_name, traceback_text
            )

    # TIER 3: Haiku flag bypasses regex entirely
    if haiku:
        llm_result = analyze_with_llm(traceback_text, haiku=True)
        if llm_result and "root_cause" in llm_result:
            return _build_report_from_llm(
                llm_result, error_type, error_message,
                file_path, line_number, function_name, traceback_text
            )

    # TIER 1: Regex
    matched = _match_pattern(error_line)
    if matched:
        return DebugReport(
            error_type=error_type,
            error_message=error_message,
            file_path=file_path,
            line_number=line_number,
            function_name=function_name,
            root_cause=matched["root_cause"],
            suggested_fix=matched["suggested_fix"],
            severity=matched["severity"],
            raw_traceback=traceback_text,
            tier=1,
        )

    # TIER 2: Grok Fast fallback
    llm_result = analyze_with_llm(traceback_text)
    if llm_result and "root_cause" in llm_result:
        return _build_report_from_llm(
            llm_result, error_type, error_message,
            file_path, line_number, function_name, traceback_text
        )

    # FALLBACK: No LLM available
    return DebugReport(
        error_type=error_type,
        error_message=error_message,
        file_path=file_path,
        line_number=line_number,
        function_name=function_name,
        root_cause=f"Unrecognized error: {error_type} (no LLM available — set XAI_API_KEY or ANTHROPIC_API_KEY in .env)",
        suggested_fix="Configure .env with API keys to enable AI analysis",
        severity="medium",
        raw_traceback=traceback_text,
        tier=0,
    )


def analyze_to_json(traceback_text: str, deep: bool = False, haiku: bool = False) -> str:
    """Analyze and return JSON string."""
    report = analyze(traceback_text, deep=deep, haiku=haiku)
    d = asdict(report)
    d.pop("raw_traceback")
    return json.dumps(d, indent=2)
