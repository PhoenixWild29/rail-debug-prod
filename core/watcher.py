"""
Watch Mode Sentinel — real-time log file monitoring.

Tails a log file, detects Python tracebacks as they appear,
and routes them through the Tri-State Analyzer automatically.
"""

import os
import re
import time
import signal
import sys
from typing import Optional, Callable

from core.analyzer import analyze


# Traceback detection patterns
TRACEBACK_START = re.compile(r"^Traceback \(most recent call last\):")
TRACEBACK_FILE_LINE = re.compile(r"^\s+File ")
ERROR_LINE = re.compile(r"^[A-Za-z][\w.]*(?:Error|Exception|Warning|Exit).*:")


class Sentinel:
    """
    Real-time log watcher that detects and analyzes tracebacks.
    
    Uses tail-follow approach (no external deps like watchdog).
    Pure Python. Zero additional dependencies. Ships now.
    """

    def __init__(
        self,
        filepath: str,
        deep: bool = False,
        json_output: bool = False,
        callback: Optional[Callable] = None,
    ):
        self.filepath = filepath
        self.deep = deep
        self.json_output = json_output
        self.callback = callback
        self._running = False
        self._buffer = []
        self._in_traceback = False
        self._error_count = 0

    def _flush_traceback(self, format_fn):
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
            print(analyze_to_json(traceback_text, deep=self.deep))
        else:
            report = analyze(traceback_text, deep=self.deep)
            if self.callback:
                self.callback(report)
            else:
                format_fn(report, timestamp)

    def _default_format(self, report, timestamp):
        """Pretty-print a detected error."""
        severity_icons = {
            "low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"
        }
        tier_labels = {
            0: "OFFLINE", 1: "Regex", 2: "Haiku", 3: "Deep"
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

        # Start of new traceback
        if TRACEBACK_START.match(stripped):
            # Flush any previous incomplete traceback
            if self._in_traceback and self._buffer:
                self._flush_traceback(self._default_format)
            self._in_traceback = True
            self._buffer = [stripped]
            return

        if self._in_traceback:
            self._buffer.append(stripped)

            # Check if this line is the final error line (not indented, contains Error/Exception)
            if stripped and not stripped.startswith(" ") and not TRACEBACK_START.match(stripped):
                if ERROR_LINE.match(stripped) or not TRACEBACK_FILE_LINE.match(stripped):
                    self._flush_traceback(self._default_format)

    def start(self):
        """Begin watching the log file. Blocks until interrupted."""
        if not os.path.exists(self.filepath):
            print(f"⚠️  File not found: {self.filepath}")
            print(f"    Waiting for file to be created...")

            # Wait for file creation
            while not os.path.exists(self.filepath):
                time.sleep(1)

            print(f"    ✅ File detected. Starting watch.")

        self._running = True

        # Register clean shutdown
        def _handle_signal(sig, frame):
            self._running = False
            print(f"\n\n🛑 Sentinel stopped. {self._error_count} error(s) caught.")
            sys.exit(0)

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        print(f"""
╔══════════════════════════════════════════════╗
║  👁️  RAIL DEBUG — Sentinel Mode Active       ║
╚══════════════════════════════════════════════╝

📂 Watching:  {self.filepath}
🏷️  Mode:     {'🔬 Deep Analysis (Tier 3)' if self.deep else '⚡ Auto (Tier 1→2)'}
⏹️  Stop:     Ctrl+C

Waiting for errors...
""")

        # Tail-follow the file
        with open(self.filepath, "r") as f:
            # Seek to end (only watch new content)
            f.seek(0, 2)

            while self._running:
                line = f.readline()
                if line:
                    self._process_line(line)
                else:
                    # Flush any pending traceback after a pause (end of burst)
                    if self._in_traceback and self._buffer:
                        # Wait a beat to see if more lines are coming
                        time.sleep(0.2)
                        next_line = f.readline()
                        if next_line:
                            self._process_line(next_line)
                        else:
                            self._flush_traceback(self._default_format)
                    time.sleep(0.1)
