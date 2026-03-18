#!/usr/bin/env python3
"""
Sprint 037 Tests: Team Collaboration Features
Tests team CRUD, invite, member management, shared analyses, and permissions.
"""
import sys
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))
from server import app

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────

def _make_token(user_id=1, email="test@example.com", tier="team"):
    from core.auth_middleware import make_token
    return make_token(user_id, email, tier)

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Team CRUD — Endpoint Existence & Auth ────────────────────────

def test_create_team_no_auth():
    resp = client.post("/teams/", json={"name": "Test Team"})
    assert resp.status_code == 401

def test_create_team_endpoint_exists():
    token = _make_token()
    resp = client.post("/teams/", json={"name": "Test Team"}, headers=_auth(token))
    assert resp.status_code != 404

def test_create_team_missing_name():
    token = _make_token()
    resp = client.post("/teams/", json={}, headers=_auth(token))
    assert resp.status_code == 422

def test_list_teams_no_auth():
    resp = client.get("/teams/")
    assert resp.status_code == 401

def test_list_teams_endpoint_exists():
    token = _make_token()
    resp = client.get("/teams/", headers=_auth(token))
    assert resp.status_code != 404


# ── Team Members — Endpoint Existence & Auth ─────────────────────

def test_list_members_no_auth():
    resp = client.get("/teams/1/members")
    assert resp.status_code == 401

def test_list_members_endpoint_exists():
    token = _make_token()
    resp = client.get("/teams/1/members", headers=_auth(token))
    # 403 (not member) or 500 (no DB) — not 404
    assert resp.status_code != 404


# ── Invite — Endpoint Existence & Auth ───────────────────────────

def test_invite_no_auth():
    resp = client.post("/teams/1/invite", json={"email": "x@example.com"})
    assert resp.status_code == 401

def test_invite_endpoint_exists():
    token = _make_token()
    resp = client.post("/teams/1/invite", json={"email": "x@example.com"}, headers=_auth(token))
    assert resp.status_code != 404

def test_invite_missing_email():
    token = _make_token()
    resp = client.post("/teams/1/invite", json={}, headers=_auth(token))
    assert resp.status_code == 422


# ── Join — Endpoint Existence & Auth ─────────────────────────────

def test_join_no_auth():
    resp = client.post("/teams/join", json={"token": "1"})
    assert resp.status_code == 401

def test_join_endpoint_exists():
    token = _make_token()
    resp = client.post("/teams/join", json={"token": "1"}, headers=_auth(token))
    assert resp.status_code != 404

def test_join_invalid_token():
    token = _make_token()
    resp = client.post("/teams/join", json={"token": "not-a-number"}, headers=_auth(token))
    assert resp.status_code == 400


# ── Delete Team — Endpoint Existence & Auth ──────────────────────

def test_delete_team_no_auth():
    resp = client.delete("/teams/1")
    assert resp.status_code == 401

def test_delete_team_endpoint_exists():
    token = _make_token()
    resp = client.delete("/teams/1", headers=_auth(token))
    assert resp.status_code != 404


# ── Remove Member — Endpoint Existence & Auth ────────────────────

def test_remove_member_no_auth():
    resp = client.delete("/teams/1/members/2")
    assert resp.status_code == 401

def test_remove_member_endpoint_exists():
    token = _make_token()
    resp = client.delete("/teams/1/members/2", headers=_auth(token))
    assert resp.status_code != 404


# ── Role Update — Endpoint Existence & Auth ──────────────────────

def test_update_role_no_auth():
    resp = client.put("/teams/1/members/2/role", json={"role": "admin"})
    assert resp.status_code == 401

def test_update_role_endpoint_exists():
    token = _make_token()
    resp = client.put("/teams/1/members/2/role", json={"role": "admin"}, headers=_auth(token))
    assert resp.status_code != 404

def test_update_role_invalid_role():
    token = _make_token()
    resp = client.put("/teams/1/members/2/role", json={"role": "superadmin"}, headers=_auth(token))
    assert resp.status_code == 422


# ── Shared Analyses — Endpoint Existence & Auth ──────────────────

def test_team_analyses_no_auth():
    resp = client.get("/teams/1/analyses")
    assert resp.status_code == 401

def test_team_analyses_endpoint_exists():
    token = _make_token()
    resp = client.get("/teams/1/analyses", headers=_auth(token))
    assert resp.status_code != 404

def test_share_analysis_no_auth():
    resp = client.post("/teams/analyses/1/share?team_id=1")
    assert resp.status_code == 401

def test_share_analysis_endpoint_exists():
    token = _make_token()
    resp = client.post("/teams/analyses/1/share?team_id=1", headers=_auth(token))
    assert resp.status_code != 404
