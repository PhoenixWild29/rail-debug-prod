"""
routes/dashboard.py — User dashboard API.
"""

from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from core.auth_middleware import get_current_user, get_db_conn


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
