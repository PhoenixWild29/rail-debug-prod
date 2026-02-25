"""
Codebase Context Injection — Universal Surgical Source Reader.

Parses file paths and line numbers from Python, Node.js/JavaScript,
and Rust tracebacks, then extracts a targeted ±5 line window using
linecache. Zero full-file reads. Injects only what the LLM needs.
"""

import linecache
import os
import re
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class SourceContext:
    """A window of source code surrounding an error location."""
    file_path: str
    error_line: int
    start_line: int
    end_line: int
    source_lines: List[str]
    exists: bool

    def format_for_prompt(self) -> str:
        """Format source context for LLM injection."""
        if not self.exists or not self.source_lines:
            return f"[Source file not accessible: {self.file_path}]"

        header = f"── {self.file_path} (lines {self.start_line}-{self.end_line}) ──"
        lines = []
        for i, line in enumerate(self.source_lines):
            line_num = self.start_line + i
            marker = ">>>" if line_num == self.error_line else "   "
            lines.append(f"{marker} {line_num:4d} | {line}")
        return f"{header}\n" + "\n".join(lines)


# ── Multi-Language Frame Parsers ──────────────────────────────────

# Python: File "path.py", line 42
PYTHON_FRAME = re.compile(r'File "(.+?)", line (\d+)')

# Node.js/JavaScript: at functionName (path.js:42:10) or at path.js:42:10
NODE_FRAME = re.compile(r'at\s+(?:.+?\s+\()?(.+?):(\d+):\d+\)?')

# Rust: thread 'main' panicked ... src/main.rs:42:5
# Also matches backtrace frames like: 0: app::module::function at ./src/main.rs:42:5
RUST_FRAME = re.compile(r'(?:at\s+)?(\S+\.rs):(\d+)(?::\d+)?')

# Go: tab-indented file reference in goroutine/panic output
#   \t/path/to/main.go:42 +0x18
GO_FRAME = re.compile(r'\t(.+\.go):(\d+)')

# Java/Kotlin: at com.example.Class.method(File.java:42) or (File.kt:42)
JAVA_FRAME = re.compile(r'at\s+\S+\(([\w./\-$]+\.(?:java|kt)):(\d+)\)')

# Solidity: --> contracts/MyContract.sol:42:5 (solc compiler error format)
SOLIDITY_FRAME = re.compile(r'-->\s+(.+\.sol):(\d+)')

# Default context window: ±5 lines around the error
CONTEXT_RADIUS = 5

# Supported languages and their detection heuristics
LANGUAGE_SIGNATURES = {
    "python": [r'Traceback \(most recent call last\)', r'File ".+?", line \d+'],
    "node": [r'at\s+.+?\(.+?:\d+:\d+\)', r'at\s+\S+:\d+:\d+', r'Error:.*\n\s+at\s'],
    "rust": [r"thread '.*' panicked", r'\.rs:\d+:\d+', r'stack backtrace:'],
    "go": [r'goroutine \d+ \[', r'\.go:\d+', r'panic:'],
    "java": [r'Exception in thread "', r'at \S+\([\w$]+\.(?:java|kt):\d+\)', r'(?:java|kotlin)\.'],
    "solidity": [r'execution reverted', r'Transaction reverted', r'out of gas', r'\.sol:\d+'],
}


def detect_language(traceback_text: str) -> str:
    """
    Auto-detect the language/runtime from traceback format.
    Returns: 'python' | 'node' | 'rust' | 'go' | 'java' | 'solidity' | 'unknown'
    """
    scores = {}
    for lang, patterns in LANGUAGE_SIGNATURES.items():
        score = sum(1 for p in patterns if re.search(p, traceback_text))
        if score > 0:
            scores[lang] = score

    if not scores:
        return "unknown"

    return max(scores, key=scores.get)


def extract_frames_python(traceback_text: str) -> List[tuple]:
    """Extract (file_path, line_number) from Python tracebacks."""
    return [
        (m.group(1), int(m.group(2)))
        for m in PYTHON_FRAME.finditer(traceback_text)
    ]


def extract_frames_node(traceback_text: str) -> List[tuple]:
    """
    Extract (file_path, line_number) from Node.js/JavaScript stack traces.
    Filters out node internals (node:, <anonymous>) to focus on user code.
    """
    frames = []
    for m in NODE_FRAME.finditer(traceback_text):
        path = m.group(1)
        # Skip node internals and anonymous frames
        if path.startswith("node:") or path.startswith("<"):
            continue
        frames.append((path, int(m.group(2))))
    return frames


def extract_frames_rust(traceback_text: str) -> List[tuple]:
    """
    Extract (file_path, line_number) from Rust panic/backtrace output.
    Filters out stdlib frames to focus on user crate code.
    """
    frames = []
    for m in RUST_FRAME.finditer(traceback_text):
        path = m.group(1)
        # Skip rustc stdlib internals
        if "/rustc/" in path or "library/std" in path:
            continue
        frames.append((path, int(m.group(2))))
    return frames


def extract_frames_go(traceback_text: str) -> List[tuple]:
    """
    Extract (file_path, line_number) from Go goroutine/panic output.
    Filters out Go stdlib frames to focus on user code.
    """
    frames = []
    for m in GO_FRAME.finditer(traceback_text):
        path = m.group(1)
        # Skip Go stdlib internals
        if "/usr/local/go/" in path or "GOROOT" in path:
            continue
        frames.append((path, int(m.group(2))))
    return frames


def extract_frames_java(traceback_text: str) -> List[tuple]:
    """
    Extract (file_path, line_number) from Java/Kotlin JVM stack traces.
    Handles both .java and .kt source files.
    """
    frames = []
    for m in JAVA_FRAME.finditer(traceback_text):
        frames.append((m.group(1), int(m.group(2))))
    return frames


def extract_frames_solidity(traceback_text: str) -> List[tuple]:
    """
    Extract (file_path, line_number) from Solidity/solc compiler error output.
    Format: --> contracts/MyContract.sol:42:5
    """
    frames = []
    for m in SOLIDITY_FRAME.finditer(traceback_text):
        frames.append((m.group(1), int(m.group(2))))
    return frames


def extract_frames(traceback_text: str) -> List[tuple]:
    """
    Universal frame extractor — auto-detects language and routes
    to the correct parser. Returns (file_path, line_number) pairs.
    """
    lang = detect_language(traceback_text)

    if lang == "python":
        return extract_frames_python(traceback_text)
    elif lang == "node":
        return extract_frames_node(traceback_text)
    elif lang == "rust":
        return extract_frames_rust(traceback_text)
    elif lang == "go":
        return extract_frames_go(traceback_text)
    elif lang == "java":
        return extract_frames_java(traceback_text)
    elif lang == "solidity":
        return extract_frames_solidity(traceback_text)

    # Unknown — try all parsers, return first non-empty result
    for parser in (extract_frames_python, extract_frames_node, extract_frames_rust,
                   extract_frames_go, extract_frames_java):
        frames = parser(traceback_text)
        if frames:
            return frames

    return []


def read_source_window(
    file_path: str,
    line_number: int,
    radius: int = CONTEXT_RADIUS,
) -> SourceContext:
    """
    Read a ±radius line window around line_number using linecache.

    linecache is ideal here — it caches reads, handles missing files
    gracefully, and never loads the entire file into our context.
    """
    start = max(1, line_number - radius)
    end = line_number + radius

    # Check file exists before burning linecache calls
    exists = os.path.isfile(file_path)
    if not exists:
        return SourceContext(
            file_path=file_path,
            error_line=line_number,
            start_line=start,
            end_line=end,
            source_lines=[],
            exists=False,
        )

    lines = []
    actual_end = start
    for i in range(start, end + 1):
        line = linecache.getline(file_path, i)
        if line:
            lines.append(line.rstrip())
            actual_end = i
        elif i > line_number:
            # Past end of file
            break

    # Clear linecache to avoid stale reads on watched files
    linecache.clearcache()

    return SourceContext(
        file_path=file_path,
        error_line=line_number,
        start_line=start,
        end_line=actual_end,
        source_lines=lines,
        exists=True,
    )


def extract_context(
    traceback_text: str,
    max_frames: int = 3,
    radius: int = CONTEXT_RADIUS,
) -> Optional[str]:
    """
    Extract source context from a traceback for LLM prompt injection.

    Reads the last N frames (innermost = most relevant) and builds
    a formatted context block. Returns None if no frames found or
    no files are accessible.

    Args:
        traceback_text: Raw traceback string
        max_frames: Maximum number of frames to include (default 3, innermost)
        radius: Lines above/below error to include (default 5)
    """
    frames = extract_frames(traceback_text)
    if not frames:
        return None

    # Take the last max_frames (innermost frames are most relevant)
    target_frames = frames[-max_frames:]

    contexts = []
    for file_path, line_number in target_frames:
        ctx = read_source_window(file_path, line_number, radius)
        if ctx.exists and ctx.source_lines:
            contexts.append(ctx.format_for_prompt())

    if not contexts:
        return None

    return "\n\n".join(contexts)


# Aliases for backward compatibility with analyzer imports
extract_source_context = extract_context


def clear_cache():
    """Clear linecache to avoid stale reads on watched files."""
    linecache.clearcache()
