"""
Rail Debug Python SDK — Client for the Rail Debug API Server.

Usage:
    from sdk import RailDebug

    client = RailDebug("http://localhost:8000")
    report = client.analyze("Traceback (most recent call last):\\n  ...")
    print(report["severity"])
"""

from typing import Optional

import httpx


class RailDebug:
    """Lightweight client for the Rail Debug API."""

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, payload: dict) -> dict:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}{path}", json=payload)
            resp.raise_for_status()
            return resp.json()

    def _get(self, path: str) -> dict:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(f"{self.base_url}{path}")
            resp.raise_for_status()
            return resp.json()

    # ── Public API ───────────────────────────────────────────────

    def health(self) -> dict:
        """Check server health."""
        return self._get("/health")

    def analyze(
        self,
        traceback: str,
        deep: bool = False,
        haiku: bool = False,
        project_path: Optional[str] = None,
        no_git: bool = False,
    ) -> dict:
        """Analyze a single traceback."""
        return self._post("/analyze", {
            "traceback": traceback,
            "deep": deep,
            "haiku": haiku,
            "project_path": project_path,
            "no_git": no_git,
        })

    def analyze_chain(
        self,
        traceback: str,
        deep: bool = False,
        haiku: bool = False,
        project_path: Optional[str] = None,
    ) -> dict:
        """Analyze a chained exception traceback."""
        return self._post("/analyze/chain", {
            "traceback": traceback,
            "deep": deep,
            "haiku": haiku,
            "project_path": project_path,
        })

    def analyze_batch(
        self,
        text: str,
        deep: bool = False,
        haiku: bool = False,
        project_path: Optional[str] = None,
    ) -> dict:
        """Analyze multiple errors from a log blob."""
        return self._post("/analyze/batch", {
            "text": text,
            "deep": deep,
            "haiku": haiku,
            "project_path": project_path,
        })

    def scan_project(self, project_path: str) -> dict:
        """Scan a project and return its profile."""
        return self._post("/project/scan", {
            "project_path": project_path,
        })
