"""
Core error analyzer — Quad-Tier Universal Cascading Engine.

Supports Python, Node.js/JavaScript, and Rust error analysis.

Tier 1: Regex patterns (instant/free) — Python + Node + Rust
Tier 2: xAI Grok Fast (cheap/fast default LLM)
Tier 3: Anthropic Claude 3.5 Haiku (mid-tier via --haiku)
Tier 4: Anthropic Claude 3.7 Sonnet (deep reasoning via --deep)
"""

import re
import json
from dataclasses import dataclass, asdict, field
from typing import Optional

from core.llm import analyze_with_llm
from core.context import extract_context, detect_language
from core.context import extract_source_context, clear_cache


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

# ── Node.js / JavaScript Error Patterns ──────────────────────────
NODE_PATTERNS = {
    r"Error: Cannot find module '(.+?)'": {
        "root_cause": "Missing Node module: {m1}",
        "suggested_fix": "Run: npm install {m1}",
        "severity": "high",
    },
    r"TypeError: Cannot read propert(?:y|ies) of (undefined|null)": {
        "root_cause": "Accessed property on {m1} — object not initialized or missing",
        "suggested_fix": "Add null check or optional chaining (?.) before access",
        "severity": "high",
    },
    r"TypeError: (.+?) is not a function": {
        "root_cause": "{m1} is not callable — wrong type or undefined import",
        "suggested_fix": "Verify import/require path and that the export is a function",
        "severity": "high",
    },
    r"ReferenceError: (\S+) is not defined": {
        "root_cause": "Undeclared variable: {m1}",
        "suggested_fix": "Declare '{m1}' with let/const or check import",
        "severity": "medium",
    },
    r"SyntaxError: Unexpected token (.+)": {
        "root_cause": "Syntax error — unexpected token: {m1}",
        "suggested_fix": "Check for missing brackets, commas, or mismatched quotes near the error",
        "severity": "high",
    },
    r"RangeError: Maximum call stack size exceeded": {
        "root_cause": "Infinite recursion — call stack overflow",
        "suggested_fix": "Add base case to recursive function or convert to iterative",
        "severity": "critical",
    },
    r"ECONNREFUSED.+?(\d+\.\d+\.\d+\.\d+:\d+|\S+:\d+)": {
        "root_cause": "Connection refused to {m1}",
        "suggested_fix": "Verify target service is running and port is correct",
        "severity": "critical",
    },
    r"ENOENT.+?'(.+?)'": {
        "root_cause": "File/path not found: {m1}",
        "suggested_fix": "Verify path exists — check cwd and relative path resolution",
        "severity": "high",
    },
}

# ── Rust Error Patterns ──────────────────────────────────────────
RUST_PATTERNS = {
    r"thread '(.+?)' panicked at '(.+?)'": {
        "root_cause": "Thread '{m1}' panicked: {m2}",
        "suggested_fix": "Handle the error with Result/Option instead of unwrap/expect",
        "severity": "critical",
    },
    r"called `Option::unwrap\(\)` on a `None` value": {
        "root_cause": "Unwrapped None — Option was empty",
        "suggested_fix": "Use match/if-let or unwrap_or_default() instead of bare unwrap()",
        "severity": "critical",
    },
    r"called `Result::unwrap\(\)` on an `Err` value: (.+)": {
        "root_cause": "Unwrapped Err: {m1}",
        "suggested_fix": "Propagate with ? operator or handle with match/unwrap_or_else",
        "severity": "critical",
    },
    r"index out of bounds: the len is (\d+) but the index is (\d+)": {
        "root_cause": "Index out of bounds — length {m1}, tried index {m2}",
        "suggested_fix": "Use .get() for safe access or validate index before access",
        "severity": "high",
    },
    r"borrow of moved value: `(\S+)`": {
        "root_cause": "Used moved value '{m1}' — ownership already transferred",
        "suggested_fix": "Clone before move, use references, or restructure ownership",
        "severity": "high",
    },
    r"cannot borrow `(\S+)` as mutable .+ already borrowed as immutable": {
        "root_cause": "Borrow conflict on '{m1}' — simultaneous mutable + immutable borrow",
        "suggested_fix": "Restructure to separate borrow scopes or use RefCell/Cell",
        "severity": "high",
    },
}


def _extract_location(traceback_text: str) -> tuple:
    """Pull the last file/line/function from a traceback (multi-language)."""
    lang = detect_language(traceback_text)

    if lang == "python":
        matches = re.findall(
            r'File "(.+?)", line (\d+), in (.+)', traceback_text
        )
        if matches:
            last = matches[-1]
            return last[0], int(last[1]), last[2]

    elif lang == "node":
        # at functionName (/path/to/file.js:42:10)
        matches = re.findall(
            r'at\s+(\S+)\s+\((.+?):(\d+):\d+\)', traceback_text
        )
        if matches:
            # First frame is usually innermost for Node
            first = matches[0]
            return first[1], int(first[2]), first[0]
        # Anonymous: at /path/to/file.js:42:10
        matches = re.findall(r'at\s+(.+?):(\d+):\d+', traceback_text)
        if matches:
            first = matches[0]
            return first[0], int(first[1]), "<anonymous>"

    elif lang == "rust":
        matches = re.findall(r'(\S+\.rs):(\d+)', traceback_text)
        if matches:
            last = matches[-1]
            return last[0], int(last[1]), None

    return None, None, None


def _match_pattern(error_text: str, lang: str = "python") -> Optional[dict]:
    """Match error text against known patterns for the detected language."""
    # Select pattern sets based on language
    pattern_sets = [KNOWN_PATTERNS]  # Always try Python (universal fallback)
    if lang == "node":
        pattern_sets = [NODE_PATTERNS, KNOWN_PATTERNS]
    elif lang == "rust":
        pattern_sets = [RUST_PATTERNS, KNOWN_PATTERNS]

    for patterns in pattern_sets:
        for pattern, template in patterns.items():
            m = re.search(pattern, error_text)
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


def analyze(traceback_text: str, deep: bool = False, haiku: bool = False, project_path: str = None) -> DebugReport:
    """
    Quad-Tier Cascading Analysis with optional Project-Aware Mode.

    1. Regex match (Tier 1 — free/instant)
    2. If miss + default → xAI Grok Fast (Tier 2)
    3. If --haiku → Claude 3.5 Haiku (Tier 3)
    4. If --deep → Claude 3.7 Sonnet (Tier 4)

    If project_path is provided, scans the project for language, framework,
    and dependency context to inject into LLM prompts for precise fixes.
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

    # Detect language for multi-language routing
    lang = detect_language(traceback_text)

    # Extract surgical source context (±5 lines around each error frame)
    source_context = extract_source_context(traceback_text)

    # Project-Aware Mode: scan project for dependency/framework context
    project_context = ""
    if project_path:
        from core.project import get_project_profile
        profile = get_project_profile(project_path)
        project_context = profile.format_for_prompt()

    # TIER 4: Deep flag bypasses regex entirely
    if deep:
        llm_result = analyze_with_llm(traceback_text, deep=True, source_context=source_context, project_context=project_context)
        clear_cache()
        if llm_result and "root_cause" in llm_result:
            return _build_report_from_llm(
                llm_result, error_type, error_message,
                file_path, line_number, function_name, traceback_text
            )

    # TIER 3: Haiku flag bypasses regex entirely
    if haiku:
        llm_result = analyze_with_llm(traceback_text, haiku=True, source_context=source_context, project_context=project_context)
        clear_cache()
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
    llm_result = analyze_with_llm(traceback_text, source_context=source_context, project_context=project_context)
    clear_cache()
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


def analyze_to_json(traceback_text: str, deep: bool = False, haiku: bool = False, project_path: str = None) -> str:
    """Analyze and return JSON string."""
    report = analyze(traceback_text, deep=deep, haiku=haiku, project_path=project_path)
    d = asdict(report)
    d.pop("raw_traceback")
    return json.dumps(d, indent=2)
