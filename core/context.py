"""
Codebase Context Injection — Surgical Source Reader.

Parses file paths and line numbers from Python tracebacks,
then extracts a targeted ±5 line window using linecache.
Zero full-file reads. Injects only what the LLM needs.
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


# Pattern to extract file/line from traceback frames
FRAME_PATTERN = re.compile(r'File "(.+?)", line (\d+)')

# Default context window: ±5 lines around the error
CONTEXT_RADIUS = 5


def extract_frames(traceback_text: str) -> List[tuple]:
    """
    Extract (file_path, line_number) pairs from a traceback.
    Returns all frames in order (outermost to innermost).
    """
    return [
        (m.group(1), int(m.group(2)))
        for m in FRAME_PATTERN.finditer(traceback_text)
    ]


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
