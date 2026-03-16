"""
Rail Debug API Server — FastAPI wrapper over the Quad-Tier Engine.

Launch:
    uvicorn server:app --host 0.0.0.0 --port 8000
    python cli.py --serve --port 8000
"""

from dataclasses import asdict
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.analyzer import analyze, analyze_to_json, analyze_chained
from core.auth_middleware import (
    TIER_MAX_AI,
    check_and_increment_usage,
    get_analyze_user,
    get_db_conn,
)
from core.context import detect_language
from core.batch import analyze_batch
from core.project import scan_project
from routes.auth import router as auth_router
from routes.billing import router as billing_router
from routes.github import router as github_router
from routes.waitlist import router as waitlist_router
from routes.webhooks import router as webhooks_router

TIER_NAMES = {
    1: "regex",
    2: "grok",
    3: "haiku",
    4: "sonnet",
}

# ── App ──────────────────────────────────────────────────────────

app = FastAPI(
    title="Rail Debug API",
    description="Quad-Tier AI Error Analysis Engine",
    version="0.10.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(github_router)
app.include_router(waitlist_router)
app.include_router(webhooks_router)

from routes.dashboard import router as dashboard_router
app.include_router(dashboard_router)

# ── Request / Response Models ────────────────────────────────────

class AnalyzeRequest(BaseModel):
    traceback: str
    deep: bool = False
    haiku: bool = False
    project_path: Optional[str] = None
    no_git: bool = False

class ChainRequest(BaseModel):
    traceback: str
    deep: bool = False
    haiku: bool = False
    project_path: Optional[str] = None

class BatchRequest(BaseModel):
    text: str
    deep: bool = False
    haiku: bool = False
    project_path: Optional[str] = None

class ScanRequest(BaseModel):
    project_path: str

# ── Helpers ──────────────────────────────────────────────────────

def _report_to_dict(report) -> dict:
    """Convert a DebugReport dataclass to a JSON-safe dict."""
    d = asdict(report)
    d.pop("raw_traceback", None)      # Strip bulky raw text
    d.pop("git_context_raw", None)    # Strip non-serializable objects
    return d

# ── Endpoints ────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.10.0"}


@app.post("/analyze")
def analyze_endpoint(req: AnalyzeRequest, user: Optional[dict] = Depends(get_analyze_user)):
    tier = user.get("tier", "free") if user else "free"
    max_tier = TIER_MAX_AI.get(tier, 1)
    user_id = int(user["sub"]) if user else None

    if user_id:
        check_and_increment_usage(user_id, tier)

    try:
        report = analyze(
            traceback_text=req.traceback,
            deep=req.deep,
            haiku=req.haiku,
            project_path=req.project_path,
            max_tier=max_tier,
        )
        lang = detect_language(req.traceback)
        tier_used = TIER_NAMES.get(report.tier, "unknown")
        if user_id is not None:
            conn = get_db_conn()
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO analyses (user_id, language, tier_used, severity) VALUES (%s, %s, %s, %s)",
                    (user_id, lang, tier_used, report.severity)
                )
                conn.commit()
            except Exception as log_e:
                print(f"Analysis log failed: {log_e}")
            finally:
                conn.close()
        return _report_to_dict(report)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/chain")
def analyze_chain_endpoint(req: ChainRequest, user: Optional[dict] = Depends(get_analyze_user)):
    tier = user.get("tier", "free") if user else "free"
    max_tier = TIER_MAX_AI.get(tier, 1)
    user_id = int(user["sub"]) if user else None

    if user_id:
        check_and_increment_usage(user_id, tier)

    try:
        result = analyze_chained(
            traceback_text=req.traceback,
            deep=req.deep,
            haiku=req.haiku,
            project_path=req.project_path,
            max_tier=max_tier,
        )
        return {
            "chain_summary": result.chain_summary,
            "is_chained": result.is_chained,
            "reports": [_report_to_dict(r) for r in result.reports],
            "root_cause": _report_to_dict(result.root_cause_report) if result.root_cause_report else None,
            "final_error": _report_to_dict(result.final_report) if result.final_report else None,
            "total_linked": len(result.reports),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/batch")
def analyze_batch_endpoint(req: BatchRequest, user: Optional[dict] = Depends(get_analyze_user)):
    tier = user.get("tier", "free") if user else "free"
    max_tier = TIER_MAX_AI.get(tier, 1)
    user_id = int(user["sub"]) if user else None

    if user_id:
        check_and_increment_usage(user_id, tier)

    try:
        result = analyze_batch(
            text=req.text,
            deep=req.deep,
            haiku=req.haiku,
            project_path=req.project_path,
            max_tier=max_tier,
        )
        return {
            "reports": [_report_to_dict(r) for r in result.reports],
            "total_errors": result.total_errors,
            "severity_counts": result.severity_counts,
            "elapsed_seconds": result.elapsed_seconds,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/project/scan")
def scan_project_endpoint(req: ScanRequest):
    try:
        profile = scan_project(req.project_path)
        return profile.to_dict()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project path not found: {req.project_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
