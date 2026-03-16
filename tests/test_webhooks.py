"""
tests/test_webhooks.py — Unit tests for webhook formatting and integration tests for settings endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from server import app
from routes.webhooks import _send_slack_webhook, _send_discord_webhook

client = TestClient(app)

# Mock get_current_user
def mock_get_current_user():
    return {"sub": "1"}

# Unit tests for webhook formatting
@patch('routes.webhooks.httpx.post')
def test_send_slack_webhook(mock_post):
    url = "https://hooks.slack.com/test"
    analysis = {
        "error_type": "ValueError",
        "root_cause": "Invalid value passed",
        "suggested_fix": "Check input validation",
        "severity": "high"
    }
    repo_full_name = "test/repo"
    run_id = 12345

    _send_slack_webhook(url, analysis, repo_full_name, run_id)

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == url
    payload = call_args[1]['json']
    assert 'blocks' in payload
    assert len(payload['blocks']) == 3  # section, section, actions
    assert ':orange_circle:' in payload['blocks'][0]['text']['text']  # high severity

@patch('routes.webhooks.httpx.post')
def test_send_discord_webhook(mock_post):
    url = "https://discord.com/api/webhooks/test"
    analysis = {
        "error_type": "SyntaxError",
        "root_cause": "Missing colon",
        "suggested_fix": "Add colon after if",
        "severity": "critical"
    }
    repo_full_name = "test/repo"
    run_id = 12345

    _send_discord_webhook(url, analysis, repo_full_name, run_id)

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == url
    payload = call_args[1]['json']
    assert 'embeds' in payload
    embed = payload['embeds'][0]
    assert embed['color'] == 0xff0000  # critical color
    assert 'SyntaxError' in embed['title']
    assert 'Missing colon' in embed['description']

# Integration tests for settings endpoints
def test_get_webhook_settings():
    with patch('routes.webhooks.get_current_user', return_value=mock_get_current_user()):
        with patch('routes.webhooks.get_db_conn') as mock_conn:
            mock_cur = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cur
            mock_cur.fetchone.return_value = ("https://slack.com/hook", "https://discord.com/hook")

            response = client.get("/webhooks")
            assert response.status_code == 200
            data = response.json()
            assert data["slack_webhook_url"] == "https://slack.com/hook"
            assert data["discord_webhook_url"] == "https://discord.com/hook"

def test_update_webhook_settings():
    with patch('routes.webhooks.get_current_user', return_value=mock_get_current_user()):
        with patch('routes.webhooks.get_db_conn') as mock_conn:
            mock_cur = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cur

            response = client.put("/webhooks", data={
                "slack_webhook_url": "https://new-slack.com/hook",
                "discord_webhook_url": "https://new-discord.com/hook"
            })
            assert response.status_code == 200
            assert response.json() == {"message": "Webhook settings updated"}

            # Check if execute was called with correct params
            mock_cur.execute.assert_called_with(
                "UPDATE users SET slack_webhook_url = %s, discord_webhook_url = %s WHERE id = %s",
                ("https://new-slack.com/hook", "https://new-discord.com/hook", 1)
            )

def test_update_invalid_url():
    with patch('routes.webhooks.get_current_user', return_value=mock_get_current_user()):
        response = client.put("/webhooks", data={
            "slack_webhook_url": "invalid-url",
            "discord_webhook_url": "https://valid.com"
        })
        assert response.status_code == 400
        assert "Invalid Slack webhook URL format" in response.json()["detail"]

@patch('routes.webhooks.httpx.post')
def test_test_webhooks(mock_post):
    with patch('routes.webhooks.get_current_user', return_value=mock_get_current_user()):
        with patch('routes.webhooks.get_db_conn') as mock_conn:
            mock_cur = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cur
            mock_cur.fetchone.return_value = ("https://slack.com/hook", "https://discord.com/hook")

            response = client.post("/webhooks/test")
            assert response.status_code == 200
            assert response.json() == {"message": "Test notifications sent"}

            # Should call post twice, once for slack, once for discord
            assert mock_post.call_count == 2