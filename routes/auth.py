"""
routes/auth.py — Register, login, /me, API key regeneration.
All routes mounted at /auth/* via server.py.
"""
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr

from core.auth_middleware import get_current_user, get_db_conn, make_token

router = APIRouter(prefix="/auth")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest):
    if len(req.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    email_lower = req.email.lower().strip()
    password_hash = pwd_context.hash(req.password)
    api_key = "rd_" + secrets.token_hex(24)

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE email = %s", (email_lower,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Email already registered")

        cur.execute(
            "INSERT INTO users (email, password_hash, api_key, tier) "
            "VALUES (%s, %s, %s, 'free') RETURNING id, email, tier, api_key",
            (email_lower, password_hash, api_key),
        )
        user = cur.fetchone()
        conn.commit()
        cur.close()

        return {
            "token": make_token(user["id"], user["email"], user["tier"]),
            "user": {"id": user["id"], "email": user["email"], "tier": user["tier"], "api_key": user["api_key"]},
        }
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.post("/login")
def login(req: LoginRequest):
    email_lower = req.email.lower().strip()

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, password_hash, tier, api_key FROM users WHERE email = %s",
            (email_lower,),
        )
        user = cur.fetchone()
        cur.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

    if not user or not pwd_context.verify(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "token": make_token(user["id"], user["email"], user["tier"]),
        "user": {"id": user["id"], "email": user["email"], "tier": user["tier"], "api_key": user["api_key"]},
    }


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["sub"])

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, tier, api_key, daily_usage, monthly_usage, "
            "subscription_status, billing_period_end, created_at FROM users WHERE id = %s",
            (user_id,),
        )
        user = cur.fetchone()
        cur.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(user)


@router.post("/regenerate-key")
def regenerate_key(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["sub"])
    new_key = "rd_" + secrets.token_hex(24)

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET api_key = %s WHERE id = %s RETURNING api_key",
            (new_key, user_id),
        )
        result = cur.fetchone()
        conn.commit()
        cur.close()
        return {"api_key": result["api_key"]}
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()
