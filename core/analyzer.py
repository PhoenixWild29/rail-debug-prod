"""
Core error analyzer — Quad-Tier Universal Cascading Engine.

Supports Python, Node.js/JavaScript, Rust, Go, Java/Kotlin, and Solidity.

Tier 1: Regex patterns (instant/free) — all 6 languages
Tier 2: xAI Grok Fast (cheap/fast default LLM)
Tier 3: Anthropic Claude Haiku 4.5 (mid-tier via --haiku)
Tier 4: Anthropic Claude Sonnet 4.6 (deep reasoning via --deep)
"""

import os
import re
import json
from dataclasses import dataclass, asdict, field
from typing import Optional

from core.llm import analyze_with_llm
from core.context import extract_context, detect_language
from core.context import extract_source_context, clear_cache
from core.chaining import parse_exception_chain, is_chained_traceback, ExceptionChain
from core.git_blame import get_git_context_for_traceback, format_git_context_for_prompt

from core.memory import query_similar, insert_analysis
from utils.normalize import normalize_traceback


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
    git_blame: Optional[str] = None  # Compact blame summary for CLI
    git_context_raw: Optional[list] = field(default=None, repr=False)  # Raw GitContext objects (not serialized)


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

# ── Go Error Patterns ─────────────────────────────────────────────
GO_PATTERNS = {
    r"panic: runtime error: integer divide by zero": {
        "root_cause": "Division by zero at runtime",
        "suggested_fix": "Guard before dividing: if divisor == 0 { return/error }",
        "severity": "critical",
    },
    r"panic: runtime error: index out of range \[(\d+)\] with length (\d+)": {
        "root_cause": "Index out of range — accessed index {m1}, slice length is {m2}",
        "suggested_fix": "Validate index before access: if i < len(slice) { ... }",
        "severity": "critical",
    },
    r"panic: runtime error: invalid memory address or nil pointer dereference": {
        "root_cause": "Nil pointer dereference — dereferenced an uninitialized pointer",
        "suggested_fix": "Check for nil before use: if ptr != nil { ... }",
        "severity": "critical",
    },
    r"panic: (.+)": {
        "root_cause": "Go panic: {m1}",
        "suggested_fix": "Use defer/recover for panic recovery, or fix the underlying condition",
        "severity": "critical",
    },
    r"all goroutines are asleep - deadlock!": {
        "root_cause": "Goroutine deadlock — all goroutines blocked waiting on each other",
        "suggested_fix": "Check channel send/receive symmetry and mutex lock/unlock pairs",
        "severity": "critical",
    },
    r"interface conversion: interface \{\} is (.+?), not (.+)": {
        "root_cause": "Type assertion failed — value is {m1}, expected {m2}",
        "suggested_fix": "Use two-value assertion: v, ok := x.({type}); if !ok { handle }",
        "severity": "high",
    },
}

# ── Java / Kotlin Error Patterns ──────────────────────────────────
JAVA_PATTERNS = {
    r"java\.lang\.NullPointerException": {
        "root_cause": "Null pointer exception — method or field accessed on null object",
        "suggested_fix": "Add null check before use, or use Optional<> for nullable values",
        "severity": "critical",
    },
    r"java\.lang\.ArrayIndexOutOfBoundsException: Index (\d+) out of bounds for length (\d+)": {
        "root_cause": "Array index {m1} out of bounds — array length is {m2}",
        "suggested_fix": "Check index < array.length before access",
        "severity": "high",
    },
    r"java\.lang\.ClassCastException: class (.+?) cannot be cast to class (.+?)": {
        "root_cause": "Cannot cast {m1} to {m2} — incompatible types",
        "suggested_fix": "Use instanceof check before casting: if (obj instanceof TargetType t) { ... }",
        "severity": "high",
    },
    r"java\.lang\.StackOverflowError": {
        "root_cause": "Stack overflow — infinite or excessively deep recursion",
        "suggested_fix": "Add base case to recursive method or convert to iterative with explicit stack",
        "severity": "critical",
    },
    r"java\.lang\.OutOfMemoryError: Java heap space": {
        "root_cause": "JVM heap exhausted — insufficient memory for allocation",
        "suggested_fix": "Increase heap with -Xmx flag, fix memory leaks, or reduce object retention",
        "severity": "critical",
    },
    r"java\.io\.FileNotFoundException: (.+)": {
        "root_cause": "File not found: {m1}",
        "suggested_fix": "Verify file path — check working directory and path separators",
        "severity": "high",
    },
    r"java\.util\.ConcurrentModificationException": {
        "root_cause": "Collection modified while iterating — concurrent modification detected",
        "suggested_fix": "Use Iterator.remove() or CopyOnWriteArrayList for safe concurrent iteration",
        "severity": "high",
    },
    r"java\.lang\.IllegalArgumentException: (.+)": {
        "root_cause": "Illegal argument: {m1}",
        "suggested_fix": "Validate input before passing to the method",
        "severity": "medium",
    },
    r"kotlin\.KotlinNullPointerException": {
        "root_cause": "Kotlin null pointer exception — non-null type received null value",
        "suggested_fix": "Use nullable type (Type?) with safe call (?.) or Elvis operator (?:)",
        "severity": "critical",
    },
    r"kotlin\.UninitializedPropertyAccessException: (.+)": {
        "root_cause": "Property accessed before initialization: {m1}",
        "suggested_fix": "Ensure lateinit var is initialized before access, or switch to lazy { }",
        "severity": "high",
    },
}

# ── Solidity / EVM Error Patterns ─────────────────────────────────
SOLIDITY_PATTERNS = {
    r"revert(?:ed)?\s+(?:with reason string\s+)?['\"](.+?)['\"]": {
        "root_cause": "Transaction reverted: {m1}",
        "suggested_fix": "Check the require/revert condition — caller must meet contract preconditions",
        "severity": "critical",
    },
    r"Transaction reverted without a reason": {
        "root_cause": "Transaction reverted with no reason string — bare revert() or failed require(false)",
        "suggested_fix": "Add descriptive reason to require(): require(condition, 'Descriptive reason')",
        "severity": "critical",
    },
    r"out of gas": {
        "root_cause": "Transaction ran out of gas",
        "suggested_fix": "Increase gas limit, optimize loops/storage ops, or use estimateGas first",
        "severity": "critical",
    },
    r"invalid opcode": {
        "root_cause": "Invalid EVM opcode — usually a failing assert() or division by zero in Solidity < 0.8",
        "suggested_fix": "Check assert() conditions and division-by-zero guards in the contract",
        "severity": "critical",
    },
    r"execution reverted": {
        "root_cause": "EVM execution reverted — a require(), revert(), or assert() condition failed",
        "suggested_fix": "Inspect the failing condition — add reason strings to require() for easier debugging",
        "severity": "critical",
    },
    r"SafeMath: (.+)": {
        "root_cause": "SafeMath overflow/underflow: {m1}",
        "suggested_fix": "Solidity >= 0.8 has built-in overflow protection. For older versions, upgrade or use checked arithmetic",
        "severity": "critical",
    },
    r"caller is not the owner": {
        "root_cause": "Access control failure — caller is not the contract owner",
        "suggested_fix": "Ensure the calling address is the contract owner, or review onlyOwner modifier logic",
        "severity": "critical",
    },
}


def _get_error_line(traceback_text: str, lang: str) -> str:
    """Extract the most relevant error line based on language conventions."""
    lines = [l for l in traceback_text.strip().splitlines() if l.strip()]
    if not lines:
        return ""

    # Go: panic line first (before goroutine header)
    if lang == "go":
        for line in lines:
            if line.strip().startswith("panic:"):
                return line.strip()
        return lines[0].strip()

    # Java/Kotlin: first line contains exception class (may be preceded by "Exception in thread...")
    if lang == "java":
        for line in lines:
            line = line.strip()
            if re.match(r'(?:java|kotlin|android)\.', line):
                return line
            m = re.search(r'Exception in thread "[^"]+" (.+)', line)
            if m:
                return m.group(1)
        return lines[0].strip()

    # Solidity: look for the revert/error line
    if lang == "solidity":
        for line in lines:
            line = line.strip()
            if any(kw in line.lower() for kw in ("revert", "out of gas", "invalid opcode", "execution reverted")):
                return line
        return lines[0].strip()

    # Python/Node/Rust: error is on the last line
    return lines[-1]


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

    elif lang == "go":
        # Tab-indented: \t/path/to/file.go:42
        matches = re.findall(r'\t(.+\.go):(\d+)', traceback_text)
        if matches:
            last = matches[-1]
            return last[0], int(last[1]), None

    elif lang == "java":
        # at com.example.Class.method(File.java:42) — first frame is innermost
        matches = re.findall(r'at\s+(\S+)\(([\w./\-$]+\.(?:java|kt)):(\d+)\)', traceback_text)
        if matches:
            first = matches[0]
            method = first[0].split(".")[-1]  # Last segment = method name
            return first[1], int(first[2]), method

    elif lang == "solidity":
        # --> contracts/Contract.sol:42:5 (solc format)
        matches = re.findall(r'-->\s+(.+\.sol):(\d+)', traceback_text)
        if matches:
            first = matches[0]
            return first[0], int(first[1]), None

    return None, None, None


def _match_pattern(error_text: str, lang: str = "python") -> Optional[dict]:
    """Match error text against known patterns for the detected language."""
    # Select pattern sets based on language
    pattern_sets = [KNOWN_PATTERNS]  # Always try Python (universal fallback)
    if lang == "node":
        pattern_sets = [NODE_PATTERNS, KNOWN_PATTERNS]
    elif lang == "rust":
        pattern_sets = [RUST_PATTERNS, KNOWN_PATTERNS]
    elif lang == "go":
        pattern_sets = [GO_PATTERNS]
    elif lang == "java":
        pattern_sets = [JAVA_PATTERNS]
    elif lang == "solidity":
        pattern_sets = [SOLIDITY_PATTERNS]

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


def analyze(traceback_text: str, deep: bool = False, haiku: bool = False, project_path: str = None, no_git: bool = False, use_memory: bool = True) -> DebugReport:
    """
    Quad-Tier Cascading Analysis with optional Project-Aware Mode.

    1. Regex match (Tier 1 — free/instant)
    2. If miss + default → xAI Grok Fast (Tier 2)
    3. If --haiku → Claude 3.5 Haiku (Tier 3)
    4. If --deep → Claude 3.7 Sonnet (Tier 4)

    If project_path is provided, scans the project for language, framework,
    and dependency context to inject into LLM prompts for precise fixes.
    """
    # Detect language first — needed for error line extraction
    lang = detect_language(traceback_text)

    error_line = _get_error_line(traceback_text, lang)

    if ":" in error_line:
        error_type, _, error_message = error_line.partition(":")
        error_type = error_type.strip()
        error_message = error_message.strip()
    else:
        error_type = error_line.strip()
        error_message = ""

    file_path, line_number, function_name = _extract_location(traceback_text)

    # Extract surgical source context (±5 lines around each error frame)
    source_context = extract_source_context(traceback_text)

    # Git-Aware Mode: blame + diff context for error frames
    git_disabled = no_git or os.environ.get("RAIL_NO_GIT", "")
    if git_disabled:
        git_contexts = []
        git_prompt_context = ""
    else:
        git_contexts = get_git_context_for_traceback(traceback_text, max_frames=3)
        git_prompt_context = format_git_context_for_prompt(git_contexts)

    # Project-Aware Mode: scan project for dependency/framework context
    project_context = ""
    if project_path:
        from core.project import get_project_profile
        profile = get_project_profile(project_path)
        project_context = profile.format_for_prompt()
    
    tb_hash, tb_snippet = normalize_traceback(traceback_text)
    past_context = ""
    if use_memory:
        past_analyses = query_similar(tb_snippet)
        if past_analyses:
            past_context = "Past similar analyses:\n" + "\n".join(
                f"Language: {r['language']}, Severity: {r['severity']}, Cause: {r['root_cause'][:100]}..., Fix: {r['suggested_fix'][:100]}... (conf: {r['confidence']:.1f}, success: {r['success']})"
                for r in past_analyses
            )

    # Combine all context for LLM
    full_source_context = source_context or ""
    if git_prompt_context:
        full_source_context = (full_source_context + "\n\n" + git_prompt_context).strip() if full_source_context else git_prompt_context

    # Helper to attach git info to reports
    def _attach_git(report: DebugReport) -> DebugReport:
        if git_contexts:
            blame_lines = []
            for gc in git_contexts:
                if gc.blame:
                    blame_lines.append(gc.blame.format_compact())
            report.git_blame = " | ".join(blame_lines) if blame_lines else None
            report.git_context_raw = git_contexts
        return report

    # TIER 4: Deep flag bypasses regex entirely
    if deep:
        llm_result = analyze_with_llm(traceback_text, deep=True, source_context=full_source_context, project_context=project_context)
        clear_cache()
        if llm_result and "root_cause" in llm_result:
            return _attach_git(_build_report_from_llm(
                llm_result, error_type, error_message,
                file_path, line_number, function_name, traceback_text
            ))

    # TIER 3: Haiku flag bypasses regex entirely
    if haiku:
        llm_result = analyze_with_llm(traceback_text, haiku=True, source_context=full_source_context, project_context=project_context)
        clear_cache()
        if llm_result and "root_cause" in llm_result:
            return _attach_git(_build_report_from_llm(
                llm_result, error_type, error_message,
                file_path, line_number, function_name, traceback_text
            ))

    # TIER 1: Regex — Go/Java/Solidity errors appear at top of traceback, not last line
    match_text = traceback_text if lang in ("go", "java", "solidity", "rust") else error_line
    matched = _match_pattern(match_text, lang)
    if matched:
        return _attach_git(DebugReport(
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
        ))

    # TIER 2: Grok Fast fallback
    llm_result = analyze_with_llm(traceback_text, source_context=full_source_context, project_context=project_context)
    clear_cache()
    if llm_result and "root_cause" in llm_result:
        return _attach_git(_build_report_from_llm(
            llm_result, error_type, error_message,
            file_path, line_number, function_name, traceback_text
        ))

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
    d.pop("git_context_raw", None)  # Not serializable — use git_blame string instead
    return json.dumps(d, indent=2)


@dataclass
class ChainedDebugReport:
    """Analysis result for a chained exception — multiple linked reports."""
    chain_summary: str
    reports: list  # List[DebugReport] — one per chain link
    root_cause_report: Optional[DebugReport] = None
    final_report: Optional[DebugReport] = None
    is_chained: bool = True

    def to_json(self) -> str:
        results = []
        for r in self.reports:
            d = asdict(r)
            d.pop("raw_traceback")
            results.append(d)
        return json.dumps({
            "chain_summary": self.chain_summary,
            "errors": results,
            "total_linked": len(results),
        }, indent=2)


def analyze_chained(
    traceback_text: str,
    deep: bool = False,
    haiku: bool = False,
    project_path: str = None,
) -> ChainedDebugReport:
    """
    Analyze a chained traceback — parse the chain, analyze each link,
    and return a unified ChainedDebugReport.

    If the traceback is NOT chained, wraps the single analysis in a
    ChainedDebugReport for uniform handling.
    """
    chain = parse_exception_chain(traceback_text)

    reports = []
    for link in chain.links:
        report = analyze(link.traceback_text, deep=deep, haiku=haiku, project_path=project_path)
        reports.append(report)

    return ChainedDebugReport(
        chain_summary=chain.format_chain_summary(),
        reports=reports,
        root_cause_report=reports[0] if reports else None,
        final_report=reports[-1] if reports else None,
        is_chained=chain.is_chained,
    )
