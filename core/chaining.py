"""
Stack Trace Chaining — Exception Chain Parser & Analyzer.

Handles Python's exception chaining:
  - "The above exception was the direct cause of the following exception:" (__cause__)
  - "During handling of the above exception, another exception occurred:" (__context__)

Also handles Node.js "Caused by:" chains and Rust "caused by:" backtraces.

Splits chained tracebacks into individual links, preserves causal ordering,
and provides unified analysis across the entire chain.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

from core.context import detect_language


# ── Chain Boundary Patterns ──────────────────────────────────────

# Python explicit cause (__cause__ — raise X from Y)
PY_DIRECT_CAUSE = re.compile(
    r"^\s*The above exception was the direct cause of the following exception:\s*$",
    re.MULTILINE,
)

# Python implicit context (__context__ — exception during handling)
PY_IMPLICIT_CONTEXT = re.compile(
    r"^\s*During handling of the above exception, another exception occurred:\s*$",
    re.MULTILINE,
)

# Node.js/generic "Caused by:" pattern
NODE_CAUSED_BY = re.compile(
    r"^Caused by:\s*",
    re.MULTILINE,
)

# Rust "Caused by:" in error chain (e.g., anyhow, thiserror)
RUST_CAUSED_BY = re.compile(
    r"^Caused by:\s*$",
    re.MULTILINE,
)


@dataclass
class ChainLink:
    """A single exception in a chained traceback."""
    traceback_text: str
    relationship: str  # "root" | "direct_cause" | "implicit_context" | "caused_by"
    index: int  # 0 = outermost/first in text, last = final raised exception

    @property
    def error_line(self) -> str:
        """Extract the final error line from this link."""
        lines = self.traceback_text.strip().splitlines()
        return lines[-1] if lines else ""


@dataclass
class ExceptionChain:
    """An ordered chain of exceptions from a chained traceback."""
    links: List[ChainLink] = field(default_factory=list)
    language: str = "python"

    @property
    def is_chained(self) -> bool:
        return len(self.links) > 1

    @property
    def root_exception(self) -> Optional[ChainLink]:
        """The original exception that started the chain (first in text = deepest cause)."""
        return self.links[0] if self.links else None

    @property
    def final_exception(self) -> Optional[ChainLink]:
        """The exception that was ultimately raised (last in text)."""
        return self.links[-1] if self.links else None

    def format_chain_summary(self) -> str:
        """Human-readable chain summary for CLI output."""
        if not self.is_chained:
            return ""

        lines = [f"🔗 Exception Chain ({len(self.links)} linked errors):"]
        for i, link in enumerate(self.links):
            arrow = "  ╰→" if i > 0 else "  ●"
            rel_label = {
                "root": "ROOT CAUSE",
                "direct_cause": "caused →",
                "implicit_context": "during handling →",
                "caused_by": "caused by →",
            }.get(link.relationship, link.relationship)

            error = link.error_line
            if len(error) > 80:
                error = error[:77] + "..."

            lines.append(f"{arrow} [{rel_label}] {error}")

        return "\n".join(lines)


def parse_exception_chain(traceback_text: str) -> ExceptionChain:
    """
    Parse a chained traceback into individual ChainLink segments.

    Python chains read top-to-bottom as: original cause → ... → final exception.
    The first block is the root cause; the last block is what was actually raised.

    Returns an ExceptionChain with links ordered as they appear in text
    (index 0 = first/root, index N = final raised exception).
    """
    lang = detect_language(traceback_text)
    chain = ExceptionChain(language=lang)

    if lang == "python":
        chain.links = _parse_python_chain(traceback_text)
    elif lang == "node":
        chain.links = _parse_node_chain(traceback_text)
    elif lang == "rust":
        chain.links = _parse_rust_chain(traceback_text)
    else:
        # Unknown language — treat as single block
        chain.links = [ChainLink(
            traceback_text=traceback_text.strip(),
            relationship="root",
            index=0,
        )]

    return chain


def _parse_python_chain(traceback_text: str) -> List[ChainLink]:
    """
    Split Python chained tracebacks at cause/context boundaries.

    Python prints chains top-to-bottom:
      1. Original exception (root cause)
      2. Chain separator ("The above exception was the direct cause..." or "During handling...")
      3. Next exception
      ... repeat ...
      N. Final raised exception
    """
    # Find all chain boundary positions
    boundaries = []

    for m in PY_DIRECT_CAUSE.finditer(traceback_text):
        boundaries.append((m.start(), m.end(), "direct_cause"))

    for m in PY_IMPLICIT_CONTEXT.finditer(traceback_text):
        boundaries.append((m.start(), m.end(), "implicit_context"))

    if not boundaries:
        # No chaining — single traceback
        return [ChainLink(
            traceback_text=traceback_text.strip(),
            relationship="root",
            index=0,
        )]

    # Sort boundaries by position
    boundaries.sort(key=lambda x: x[0])

    links = []
    prev_end = 0

    for i, (start, end, relationship) in enumerate(boundaries):
        # Text before this boundary is a traceback block
        block = traceback_text[prev_end:start].strip()
        if block:
            rel = "root" if i == 0 else boundaries[i - 1][2]
            links.append(ChainLink(
                traceback_text=block,
                relationship="root" if i == 0 else rel,
                index=len(links),
            ))
        prev_end = end

    # Final block after last boundary = the ultimately raised exception
    final_block = traceback_text[prev_end:].strip()
    if final_block:
        links.append(ChainLink(
            traceback_text=final_block,
            relationship=boundaries[-1][2],
            index=len(links),
        ))

    return links


def _parse_node_chain(traceback_text: str) -> List[ChainLink]:
    """Split Node.js 'Caused by:' chains."""
    parts = NODE_CAUSED_BY.split(traceback_text)

    if len(parts) <= 1:
        return [ChainLink(
            traceback_text=traceback_text.strip(),
            relationship="root",
            index=0,
        )]

    links = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        links.append(ChainLink(
            traceback_text=part,
            relationship="root" if i == 0 else "caused_by",
            index=len(links),
        ))

    return links


def _parse_rust_chain(traceback_text: str) -> List[ChainLink]:
    """Split Rust 'Caused by:' error chains (anyhow, thiserror)."""
    parts = RUST_CAUSED_BY.split(traceback_text)

    if len(parts) <= 1:
        return [ChainLink(
            traceback_text=traceback_text.strip(),
            relationship="root",
            index=0,
        )]

    links = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        links.append(ChainLink(
            traceback_text=part,
            relationship="root" if i == 0 else "caused_by",
            index=len(links),
        ))

    return links


def is_chained_traceback(traceback_text: str) -> bool:
    """Quick check: does this traceback contain exception chaining?"""
    return bool(
        PY_DIRECT_CAUSE.search(traceback_text)
        or PY_IMPLICIT_CONTEXT.search(traceback_text)
        or NODE_CAUSED_BY.search(traceback_text)
        or RUST_CAUSED_BY.search(traceback_text)
    )
