"""
routes/dashboard.py — User dashboard API.
"""

from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from core.auth_middleware import (
    get_current_user,
    get_db_conn,
    TIER_DAILY_LIMITS,
    TIER_MONTHLY_LIMITS,
    TIER_MINUTE_LIMITS,
)


router = APIRouter()


@router.get("/api/user/dashboard")
def get_user_dashboard(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    user_id = int(current_user["sub"])

    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT email, tier, monthly_usage, monthly_limit FROM users WHERE id = %s",
            (user_id,),
        )
        user_data = cur.fetchone()
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        monthly_usage = user_data["monthly_usage"] or 0
        monthly_limit = user_data["monthly_limit"] or 0
        usage_pct = round((monthly_usage / monthly_limit * 100), 1) if monthly_limit > 0 else 0.0
        
        # Next reset date: first of next month
        now = datetime.now(timezone.utc)
        if now.month == 12:
            year = now.year + 1
            month = 1
        else:
            year = now.year
            month = now.month + 1
        reset_date = f"{year}-{month:02d}-01"
        
        return {
            "email": user_data["email"],
            "tier": user_data["tier"],
            "monthly_usage": int(monthly_usage),
            "monthly_limit": int(monthly_limit),
            "usage_pct": usage_pct,
            "reset_date": reset_date,
        }
    finally:
        conn.close()

@router.get("/api/user/usage")
def get_user_usage(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    user_id = int(current_user["sub"])
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    this_month = now.strftime("%Y-%m")
    current_minute = now.strftime("%Y-%m-%d %H:%M")

    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT tier, daily_usage, monthly_usage, last_daily, last_monthly, "
            "minute_usage, last_minute FROM users WHERE id = %s",
            (user_id,),
        )
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        tier = user["tier"]
        daily = user["daily_usage"] if user["last_daily"] == today else 0
        monthly = user["monthly_usage"] if (user["last_monthly"] or "")[:7] == this_month else 0
        minute = user["minute_usage"] if user.get("last_minute") == current_minute else 0

        return {
            "tier": tier,
            "minute": {"used": minute, "limit": TIER_MINUTE_LIMITS.get(tier)},
            "daily": {"used": daily, "limit": TIER_DAILY_LIMITS.get(tier)},
            "monthly": {"used": monthly, "limit": TIER_MONTHLY_LIMITS.get(tier)},
        }
    finally:
        conn.close()


@router.get("/api/user/telemetry")
def get_user_telemetry(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    user_id = int(current_user["sub"])
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT date_trunc('month', NOW() AT TIME ZONE 'UTC') as month_start;")
        month_start = cur.fetchone()["month_start"]
        cur.execute("SELECT COUNT(*)::int as count FROM analyses WHERE user_id = %s AND created_at >= %s;", (user_id, month_start))
        row = cur.fetchone()
        this_month = row["count"] if row else 0
        cur.execute("SELECT language, COUNT(*)::int as count FROM analyses WHERE user_id = %s AND created_at >= %s GROUP BY language;", (user_id, month_start))
        langs = {row["language"]: row["count"] for row in cur.fetchall()}
        cur.execute("SELECT tier_used, COUNT(*)::int as count FROM analyses WHERE user_id = %s AND created_at >= %s GROUP BY tier_used;", (user_id, month_start))
        tiers = {row["tier_used"]: row["count"] for row in cur.fetchall()}
        cur.execute("SELECT date_trunc('day', created_at)::date as date, COUNT(*)::int as count FROM analyses WHERE user_id = %s AND created_at >= NOW() - INTERVAL '30 days' GROUP BY date ORDER BY date;", (user_id,))
        daily = [{"date": str(row["date"]), "count": row["count"]} for row in cur.fetchall()]
        cur.execute("SELECT AVG(CASE WHEN severity='low' THEN 1.0 WHEN severity='medium' THEN 2.0 WHEN severity='high' THEN 3.0 WHEN severity='critical' THEN 4.0 END) as avg_score FROM analyses WHERE user_id = %s;", (user_id,))
        row = cur.fetchone()
        avg = round(float(row["avg_score"] or 0.0), 1)
        return {
            "analyses_this_month": this_month,
            "analyses_by_language": langs,
            "analyses_by_tier": tiers,
            "daily_usage": daily,
            "avg_severity": avg,
        }
    finally:
        conn.close()
