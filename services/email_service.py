"""
services/email_service.py — Transactional email via SMTP.

Sends:
  - Welcome email on new user registration
  - Trial-expiry nudge at 80% of monthly analysis quota

All sends are fire-and-forget (logged on failure, never raise).
Config via env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

log = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@debug.secureai.dev")
APP_URL = "https://debug.secureai.dev"


def _send(to_email: str, subject: str, html_body: str) -> bool:
    """Send one email. Returns True on success, False on failure (never raises)."""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        log.warning("Email not configured (SMTP_HOST/SMTP_USER/SMTP_PASSWORD missing) — skipping send")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = FROM_EMAIL
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, [to_email], msg.as_string())

        log.info(f"Email sent: {subject!r} → {to_email}")
        return True
    except Exception as e:
        log.error(f"Email send failed ({subject!r} → {to_email}): {e}")
        return False


def send_welcome_email(to_email: str, tier: str = "free") -> bool:
    """Welcome email sent immediately after registration."""
    subject = "Welcome to Rail Debug — your AI debugging platform"
    html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
  <h2 style="color: #0f172a;">Welcome to Rail Debug 🚂</h2>
  <p>Your account is live. Here's what you can do right now:</p>
  <ul style="line-height: 1.8;">
    <li><strong>Install the GitHub App</strong> — get AI-powered debug analysis on every push</li>
    <li><strong>Use the API</strong> — send error logs directly for instant analysis</li>
    <li><strong>View your dashboard</strong> — track usage and upgrade your plan</li>
  </ul>
  <p>
    <a href="{APP_URL}/dashboard" style="display: inline-block; background: #0f172a; color: #fff; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 600;">
      Open Dashboard →
    </a>
  </p>
  <p style="color: #64748b; font-size: 14px;">
    You're on the <strong>{tier.capitalize()}</strong> plan.
    {'Upgrade anytime to unlock higher analysis limits.' if tier == 'free' else 'Thanks for being a paying customer.'}
  </p>
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
  <p style="color: #94a3b8; font-size: 12px;">
    Rail Debug · <a href="{APP_URL}" style="color: #94a3b8;">debug.secureai.dev</a> ·
    <a href="{APP_URL}/privacy.html" style="color: #94a3b8;">Privacy</a>
  </p>
</body>
</html>
"""
    return _send(to_email, subject, html_body)


def send_usage_nudge_email(to_email: str, tier: str, monthly_usage: int, monthly_limit: int) -> bool:
    """Nudge email when user hits 80% of monthly analysis quota."""
    percent = int((monthly_usage / monthly_limit) * 100)
    remaining = monthly_limit - monthly_usage
    subject = f"Heads up — you've used {percent}% of your Rail Debug analyses this month"
    html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
  <h2 style="color: #b45309;">You're at {percent}% of your monthly limit</h2>
  <p>You have <strong>{remaining} analyses remaining</strong> on your {tier.capitalize()} plan this month.</p>
  <p>Once you hit your limit, new analyses will be paused until your billing period resets.</p>
  <p>
    <a href="{APP_URL}/dashboard#billing" style="display: inline-block; background: #0f172a; color: #fff; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 600;">
      Upgrade Plan →
    </a>
  </p>
  <p style="color: #64748b; font-size: 14px;">
    {'Upgrade to the Dev plan ($29/mo) for 10,000 analyses/month.' if tier == 'free' else 'Upgrade to the Team plan ($99/mo) for unlimited analyses.'}
  </p>
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
  <p style="color: #94a3b8; font-size: 12px;">
    Rail Debug · <a href="{APP_URL}" style="color: #94a3b8;">debug.secureai.dev</a>
  </p>
</body>
</html>
"""
    return _send(to_email, subject, html_body)
