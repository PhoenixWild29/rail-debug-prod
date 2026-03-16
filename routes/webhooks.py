"""
routes/webhooks.py — Webhook settings endpoints for Slack and Discord notifications.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from core.auth_middleware import get_current_user
from core.db import get_db_conn

router = APIRouter(prefix="/webhooks")


def _send_slack_webhook(url: str, analysis: dict, repo_full_name: str, run_id: int):
    """Send Slack notification using Block Kit."""
    severity_emoji = {
        "critical": ":red_circle:",
        "high": ":orange_circle:",
        "medium": ":yellow_circle:",
        "low": ":green_circle:",
    }.get(analysis.get("severity", "low"), ":white_circle:")

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{severity_emoji} *{analysis.get('error_type', 'Error')}* in {repo_full_name}\n{analysis.get('root_cause', '')[:200]}...",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Suggested Fix:* {analysis.get('suggested_fix', '')[:200]}...",
            },
        },
    ]

    run_url = f"https://github.com/{repo_full_name}/actions/runs/{run_id}"
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Full Analysis"},
                "url": run_url,
            },
        ],
    })

    payload = {"blocks": blocks}
    try:
        httpx.post(url, json=payload, timeout=10)
    except Exception:
        pass  # Ignore failures


def _send_discord_webhook(url: str, analysis: dict, repo_full_name: str, run_id: int):
    """Send Discord notification using embed."""
    severity_color = {
        "critical": 0xff0000,
        "high": 0xffa500,
        "medium": 0xffff00,
        "low": 0x00ff00,
    }.get(analysis.get("severity", "low"), 0xffffff)

    embed = {
        "title": f"{analysis.get('error_type', 'Error')} in {repo_full_name}",
        "description": analysis.get("root_cause", ""),
        "color": severity_color,
        "fields": [
            {
                "name": "Suggested Fix",
                "value": analysis.get("suggested_fix", "")[:1024],  # Discord limit
                "inline": False,
            },
        ],
        "url": f"https://github.com/{repo_full_name}/actions/runs/{run_id}",
    }

    payload = {"embeds": [embed]}
    try:
        httpx.post(url, json=payload, timeout=10)
    except Exception:
        pass


@router.get("/")
def get_webhook_settings(current_user: dict = Depends(get_current_user)):
    """Get current webhook URLs for the authenticated user."""
    user_id = int(current_user["sub"])

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT slack_webhook_url, discord_webhook_url FROM users WHERE id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        slack_url, discord_url = row
        return {
            "slack_webhook_url": slack_url or "",
            "discord_webhook_url": discord_url or "",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.put("/")
def update_webhook_settings(
    slack_webhook_url: str = "",
    discord_webhook_url: str = "",
    current_user: dict = Depends(get_current_user)
):
    """Update webhook URLs for the authenticated user. Validates URL format."""
    user_id = int(current_user["sub"])

    # Basic URL validation
    import re
    url_pattern = re.compile(r"^https?://[^\s/$.?#].[^\s]*$")

    if slack_webhook_url and not url_pattern.match(slack_webhook_url):
        raise HTTPException(status_code=400, detail="Invalid Slack webhook URL format")
    if discord_webhook_url and not url_pattern.match(discord_webhook_url):
        raise HTTPException(status_code=400, detail="Invalid Discord webhook URL format")

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET slack_webhook_url = %s, discord_webhook_url = %s WHERE id = %s",
            (slack_webhook_url or None, discord_webhook_url or None, user_id),
        )
        conn.commit()
        cur.close()
        return {"message": "Webhook settings updated"}
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.post("/test")
def test_webhooks(current_user: dict = Depends(get_current_user)):
    """Send test notifications to configured webhooks."""
    user_id = int(current_user["sub"])

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT slack_webhook_url, discord_webhook_url FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        slack_url, discord_url = row

        test_analysis = {
            "error_type": "TestError",
            "root_cause": "This is a test notification from Rail Debug.",
            "suggested_fix": "No action needed — this is just a test.",
            "severity": "low",
        }

        if slack_url:
            _send_slack_webhook(slack_url, test_analysis, "test/repo", 12345)
        if discord_url:
            _send_discord_webhook(discord_url, test_analysis, "test/repo", 12345)

        return {"message": "Test notifications sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()