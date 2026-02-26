from typing import Optional
import os
import re
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

router = APIRouter(prefix="/waitlist")

class WaitlistRequest(BaseModel):
    email: EmailStr
    first_name: Optional[str] = Field(None, max_length=100)
    tier_interest: Optional[str] = Field("free", pattern=r"^(free|dev|team)$")

@router.post("/", status_code=status.HTTP_200_OK, response_model=dict)
async def join_waitlist(req: WaitlistRequest):
    # Connect to DB
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=500, detail="Database not configured")

    import psycopg2
    from psycopg2.extras import RealDictCursor

    email_lower = req.email.lower().strip()

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Check if already exists
        cur.execute(
            "SELECT id, created_at FROM waitlist WHERE LOWER(email) = %s",
            (email_lower,)
        )
        existing = cur.fetchone()

        if existing:
            return {
                "success": True,
                "message": "You're already on the list! We'll notify you when ready.",
                "joined_at": existing["created_at"].isoformat()
            }

        # Insert new
        cur.execute(
            """
            INSERT INTO waitlist (email, first_name, tier_interest, source)
            VALUES (%s, %s, %s, 'marketing-site')
            RETURNING id, created_at
            """,
            (email_lower, req.first_name, req.tier_interest)
        )
        new_entry = cur.fetchone()

        conn.commit()
        return {
            "success": True,
            "message": "Welcome to the waitlist! We'll be in touch soon. 🚀",
            "joined_at": new_entry["created_at"].isoformat()
        }

    except psycopg2.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=409, detail="Email already exists")
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()