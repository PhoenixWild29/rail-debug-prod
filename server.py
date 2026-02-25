"""
Rail Debug API Server — FastAPI wrapper over the Quad-Tier Engine.

Launch:
    uvicorn server:app --host 0.0.0.0 --port 8000
    python cli.py --serve --port 8000
"""

from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core.analyzer import analyze, analyze_to_json, analyze_chained
from core.batch import analyze_batch, extract_tracebacks
from core.project import scan_project

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
def analyze_endpoint(req: AnalyzeRequest):
    try:
        report = analyze(
            traceback_text=req.traceback,
            deep=req.deep,
            haiku=req.haiku,
            project_path=req.project_path,
        )
        return _report_to_dict(report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/chain")
def analyze_chain_endpoint(req: ChainRequest):
    try:
        result = analyze_chained(
            traceback_text=req.traceback,
            deep=req.deep,
            haiku=req.haiku,
            project_path=req.project_path,
        )
        return {
            "chain_summary": result.chain_summary,
            "is_chained": result.is_chained,
            "reports": [_report_to_dict(r) for r in result.reports],
            "root_cause": _report_to_dict(result.root_cause_report) if result.root_cause_report else None,
            "final_error": _report_to_dict(result.final_report) if result.final_report else None,
            "total_linked": len(result.reports),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/batch")
def analyze_batch_endpoint(req: BatchRequest):
    try:
        tracebacks = extract_tracebacks(req.text)
        if not tracebacks:
            return {"reports": [], "total_errors": 0, "severity_counts": {}, "elapsed_seconds": 0.0}

        result = analyze_batch(
            tracebacks=tracebacks,
            deep=req.deep,
            haiku=req.haiku,
            project_path=req.project_path,
        )
        return {
            "reports": [_report_to_dict(r) for r in result.reports],
            "total_errors": result.total_errors,
            "severity_counts": result.severity_counts,
            "elapsed_seconds": result.elapsed_seconds,
        }
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
