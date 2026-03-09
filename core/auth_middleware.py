"""
core/auth_middleware.py — JWT decode, FastAPI auth dependencies, rate limiting.
Shared by routes/auth.py and routes/billing.py.
"""
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

TIER_DAILY_LIMITS = {"free": 20, "dev": 500, "team": None}
TIER_MONTHLY_LIMITS = {"free": 100, "dev": 10000, "team": None}


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

        new_monthly = monthly_usage + 1
        cur.execute(
            "UPDATE users SET daily_usage = %s, monthly_usage = %s, "
            "last_daily = %s, last_monthly = %s WHERE id = %s",
            (daily_usage + 1, new_monthly, today, today, user_id),
        )
        conn.commit()

        # Fire 80% nudge email once when crossing the threshold
        if monthly_limit and monthly_usage < int(monthly_limit * 0.8) <= new_monthly:
            cur.execute("SELECT email, tier FROM users WHERE id = %s", (user_id,))
            nudge_user = cur.fetchone()
            if nudge_user:
                from services.email_service import send_usage_nudge_email
                threading.Thread(
                    target=send_usage_nudge_email,
                    args=(nudge_user["email"], nudge_user["tier"], new_monthly, monthly_limit),
                    daemon=True,
                ).start()

        cur.close()
    except HTTPException:
        raise
    except Exception:
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
