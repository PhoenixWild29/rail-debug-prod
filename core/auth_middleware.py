"""
core/auth_middleware.py — JWT decode, FastAPI auth dependencies, rate limiting.
Shared by routes/auth.py and routes/billing.py.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

TIER_DAILY_LIMITS = {"free": 10, "dev": 200, "team": None}
TIER_MONTHLY_LIMITS = {"free": 50, "dev": 2000, "team": None}


def get_db_conn():
    """Return a psycopg3 connection. Raises 500 if DATABASE_URL not set."""
    import psycopg
    from psycopg.rows import dict_row

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=500, detail="Database not configured")
    return psycopg.connect(db_url, row_factory=dict_row)


def make_token(user_id: int, email: str, tier: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "tier": tier,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """FastAPI dependency — requires valid JWT. Raises 401 if missing or invalid."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return decode_token(credentials.credentials)


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """FastAPI dependency — returns decoded JWT or None. Never raises."""
    if not credentials:
        return None
    try:
        return decode_token(credentials.credentials)
    except HTTPException:
        return None


def check_and_increment_usage(user_id: int, tier: str) -> None:
    """Check rate limits and increment counters. Raises 429 if over limit.
    Silently passes if DB is unavailable (non-blocking degradation)."""
    daily_limit = TIER_DAILY_LIMITS.get(tier)
    monthly_limit = TIER_MONTHLY_LIMITS.get(tier)

    if daily_limit is None and monthly_limit is None:
        return  # Unlimited tier

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    this_month = datetime.now(timezone.utc).strftime("%Y-%m")

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT daily_usage, monthly_usage, last_daily, last_monthly "
            "FROM users WHERE id = %s FOR UPDATE",
            (user_id,),
        )
        user = cur.fetchone()
        if not user:
            return

        daily_usage = user["daily_usage"] if user["last_daily"] == today else 0
        monthly_usage = (
            user["monthly_usage"]
            if (user["last_monthly"] or "")[:7] == this_month
            else 0
        )

        if daily_limit and daily_usage >= daily_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Daily limit of {daily_limit} analyses reached. Upgrade your plan.",
            )
        if monthly_limit and monthly_usage >= monthly_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Monthly limit of {monthly_limit} analyses reached. Upgrade your plan.",
            )

        cur.execute(
            "UPDATE users SET daily_usage = %s, monthly_usage = %s, "
            "last_daily = %s, last_monthly = %s WHERE id = %s",
            (daily_usage + 1, monthly_usage + 1, today, today, user_id),
        )
        conn.commit()
        cur.close()
    except HTTPException:
        raise
    except Exception:
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
