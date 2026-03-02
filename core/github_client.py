"""
core/github_client.py — GitHub App API client.

Handles: JWT auth, installation tokens, log fetching, traceback extraction,
commit comment posting, and webhook signature verification.
"""

import hashlib
import hmac
import io
import os
import re
import time
import zipfile

import httpx
import jwt


def _get_private_key() -> str:
    """Load PEM private key from env — stored as single line with \\n escapes."""
    return os.getenv("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n")


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
    return "\n".join(all_text)


def extract_traceback_from_logs(log_text: str) -> str:
    """Strip GitHub Actions timestamps and extract the most relevant error block."""
    # Strip timestamp prefix: 2024-01-15T10:30:00.123Z
    cleaned = re.sub(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s?",
        "",
        log_text,
        flags=re.MULTILINE,
    )

    # Python traceback
    match = re.search(
        r"(Traceback \(most recent call last\):.*?)(?=\n\n|\Z)",
        cleaned,
        re.DOTALL,
    )
    if match:
        return match.group(1)[:3000]

    # Generic error line
    match = re.search(
        r"((?:\w+Error|\w+Exception):.*?)(?=\n\n|\Z)",
        cleaned,
        re.DOTALL,
    )
    if match:
        return match.group(1)[:3000]

    # Last 2000 chars as fallback
    return cleaned[-2000:].strip() if len(cleaned) > 2000 else cleaned.strip()


def post_commit_comment(owner: str, repo: str, sha: str, body: str, token: str) -> dict:
    """Post a commit comment on the failing SHA."""
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    resp = httpx.post(url, headers=headers, json={"body": body}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        return False
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)


def format_analysis_comment(analysis: dict, repo: str, run_id: int) -> str:
    """Format the LLM analysis dict as a GitHub markdown commit comment."""
    severity = analysis.get("severity", "unknown")
    severity_emoji = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🟢",
    }.get(severity, "⚪")

    lines = [
        f"## {severity_emoji} Rail Debug — CI Failure Analysis",
        "",
        f"**Error:** `{analysis.get('error_type', 'Unknown')}` — {analysis.get('error_message', '')}",
        "",
        f"**Root Cause:** {analysis.get('root_cause', 'Unable to determine')}",
        "",
        f"**Fix:** {analysis.get('suggested_fix', 'No suggestion available')}",
    ]

    arch = analysis.get("architecture_notes")
    if arch:
        lines += ["", f"**Architecture Note:** {arch}"]

    model = analysis.get("_model", "")
    if model:
        lines += ["", f"*Analyzed by Rail Debug ({model}) — [debug.secureai.dev](https://debug.secureai.dev)*"]

    return "\n".join(lines)
