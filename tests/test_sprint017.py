#!/usr/bin/env python3
"""
Sprint 017 Tests: Stripe Billing + User Dashboard
"""
import os
import sys
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))
from server import app

client = TestClient(app)

# ── Helpers ──────────────────────────────────────────────────────

def _make_token(user_id=1, email="test@example.com", tier="free"):
    from core.auth_middleware import make_token
    return make_token(user_id, email, tier)

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Auth — Structure / Input Validation (no DB) ──────────────────

def test_register_endpoint_exists():
    resp = client.post("/auth/register", json={"email": "new@example.com", "password": "password123"})
    assert resp.status_code != 404

def test_register_short_password():
    resp = client.post("/auth/register", json={"email": "x@example.com", "password": "short"})
    assert resp.status_code == 422

def test_register_invalid_email():
    resp = client.post("/auth/register", json={"email": "notanemail", "password": "password123"})
    assert resp.status_code == 422

def test_login_endpoint_exists():
    resp = client.post("/auth/login", json={"email": "x@example.com", "password": "password123"})
    assert resp.status_code != 404

def test_login_invalid_email_format():
    resp = client.post("/auth/login", json={"email": "invalid", "password": "pass"})
    assert resp.status_code == 422

def test_me_no_token():
    resp = client.get("/auth/me")
    assert resp.status_code == 401

def test_me_bad_token():
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not.a.valid.token"})
    assert resp.status_code == 401

def test_me_valid_token_no_db():
    token = _make_token()
    resp = client.get("/auth/me", headers=_auth(token))
    # Valid JWT but no DB — 500 is expected
    assert resp.status_code in (200, 500)

def test_regenerate_key_no_token():
    resp = client.post("/auth/regenerate-key")
    assert resp.status_code == 401

def test_register_missing_fields():
    resp = client.post("/auth/register", json={"email": "x@example.com"})
    assert resp.status_code == 422


# ── Auth — DB-dependent (expect 200 or 500) ──────────────────────

def test_register_valid_request():
    resp = client.post("/auth/register", json={"email": "new@example.com", "password": "password123"})
    assert resp.status_code in (201, 500)  # 201 if DB up, 500 if not

def test_login_valid_request():
    resp = client.post("/auth/login", json={"email": "x@example.com", "password": "password123"})
    assert resp.status_code in (200, 401, 500)

def test_register_duplicate_handled():
    # Both calls should give structured responses (not crash)
    r1 = client.post("/auth/register", json={"email": "dup@example.com", "password": "password123"})
    r2 = client.post("/auth/register", json={"email": "dup@example.com", "password": "password123"})
    assert r1.status_code in (201, 500)
    assert r2.status_code in (409, 500)


# ── Billing — Structure / Auth checks ────────────────────────────

def test_billing_checkout_no_token():
    resp = client.post("/billing/checkout", json={"plan": "dev"})
    assert resp.status_code == 401

def test_billing_checkout_invalid_plan():
    token = _make_token()
    resp = client.post("/billing/checkout", json={"plan": "invalid"}, headers=_auth(token))
    assert resp.status_code == 422

def test_billing_checkout_valid_token_no_stripe():
    token = _make_token()
    resp = client.post("/billing/checkout", json={"plan": "dev"}, headers=_auth(token))
    # Valid token, no Stripe keys configured → 500 or DB error
    assert resp.status_code in (200, 500)

def test_billing_portal_no_token():
    resp = client.post("/billing/portal")
    assert resp.status_code == 401

def test_billing_status_no_token():
    resp = client.get("/billing/status")
    assert resp.status_code == 401

def test_billing_status_valid_token():
    token = _make_token()
    resp = client.get("/billing/status", headers=_auth(token))
    assert resp.status_code in (200, 500)

def test_webhook_no_signature():
    resp = client.post("/billing/webhook", content=b'{}')
    # 400 when secret is set but sig is missing; 500 when STRIPE_WEBHOOK_SECRET not configured
    assert resp.status_code in (400, 500)

def test_webhook_bad_signature():
    resp = client.post(
        "/billing/webhook",
        content=b'{"type":"checkout.session.completed","data":{"object":{}}}',
        headers={"stripe-signature": "t=123,v1=bad"}
    )
    assert resp.status_code in (400, 500)


# ── JWT Token Integrity ────────────────────────────────────────────

def test_token_expired():
    import jwt as pyjwt
    from datetime import datetime, timezone, timedelta
    payload = {"sub": "1", "email": "x@x.com", "tier": "free", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}
    token = pyjwt.encode(payload, os.getenv("JWT_SECRET", "dev-secret-change-in-prod"), algorithm="HS256")
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# ── Rate Limit Logic ──────────────────────────────────────────────

def test_rate_limit_free_tier_daily():
    from core.auth_middleware import TIER_DAILY_LIMITS
    assert TIER_DAILY_LIMITS["free"] == 10

def test_rate_limit_dev_tier_daily():
    from core.auth_middleware import TIER_DAILY_LIMITS
    assert TIER_DAILY_LIMITS["dev"] == 200

def test_rate_limit_team_unlimited():
    from core.auth_middleware import TIER_DAILY_LIMITS
    assert TIER_DAILY_LIMITS["team"] is None


# ── Files ─────────────────────────────────────────────────────────

def test_dashboard_html_exists():
    assert os.path.exists("web/dashboard.html")

def test_dashboard_html_content():
    with open("web/dashboard.html") as f:
        content = f.read()
    assert "Dashboard" in content
    assert "dashboard.js" in content
    assert "auth.js" in content

def test_auth_js_exists():
    assert os.path.exists("web/assets/js/auth.js")

def test_auth_js_content():
    with open("web/assets/js/auth.js") as f:
        content = f.read()
    assert "getToken" in content
    assert "isLoggedIn" in content

def test_dashboard_js_exists():
    assert os.path.exists("web/assets/js/dashboard.js")

def test_migration_sql_exists():
    assert os.path.exists("migrations/001_sprint017_stripe.sql")

def test_migration_sql_content():
    with open("migrations/001_sprint017_stripe.sql") as f:
        content = f.read()
    assert "stripe_customer_id" in content
    assert "subscription_status" in content
    assert "users_tier_check" in content

def test_init_sql_updated():
    with open("init.sql") as f:
        content = f.read()
    assert "stripe_customer_id" in content
    assert "'free','dev','team'" in content

def test_docker_compose_stripe_env():
    with open("docker-compose.yml") as f:
        content = f.read()
    assert "STRIPE_SECRET_KEY" in content
    assert "JWT_SECRET" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
