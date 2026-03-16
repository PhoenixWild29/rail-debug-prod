"""
routes/teams.py — Team CRUD, invite, join, shared analyses endpoints.
"""

import os
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.auth_middleware import get_current_user, get_db_conn

router = APIRouter(prefix="/teams")

class TeamCreateRequest(BaseModel):
    name: str

class TeamInviteRequest(BaseModel):
    email: str

class TeamJoinRequest(BaseModel):
    token: str

@router.post("/")
def create_team(req: TeamCreateRequest, current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["sub"])
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        # Check if user already owns a team (for simplicity, allow multiple? but limit to 1 for now)
        cur.execute("SELECT COUNT(*) FROM teams WHERE created_by = %s", (user_id,))
        count = cur.fetchone()[0]
        if count >= 1:
            raise HTTPException(status_code=400, detail="You can only create one team for now.")
        # Create team
        cur.execute("INSERT INTO teams (name, created_by) VALUES (%s, %s) RETURNING id", (req.name, user_id))
        team_id = cur.fetchone()[0]
        # Add creator as owner
        cur.execute("INSERT INTO team_members (team_id, user_id, role) VALUES (%s, %s, 'owner')", (team_id, user_id))
        conn.commit()
        return {"team_id": team_id, "name": req.name}
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@router.get("/")
def list_user_teams(current_user: dict = Depends(get_current_user)) -> List[dict]:
    user_id = int(current_user["sub"])
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT t.id, t.name, tm.role, t.created_at
            FROM teams t
            JOIN team_members tm ON t.id = tm.team_id
            WHERE tm.user_id = %s
            ORDER BY t.created_at DESC
        """, (user_id,))
        teams = cur.fetchall()
        return [{"id": t["id"], "name": t["name"], "role": t["role"], "created_at": str(t["created_at"])} for t in teams]
    finally:
        if conn:
            conn.close()

@router.post("/{team_id}/invite")
def invite_to_team(team_id: int, req: TeamInviteRequest, current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["sub"])
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        # Check if user is owner/admin of the team
        cur.execute("SELECT role FROM team_members WHERE team_id = %s AND user_id = %s", (team_id, user_id))
        member = cur.fetchone()
        if not member or member["role"] not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="Not authorized to invite members.")
        # Check if user exists
        cur.execute("SELECT id FROM users WHERE email = %s", (req.email,))
        invitee = cur.fetchone()
        if not invitee:
            raise HTTPException(status_code=404, detail="User not found.")
        invitee_id = invitee["id"]
        # Check if already member
        cur.execute("SELECT 1 FROM team_members WHERE team_id = %s AND user_id = %s", (team_id, invitee_id))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="User is already a member.")
        # Generate token (simple, store in DB or send via email — for now, return token)
        token = secrets.token_urlsafe(32)
        # In real impl, store token with expiry, send email
        # For now, just add directly (simplified)
        cur.execute("INSERT INTO team_members (team_id, user_id, role) VALUES (%s, %s, 'member')", (team_id, invitee_id))
        conn.commit()
        return {"message": f"Invited {req.email} to team."}
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@router.post("/join")
def join_team(req: TeamJoinRequest, current_user: dict = Depends(get_current_user)):
    # Simplified: assume token is team_id for now
    try:
        team_id = int(req.token)
    except:
        raise HTTPException(status_code=400, detail="Invalid token.")
    user_id = int(current_user["sub"])
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        # Check if team exists
        cur.execute("SELECT id FROM teams WHERE id = %s", (team_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Team not found.")
        # Check if already member
        cur.execute("SELECT 1 FROM team_members WHERE team_id = %s AND user_id = %s", (team_id, user_id))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Already a member.")
        # Add as member
        cur.execute("INSERT INTO team_members (team_id, user_id, role) VALUES (%s, %s, 'member')", (team_id, user_id))
        conn.commit()
        return {"message": "Joined team."}
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@router.get("/{team_id}/analyses")
def get_team_analyses(team_id: int, current_user: dict = Depends(get_current_user)) -> List[dict]:
    user_id = int(current_user["sub"])
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        # Check membership
        cur.execute("SELECT 1 FROM team_members WHERE team_id = %s AND user_id = %s", (team_id, user_id))
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="Not a member of this team.")
        # Get analyses
        cur.execute("""
            SELECT id, language, tier_used, severity, created_at
            FROM analyses
            WHERE team_id = %s
            ORDER BY created_at DESC
            LIMIT 50
        """, (team_id,))
        analyses = cur.fetchall()
        return [{"id": a["id"], "language": a["language"], "tier_used": a["tier_used"], "severity": a["severity"], "created_at": str(a["created_at"])} for a in analyses]
    finally:
        if conn:
            conn.close()

@router.post("/analyses/{analysis_id}/share")
def share_analysis(analysis_id: int, team_id: int = Query(...), current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["sub"])
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        # Check if analysis belongs to user
        cur.execute("SELECT id FROM analyses WHERE id = %s AND user_id = %s", (analysis_id, user_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Analysis not found or not yours.")
        # Check if member of team
        cur.execute("SELECT 1 FROM team_members WHERE team_id = %s AND user_id = %s", (team_id, user_id))
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="Not a member of this team.")
        # Share
        cur.execute("UPDATE analyses SET team_id = %s WHERE id = %s", (team_id, analysis_id))
        conn.commit()
        return {"message": "Analysis shared with team."}
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()