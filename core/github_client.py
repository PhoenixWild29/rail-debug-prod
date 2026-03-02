"""
core/github_client.py — GitHub App API client.

Handles: JWT auth, installation tokens, log fetching, traceback extraction,
commit comment posting, and webhook signature verification.
"""

import hashlib
import hmac
import io
import json
import os
import re
import time
import zipfile

import httpx
import jwt


def _get_private_key() -> str:
    """Load PEM private key from env — stored as single line with \\\\n escapes."""
    return os.getenv("GITHUB_APP_PRIVATE_KEY", "").replace("\\\\n", "\\n")


def make_app_jwt() -> str:
    """Create a short-lived RS256 JWT signed with the App private key."""
    app_id = os.getenv("GITHUB_APP_ID", "")
    private_key = _get_private_key()
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 600, "iss": app_id}
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_installation_token(installation_id: int) -> str:
    """Exchange App JWT for an installation access token."""
    app_jwt = make_app_jwt()
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = httpx.post(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()["token"]


def get_workflow_run_logs(owner: str, repo: str, run_id: int, token: str) -> str:
    """Download and extract all text from a workflow run's log ZIP."""
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    resp = httpx.get(url, headers=headers, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    all_text = []
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        for name in z.namelist():
            with z.open(name) as f:
                all_text.append(f.read().decode("utf-8", errors="replace"))
    return "\\n".join(all_text)