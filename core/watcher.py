"""
Watch Mode Sentinel — real-time log file monitoring with watchdog.

Uses watchdog for filesystem event detection (replaces manual tail-follow).
Detects Python tracebacks as they appear and routes through Quad-Tier Analyzer.
"""

import os
import re
import time
import signal
import sys
from typing import Optional, Callable

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

from core.analyzer import analyze


# Traceback detection patterns
TRACEBACK_START = re.compile(r"^Traceback \(most recent call last\):")
TRACEBACK_FILE_LINE = re.compile(r"^\s+File ")
ERROR_LINE = re.compile(r"^[A-Za-z][\w.]*(?:Error|Exception|Warning|Exit).*:")


class _LogHandler(FileSystemEventHandler):
    """Watchdog handler that triggers on file modifications."""

    def __init__(self, sentinel):
        super().__init__()
        self.sentinel = sentinel

    def on_modified(self, event):
        if event.src_path == self.sentinel.filepath:
            self.sentinel._read_new_lines()


class Sentinel:
    """
    Real-time log watcher that detects and analyzes tracebacks.

    Uses watchdog for efficient filesystem monitoring when available,
    falls back to tail-follow polling if watchdog is not installed.
    """

    def __init__(
        self,
        filepath: str,
        deep: bool = False,
        haiku: bool = False,
        json_output: bool = False,
        callback: Optional[Callable] = None,
        project_path: Optional[str] = None,
    ):
        self.filepath = os.path.abspath(filepath)
        self.deep = deep
        self.haiku = haiku
        self.json_output = json_output
        self.callback = callback
        self.project_path = project_path
        self._running = False
        self._buffer = []
        self._in_traceback = False
        self._error_count = 0
        self._file_pos = 0

    def _flush_traceback(self):
        """Process a completed traceback from the buffer."""
        if not self._buffer:
            return

        traceback_text = "\n".join(self._buffer)
        self._buffer = []
        self._in_traceback = False
        self._error_count += 1

        timestamp = time.strftime("%H:%M:%S")

        if self.json_output:
            from core.analyzer import analyze_to_json
            print(f"\n[{timestamp}] 🚨 Error #{self._error_count} detected:")
            print(analyze_to_json(traceback_text, deep=self.deep, haiku=self.haiku, project_path=self.project_path))
        else:
            report = analyze(traceback_text, deep=self.deep, haiku=self.haiku, project_path=self.project_path)
            if self.callback:
                self.callback(report)
            else:
                self._default_format(report, timestamp)

    def _default_format(self, report, timestamp):
        """Pretty-print a detected error."""
        severity_icons = {
            "low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"
        }
        tier_labels = {
            0: "OFFLINE", 1: "Regex", 2: "Grok", 3: "Haiku", 4: "Sonnet"
        }
        icon = severity_icons.get(report.severity, "⚪")
        tier = tier_labels.get(report.tier, f"T{report.tier}")

        print(f"\n{'─' * 50}")
        print(f"[{timestamp}] {icon} Error #{self._error_count} | {tier}")
        print(f"  ❌ {report.error_type}: {report.error_message}")
        print(f"  🧠 {report.root_cause}")
        print(f"  ✅ {report.suggested_fix}")
        if report.file_path:
            print(f"  📂 {report.file_path}:{report.line_number}")
        if report.architecture_notes:
            print(f"  🏗️  {report.architecture_notes}")
        print(f"{'─' * 50}")

    def _process_line(self, line: str):
        """State machine: detect traceback boundaries."""
        stripped = line.rstrip()

        if TRACEBACK_START.match(stripped):
            if self._in_traceback and self._buffer:
                self._flush_traceback()
            self._in_traceback = True
            self._buffer = [stripped]
            return

        if self._in_traceback:
            self._buffer.append(stripped)
            if stripped and not stripped.startswith(" ") and not TRACEBACK_START.match(stripped):
                if ERROR_LINE.match(stripped) or not TRACEBACK_FILE_LINE.match(stripped):
                    self._flush_traceback()

    def _read_new_lines(self):
        """Read new lines from the watched file since last position."""
        try:
            with open(self.filepath, "r") as f:
                f.seek(self._file_pos)
                for line in f:
                    self._process_line(line)
                self._file_pos = f.tell()
        except (IOError, OSError):
            pass

    def _get_mode_label(self) -> str:
        if self.deep:
            return "🔬 Deep Analysis (Tier 4 — Claude Sonnet)"
        if self.haiku:
            return "🧠 Mid-Tier (Tier 3 — Claude Haiku)"
        return "🚀 Auto (Tier 1 Regex → Tier 2 Grok)"

    def start(self):
        """Begin watching the log file. Blocks until interrupted."""
        if not os.path.exists(self.filepath):
            print(f"⚠️  File not found: {self.filepath}")
            print(f"    Waiting for file to be created...")
            while not os.path.exists(self.filepath):
                time.sleep(1)
            print(f"    ✅ File detected. Starting watch.")

        self._running = True

        # Seek to end of existing content
        with open(self.filepath, "r") as f:
            f.seek(0, 2)
            self._file_pos = f.tell()

        def _handle_signal(sig, frame):
            self._running = False
            print(f"\n\n🛑 Sentinel stopped. {self._error_count} error(s) caught.")
            sys.exit(0)

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        backend = "watchdog" if HAS_WATCHDOG else "poll"
        print(f"""
╔══════════════════════════════════════════════╗
║  👁️  RAIL DEBUG — Sentinel Mode Active       ║
╚══════════════════════════════════════════════╝

📂 Watching:  {self.filepath}
🏷️  Mode:     {self._get_mode_label()}
⚙️  Backend:  {backend}
⏹️  Stop:     Ctrl+C

Waiting for errors...
""")

        if HAS_WATCHDOG:
            self._start_watchdog()
        else:
            self._start_polling()

    def _start_watchdog(self):
        """Watch using watchdog filesystem events."""
        handler = _LogHandler(self)
        observer = Observer()
        observer.schedule(handler, path=os.path.dirname(self.filepath), recursive=False)
        observer.start()

        try:
            while self._running:
                time.sleep(0.5)
                # Flush any pending traceback after idle
                if self._in_traceback and self._buffer:
                    self._flush_traceback()
        finally:
            observer.stop()
            observer.join()

    def _start_polling(self):
        """Fallback: poll-based tail-follow."""
        while self._running:
            self._read_new_lines()
            if self._in_traceback and self._buffer:
                time.sleep(0.2)
                self._read_new_lines()
                if self._in_traceback and self._buffer:
                    self._flush_traceback()
            time.sleep(0.1)
