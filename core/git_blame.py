"""
Git-Aware Blame + Diff Context — Who Broke It & When.

Integrates git blame and git log/diff into Rail Debug's analysis pipeline.
For each error frame, identifies:
  - Who last modified the error line (author, commit, timestamp)
  - Recent changes around the error location (diff context)
  - Commit message for the breaking change

Designed for surgical git queries — no full-repo scans. Uses subprocess
with targeted line ranges for minimal overhead.
"""

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from datetime import datetime

from core.context import extract_frames, detect_language


@dataclass
class BlameLine:
    """Git blame result for a single line."""
    commit_hash: str
    author: str
    author_email: str
    timestamp: str  # ISO-ish format
    line_number: int
    line_content: str
    commit_message: str = ""
    is_recent: bool = False  # Changed within last 7 days

    @property
    def short_hash(self) -> str:
        return self.commit_hash[:8]

    def format_compact(self) -> str:
        """One-line blame summary."""
        age = self._age_label()
        return f"{self.short_hash} ({self.author}, {age}) L{self.line_number}"

    def _age_label(self) -> str:
        """Human-readable age from timestamp."""
        try:
            ts = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
            delta = datetime.now(ts.tzinfo) - ts
            if delta.days == 0:
                return "today"
            elif delta.days == 1:
                return "yesterday"
            elif delta.days < 7:
                return f"{delta.days}d ago"
            elif delta.days < 30:
                return f"{delta.days // 7}w ago"
            elif delta.days < 365:
                return f"{delta.days // 30}mo ago"
            else:
                return f"{delta.days // 365}y ago"
        except (ValueError, TypeError):
            return self.timestamp


@dataclass
class DiffHunk:
    """A relevant diff hunk near the error location."""
    commit_hash: str
    author: str
    timestamp: str
    commit_message: str
    diff_text: str  # The actual diff lines
    file_path: str

    @property
    def short_hash(self) -> str:
        return self.commit_hash[:8]


@dataclass
class GitContext:
    """Complete git context for an error frame."""
    file_path: str
    line_number: int
    blame: Optional[BlameLine] = None
    recent_diffs: List[DiffHunk] = field(default_factory=list)
    repo_root: Optional[str] = None
    error: Optional[str] = None  # If git ops failed

    @property
    def has_context(self) -> bool:
        return self.blame is not None or len(self.recent_diffs) > 0

    def format_for_prompt(self) -> str:
        """Format git context for LLM injection."""
        if self.error:
            return f"[Git context unavailable: {self.error}]"

        parts = []

        if self.blame:
            parts.append(
                f"Git Blame (L{self.blame.line_number}): "
                f"{self.blame.short_hash} by {self.blame.author} "
                f"({self.blame._age_label()})"
            )
            if self.blame.commit_message:
                parts.append(f"  Commit: {self.blame.commit_message}")

        if self.recent_diffs:
            parts.append(f"Recent Changes ({len(self.recent_diffs)} commits touching this area):")
            for diff in self.recent_diffs[:3]:  # Cap at 3 for token budget
                parts.append(
                    f"  {diff.short_hash} by {diff.author}: {diff.commit_message}"
                )
                # Include compact diff (max 15 lines)
                diff_lines = diff.diff_text.strip().splitlines()
                if len(diff_lines) > 15:
                    diff_lines = diff_lines[:15] + ["  ... (truncated)"]
                parts.append("  " + "\n  ".join(diff_lines))

        return "\n".join(parts) if parts else "[No git context found]"

    def format_for_cli(self) -> str:
        """Human-readable git context for CLI output."""
        if self.error:
            return f"  ⚠️  Git: {self.error}"

        parts = []

        if self.blame:
            parts.append(
                f"  👤 Blame:    {self.blame.short_hash} — {self.blame.author} "
                f"({self.blame._age_label()})"
            )
            if self.blame.commit_message:
                msg = self.blame.commit_message
                if len(msg) > 60:
                    msg = msg[:57] + "..."
                parts.append(f"  💬 Commit:   {msg}")

        if self.recent_diffs:
            parts.append(f"  📝 Recent:   {len(self.recent_diffs)} commit(s) touched this area")
            for diff in self.recent_diffs[:2]:
                parts.append(f"             {diff.short_hash} — {diff.author}: {diff.commit_message[:50]}")

        return "\n".join(parts) if parts else ""


def _run_git(args: List[str], cwd: str, timeout: int = 5) -> Optional[str]:
    """Run a git command, return stdout or None on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _find_repo_root(file_path: str) -> Optional[str]:
    """Find the git repo root containing file_path."""
    directory = os.path.dirname(os.path.abspath(file_path))
    return _run_git(["rev-parse", "--show-toplevel"], cwd=directory)


def _get_blame(file_path: str, line_number: int, repo_root: str) -> Optional[BlameLine]:
    """
    Get git blame for a specific line.

    Uses --porcelain for machine-readable output with full metadata.
    Targets a single line range for minimal overhead.
    """
    abs_path = os.path.abspath(file_path)
    rel_path = os.path.relpath(abs_path, repo_root)

    output = _run_git(
        ["blame", "--porcelain", f"-L{line_number},{line_number}", "--", rel_path],
        cwd=repo_root,
    )

    if not output:
        return None

    return _parse_porcelain_blame(output, line_number)


def _parse_porcelain_blame(output: str, line_number: int) -> Optional[BlameLine]:
    """Parse git blame --porcelain output into a BlameLine."""
    lines = output.splitlines()
    if not lines:
        return None

    # First line: <hash> <orig_line> <final_line> <num_lines>
    first = lines[0].split()
    if not first:
        return None

    commit_hash = first[0]
    author = ""
    author_email = ""
    timestamp = ""
    content = ""
    commit_msg = ""

    for line in lines[1:]:
        if line.startswith("author "):
            author = line[7:]
        elif line.startswith("author-mail "):
            author_email = line[12:].strip("<>")
        elif line.startswith("author-time "):
            try:
                epoch = int(line[12:])
                timestamp = datetime.fromtimestamp(epoch).isoformat()
            except (ValueError, OSError):
                timestamp = line[12:]
        elif line.startswith("summary "):
            commit_msg = line[8:]
        elif line.startswith("\t"):
            content = line[1:]

    # Check if recent (within 7 days)
    is_recent = False
    try:
        ts = datetime.fromisoformat(timestamp)
        delta = datetime.now() - ts
        is_recent = delta.days < 7
    except (ValueError, TypeError):
        pass

    return BlameLine(
        commit_hash=commit_hash,
        author=author,
        author_email=author_email,
        timestamp=timestamp,
        line_number=line_number,
        line_content=content,
        commit_message=commit_msg,
        is_recent=is_recent,
    )


def _get_recent_diffs(
    file_path: str,
    line_number: int,
    repo_root: str,
    max_commits: int = 3,
    radius: int = 5,
) -> List[DiffHunk]:
    """
    Get recent diffs that touched the area around line_number.

    Uses git log -L for line-range history — shows exactly which commits
    modified the ±radius lines around the error.
    """
    abs_path = os.path.abspath(file_path)
    rel_path = os.path.relpath(abs_path, repo_root)

    start = max(1, line_number - radius)
    end = line_number + radius

    # git log -L start,end:file — line-range log
    output = _run_git(
        [
            "log", f"-{max_commits}",
            f"-L{start},{end}:{rel_path}",
            "--format=%H|%an|%aI|%s",
            "--no-patch",
        ],
        cwd=repo_root,
        timeout=10,
    )

    if not output:
        # Fallback: simple log for the file
        output = _run_git(
            [
                "log", f"-{max_commits}",
                "--format=%H|%an|%aI|%s",
                "--", rel_path,
            ],
            cwd=repo_root,
        )
        if not output:
            return []

    diffs = []
    for line in output.splitlines():
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue

        commit_hash, author, timestamp, message = parts

        # Get the actual diff for this commit on this file (compact)
        diff_output = _run_git(
            ["diff", f"{commit_hash}~1..{commit_hash}", "--", rel_path],
            cwd=repo_root,
        )

        # Extract only the relevant hunk (near our line range)
        diff_text = _extract_relevant_hunk(diff_output, line_number, radius) if diff_output else ""

        diffs.append(DiffHunk(
            commit_hash=commit_hash,
            author=author,
            timestamp=timestamp,
            commit_message=message,
            diff_text=diff_text,
            file_path=rel_path,
        ))

    return diffs


def _extract_relevant_hunk(diff_output: str, target_line: int, radius: int = 10) -> str:
    """
    Extract the diff hunk closest to target_line.

    Parses unified diff format to find the hunk that overlaps with
    the target line ± radius.
    """
    if not diff_output:
        return ""

    hunks = []
    current_hunk = []
    hunk_start = 0

    for line in diff_output.splitlines():
        hunk_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if hunk_match:
            if current_hunk:
                hunks.append((hunk_start, current_hunk))
            hunk_start = int(hunk_match.group(1))
            current_hunk = [line]
        elif current_hunk:
            current_hunk.append(line)

    if current_hunk:
        hunks.append((hunk_start, current_hunk))

    # Find the hunk that overlaps with target_line ± radius
    target_start = target_line - radius
    target_end = target_line + radius

    for start, hunk_lines in hunks:
        hunk_len = sum(1 for l in hunk_lines if not l.startswith("-"))
        hunk_end = start + hunk_len

        if start <= target_end and hunk_end >= target_start:
            return "\n".join(hunk_lines[:20])  # Cap at 20 lines

    # No overlapping hunk — return first hunk as fallback
    if hunks:
        return "\n".join(hunks[0][1][:15])

    return ""


def get_git_context(
    file_path: str,
    line_number: int,
    include_diffs: bool = True,
) -> GitContext:
    """
    Get complete git context for a file:line — blame + recent diffs.

    Args:
        file_path: Path to the file (absolute or relative)
        line_number: The error line number
        include_diffs: Whether to fetch recent diffs (more expensive)

    Returns:
        GitContext with blame info and optional diff history
    """
    abs_path = os.path.abspath(file_path)

    if not os.path.isfile(abs_path):
        return GitContext(
            file_path=file_path,
            line_number=line_number,
            error="File not found",
        )

    repo_root = _find_repo_root(abs_path)
    if not repo_root:
        return GitContext(
            file_path=file_path,
            line_number=line_number,
            error="Not in a git repository",
        )

    ctx = GitContext(
        file_path=file_path,
        line_number=line_number,
        repo_root=repo_root,
    )

    # Get blame for the error line
    ctx.blame = _get_blame(abs_path, line_number, repo_root)

    # Get recent diffs touching this area
    if include_diffs:
        ctx.recent_diffs = _get_recent_diffs(abs_path, line_number, repo_root)

    return ctx


def get_git_context_for_traceback(
    traceback_text: str,
    max_frames: int = 3,
    include_diffs: bool = True,
) -> List[GitContext]:
    """
    Extract git context for all frames in a traceback.

    Processes the last N frames (innermost = most relevant).
    Skips frames from stdlib/packages (non-local files).

    Args:
        traceback_text: Raw traceback string
        max_frames: Max frames to process (default 3)
        include_diffs: Whether to include diff history

    Returns:
        List of GitContext objects for accessible local frames
    """
    frames = extract_frames(traceback_text)
    if not frames:
        return []

    # Take innermost frames
    target_frames = frames[-max_frames:]

    contexts = []
    for file_path, line_number in target_frames:
        # Skip non-local files (stdlib, site-packages)
        if not os.path.isfile(file_path):
            continue
        abs_path = os.path.abspath(file_path)
        if "site-packages" in abs_path or "/lib/python" in abs_path:
            continue

        ctx = get_git_context(file_path, line_number, include_diffs=include_diffs)
        if ctx.has_context:
            contexts.append(ctx)

    return contexts


def format_git_context_for_prompt(contexts: List[GitContext]) -> str:
    """Format multiple GitContext objects for LLM prompt injection."""
    if not contexts:
        return ""

    parts = ["Git History (who changed what, when):"]
    for ctx in contexts:
        formatted = ctx.format_for_prompt()
        if formatted and not formatted.startswith("[No git"):
            parts.append(f"\n── {ctx.file_path}:{ctx.line_number} ──")
            parts.append(formatted)

    return "\n".join(parts) if len(parts) > 1 else ""
