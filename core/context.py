"""
Codebase Context Injection — surgical source code extraction.

Parses file paths and line numbers from tracebacks, then extracts
a targeted window (±5 lines) using linecache. Injects only the
relevant source context into LLM prompts — never full files.
"""

import linecache
import os
import re
from typing import List, Optional


# Match Python traceback file references
FILE_LINE_PATTERN = re.compile(r'File "(.+?)", line (\d+)')

# Context window: 5 lines above and below the error line
CONTEXT_WINDOW = 5


def _extract_file_refs(traceback_text: str) -> List[dict]:
    """
    Extract all file/line references from a traceback.

    Returns list of dicts with 'file', 'line' keys, ordered as they
    appear in the traceback (deepest/most relevant frame is last).
    """
    refs = []
    for match in FILE_LINE_PATTERN.finditer(traceback_text):
        file_path = match.group(1)
        line_num = int(match.group(2))
        refs.append({"file": file_path, "line": line_num})
    return refs


def _read_context_window(file_path: str, line_num: int, window: int = CONTEXT_WINDOW) -> Optional[str]:
    """
    Read a targeted window of source code around the error line.

    Uses linecache for efficient, cached line access.
    Returns formatted string with line numbers, or None if file unreadable.
    """
    if not os.path.isfile(file_path):
        return None

    start = max(1, line_num - window)
    end = line_num + window

    lines = []
    for i in range(start, end + 1):
        source_line = linecache.getline(file_path, i)
        if not source_line and i > line_num:
            break
        if source_line:
            marker = " >>>" if i == line_num else "    "
            lines.append(f"{marker} {i:4d} | {source_line.rstrip()}")

    if not lines:
        return None

    return "\n".join(lines)


def extract_source_context(traceback_text: str, max_frames: int = 3) -> str:
    """
    Extract source context for the most relevant frames in a traceback.

    Focuses on the last N frames (closest to the error) since those
    are most diagnostic. Returns a formatted string ready for LLM injection.

    Args:
        traceback_text: Raw traceback string
        max_frames: Maximum number of frames to extract context for (default 3)

    Returns:
        Formatted source context string, or empty string if no files readable
    """
    refs = _extract_file_refs(traceback_text)

    if not refs:
        return ""

    # Take the last N frames (most relevant, closest to error)
    relevant_refs = refs[-max_frames:]

    sections = []
    seen_files = set()

    for ref in relevant_refs:
        file_path = ref["file"]
        line_num = ref["line"]

        # Deduplicate same file/line
        key = f"{file_path}:{line_num}"
        if key in seen_files:
            continue
        seen_files.add(key)

        context = _read_context_window(file_path, line_num)
        if context:
            sections.append(
                f"── {os.path.basename(file_path)} (line {line_num}) ──\n{context}"
            )

    if not sections:
        return ""

    return "\n\n".join(sections)


def clear_cache():
    """Clear linecache. Call after analyzing a batch to free memory."""
    linecache.clearcache()
