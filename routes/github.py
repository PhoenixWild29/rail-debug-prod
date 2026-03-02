"""
routes/github.py — GitHub App webhook + OAuth callback.

Endpoints:
  POST /github/webhook        — receives GitHub webhook events
  GET  /github/oauth/callback — post-install OAuth exchange
"""

import os
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from core.auth_middleware import get_db_conn
from core.github_client import (
    extract_traceback_from_logs,
    format_analysis_comment,
    get_installation_token,
    get_workflow_run_logs,
    post_commit_comment,
    verify_webhook_signature,
)
from core.llm import analyze_with_llm

router = APIRouter(prefix="/github")


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

@router.post("/webhook", include_in_schema=False)
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not verify_webhook_signature(payload, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    import json
    event_type = request.headers.get("X-GitHub-Event", "")
    try:
        data = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if event_type == "installation":
        _handle_installation(data)
    elif event_type == "workflow_run":
        if data.get("action") == "completed" and data.get("workflow_run", {}).get("conclusion") == "failure":
            background_tasks.add_task(_handle_workflow_failure, data)

    return {"received": True}


def _handle_installation(data: dict) -> None:
    """Record or soft-delete GitHub App installation."""
    action = data.get("action")
    installation = data.get("installation", {})
    installation_id = installation.get("id")
    account = installation.get("account", {})
    account_login = account.get("login", "")
    account_type = account.get("type", "User")

    if not installation_id:
        return

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        if action == "created":
            cur.execute(
                """
                INSERT INTO github_installations (installation_id, account_login, account_type)
                VALUES (%s, %s, %s)
                ON CONFLICT (installation_id) DO UPDATE
                    SET active = true, uninstalled_at = NULL
                """,
                (installation_id, account_login, account_type),
            )
        elif action in ("deleted", "suspend"):
            cur.execute(
                "UPDATE github_installations SET active = false, uninstalled_at = NOW() WHERE installation_id = %s",
                (installation_id,),
            )
        conn.commit()
        cur.close()
    except Exception:
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


def _handle_workflow_failure(data: dict) -> None:
    """Fetch logs, analyze, post commit comment, record in DB."""
    run = data.get("workflow_run", {})
    installation_id = data.get("installation", {}).get("id")
    repo = data.get("repository", {})

    run_id = run.get("id")
    head_sha = run.get("head_sha")
    owner = repo.get("owner", {}).get("login")
    repo_name = repo.get("name")
    repo_full_name = repo.get("full_name")

    if not all([installation_id, run_id, head_sha, owner, repo_name]):
        return

    try:
        token = get_installation_token(installation_id)
    except Exception:
        return

    try:
        log_text = get_workflow_run_logs(owner, repo_name, run_id, token)
    except Exception:
        return

    traceback_snippet = extract_traceback_from_logs(log_text)
    if not traceback_snippet:
        return

    analysis = analyze_with_llm(traceback_snippet)
    if not analysis:
        return

    # Format and post comment
    comment_body = format_analysis_comment(analysis, repo_full_name, run_id)
    comment_posted = False
    try:
        post_commit_comment(owner, repo_name, head_sha, comment_body, token)
        comment_posted = True
    except Exception:
        pass

    # Record analysis in DB
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        import json as _json
        cur.execute(
            """
            INSERT INTO github_analyses
                (installation_id, repo_full_name, workflow_run_id, head_sha,
                 traceback_snippet, analysis_result, comment_posted)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                installation_id,
                repo_full_name,
                run_id,
                head_sha,
                traceback_snippet[:500],
                _json.dumps(analysis),
                comment_posted,
            ),
        )
        conn.commit()
        cur.close()
    except Exception:
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# OAuth Callback
# ---------------------------------------------------------------------------

@router.get("/oauth/callback")
async def github_oauth_callback(code: str = None, installation_id: int = None, state: str = None):
    """Post-install OAuth callback — exchange code for token, link installation to user."""
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code")

    import httpx as _httpx

    client_id = os.getenv("GITHUB_APP_CLIENT_ID", "")
    client_secret = os.getenv("GITHUB_APP_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    # Exchange code for access token
    resp = _httpx.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        },
        timeout=15,
    )
    token_data = resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="OAuth token exchange failed")

    # Get GitHub user profile
    user_resp = _httpx.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    gh_user = user_resp.json()
    github_username = gh_user.get("login")

    # Link installation to user (by GitHub username match if they're registered)
    if installation_id and github_username:
        conn = None
        try:
            conn = get_db_conn()
            cur = conn.cursor()
            # Update installation record with linked user (best-effort)
            cur.execute(
                """
                UPDATE github_installations
                SET user_id = (SELECT id FROM users WHERE github_username = %s LIMIT 1)
                WHERE installation_id = %s
                """,
                (github_username, installation_id),
            )
            conn.commit()
            cur.close()
        except Exception:
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    domain = os.getenv("SITE_DOMAIN", "https://debug.secureai.dev")
    return {
        "status": "installed",
        "github_username": github_username,
        "redirect": f"{domain}/dashboard",
    }