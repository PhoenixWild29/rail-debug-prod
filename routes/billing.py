"""
routes/billing.py — Stripe Checkout, Customer Portal, webhook, billing status.
All routes mounted at /billing/* via server.py.
Webhook: POST /billing/webhook (configure in Stripe dashboard)
"""
import datetime
import os

import stripe as stripe_lib
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.auth_middleware import get_current_user, get_db_conn

router = APIRouter(prefix="/billing")

PLAN_TIER_MAP = {"dev": "dev", "team": "team"}


def _stripe():
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    stripe_lib.api_key = key
    return stripe_lib


class CheckoutRequest(BaseModel):
    plan: str  # "dev" or "team"


@router.post("/checkout")
def create_checkout(req: CheckoutRequest, current_user: dict = Depends(get_current_user)):
    if req.plan not in ("dev", "team"):
        raise HTTPException(status_code=422, detail="Invalid plan. Choose 'dev' or 'team'.")

    price_id = os.getenv(f"STRIPE_PRICE_{req.plan.upper()}")
    if not price_id:
        raise HTTPException(status_code=500, detail=f"Stripe price for '{req.plan}' not configured")

    stripe = _stripe()
    user_id = int(current_user["sub"])
    email = current_user.get("email", "")

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT stripe_customer_id FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        customer_id = user["stripe_customer_id"] if user else None
        cur.close()
        conn.close()
        conn = None

        if not customer_id:
            customer = stripe.Customer.create(
                email=email, metadata={"user_id": str(user_id)}
            )
            customer_id = customer.id
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET stripe_customer_id = %s WHERE id = %s",
                (customer_id, user_id),
            )
            conn.commit()
            cur.close()

        domain = os.getenv("SITE_DOMAIN", "https://debug.secureai.dev")
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{domain}/dashboard?upgrade=success",
            cancel_url=f"{domain}/dashboard?upgrade=canceled",
            metadata={"user_id": str(user_id), "plan": req.plan},
        )
        return {"checkout_url": session.url}

    except stripe_lib.error.StripeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.post("/portal")
def customer_portal(current_user: dict = Depends(get_current_user)):
    stripe = _stripe()
    user_id = int(current_user["sub"])

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT stripe_customer_id FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        cur.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

    if not user or not user["stripe_customer_id"]:
        raise HTTPException(status_code=400, detail="No billing account found. Subscribe first.")

    try:
        domain = os.getenv("SITE_DOMAIN", "https://debug.secureai.dev")
        session = stripe_lib.billing_portal.Session.create(
            customer=user["stripe_customer_id"],
            return_url=f"{domain}/dashboard",
        )
        return {"portal_url": session.url}
    except stripe_lib.error.StripeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def billing_status(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["sub"])

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT tier, subscription_status, billing_period_end, "
            "daily_usage, monthly_usage FROM users WHERE id = %s",
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


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request):
    stripe = _stripe()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_lib.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe_lib.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    _handle_event(event)
    return {"received": True}


def _handle_event(event: dict) -> None:
    etype = event["type"]
    data = event["data"]["object"]

    dispatch = {
        "checkout.session.completed": _activate_subscription,
        "customer.subscription.updated": _update_subscription,
        "customer.subscription.deleted": _cancel_subscription,
        "invoice.payment_failed": _mark_payment_failed,
    }
    handler = dispatch.get(etype)
    if handler:
        handler(data)


def _activate_subscription(session: dict) -> None:
    user_id = (session.get("metadata") or {}).get("user_id")
    plan = (session.get("metadata") or {}).get("plan", "dev")
    tier = PLAN_TIER_MAP.get(plan, "dev")
    sub_id = session.get("subscription")
    customer_id = session.get("customer")

    if not user_id:
        return

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET tier = %s, stripe_subscription_id = %s, "
            "stripe_customer_id = %s, subscription_status = 'active' WHERE id = %s",
            (tier, sub_id, customer_id, int(user_id)),
        )
        conn.commit()
        cur.close()
    except Exception:
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


def _update_subscription(sub: dict) -> None:
    customer_id = sub.get("customer")
    sub_status = sub.get("status", "active")
    period_end = sub.get("current_period_end")
    period_end_dt = (
        datetime.datetime.fromtimestamp(period_end, tz=datetime.timezone.utc)
        if period_end
        else None
    )

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET subscription_status = %s, billing_period_end = %s "
            "WHERE stripe_customer_id = %s",
            (sub_status, period_end_dt, customer_id),
        )
        conn.commit()
        cur.close()
    except Exception:
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


def _cancel_subscription(sub: dict) -> None:
    customer_id = sub.get("customer")

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET tier = 'free', subscription_status = 'canceled', "
            "stripe_subscription_id = NULL WHERE stripe_customer_id = %s",
            (customer_id,),
        )
        conn.commit()
        cur.close()
    except Exception:
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


def _mark_payment_failed(invoice: dict) -> None:
    customer_id = invoice.get("customer")

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET subscription_status = 'past_due' "
            "WHERE stripe_customer_id = %s",
            (customer_id,),
        )
        conn.commit()
        cur.close()
    except Exception:
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
