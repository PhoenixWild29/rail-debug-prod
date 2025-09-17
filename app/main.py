"""
Rail Debugging Assistant API (modular, DI-based)
"""
import logging
from typing import Annotated, Callable, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic.types import constr
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from langgraph.graph import StateGraph, END

# Local modules
# (these are added in this refactor)
try:
    from .services.retrieval import RetrievalService
    from .agents.analyzer import AnalyzerService
    from .agents.quantized_analyzer import QuantizedAnalyzerService
    from .agents.dspy_analyzer import DSPyRAG
    from .core.prompts import get_production_analyzer_prompt
except ImportError:  # pragma: no cover
    # When running in environments that import as a script
    from services.retrieval import RetrievalService
    from agents.analyzer import AnalyzerService
    from agents.quantized_analyzer import QuantizedAnalyzerService
    from agents.dspy_analyzer import DSPyRAG
    from core.prompts import get_production_analyzer_prompt


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ----- Request/response models with validation -----

class FewShotExample(BaseModel):
    input: Annotated[str, Field(min_length=1, max_length=500)]
    output: Annotated[str, Field(min_length=1, max_length=500)]


class RailDebugRequest(BaseModel):
    query: Annotated[str, Field(min_length=5, max_length=500)]
    few_shot_examples: Annotated[List[FewShotExample], Field(min_length=0, max_length=5)] = []
    # Docs are accepted but NOT indexed in-request; kept for backwards compat
    docs: Annotated[List[Annotated[str, Field(min_length=1, max_length=2000)]], Field(min_length=0, max_length=50)] = []


class RailDebugResponse(BaseModel):
    result: str


# ----- Dependency providers -----

def get_retrieval_service() -> Optional[RetrievalService]:
    # Filled during startup; tests may override via dependency injection
    app_state = app.state
    return getattr(app_state, "retriever", None)


def get_analyzer_service() -> Optional[AnalyzerService]:
    app_state = app.state
    return getattr(app_state, "analyzer", None)


# ----- App factory -----

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize heavy clients once. If env not configured, keep None and return 400 at request time."""
    from .core.startup import build_retriever, build_analyzer

    retriever = build_retriever()
    analyzer = build_analyzer()

    app.state.retriever = retriever
    app.state.analyzer = analyzer
    yield
    # Cleanup if needed


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com", "https://app.yourdomain.com"],  # Replace with actual domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


def build_graph(retriever: RetrievalService, analyzer: AnalyzerService):
    """LangGraph with two steps: retrieve -> analyze. State is a dict."""
    def step_retrieve(state: Dict) -> Dict:
        q = state.get("query", "")
        context = retriever.retrieve_context(q, k=5)
        state["context"] = context
        return state

    def step_analyze(state: Dict) -> Dict:
        q = state.get("query", "")
        ctx = state.get("context", "")
        few_shot = state.get("few_shot_examples", [])
        result = analyzer.analyze(query=q, context=ctx, few_shot_examples=few_shot)
        state["result"] = result
        return state

    g = StateGraph(dict)
    g.add_node("retrieve", step_retrieve)
    g.add_node("analyze", step_analyze)
    g.add_edge("retrieve", "analyze")
    g.add_edge("analyze", END)
    g.set_entry_point("retrieve")
    return g.compile()


@app.post("/debug-rail-code", response_model=RailDebugResponse)
@limiter.limit("5/minute")
async def debug_rail_code(
    request: Request,
    req: RailDebugRequest,
    retriever: Optional[RetrievalService] = Depends(get_retrieval_service),
    analyzer: Optional[AnalyzerService] = Depends(get_analyzer_service),
):
    with tracer.start_as_current_span("debug_rail_code"):
        # Do not index per-request; only retrieve from existing index
        if retriever is None:
            raise HTTPException(status_code=400, detail="Index not available; initialize backend first")
        if analyzer is None:
            raise HTTPException(status_code=500, detail="Analyzer not available")

        graph = build_graph(retriever, analyzer)
        state = graph.invoke({"query": req.query, "few_shot_examples": [e.model_dump() for e in req.few_shot_examples]})
        result = state.get("result", "")
        # Keep result concise
        if len(result) > 2000:
            result = result[:2000] + " [truncated]"
        return {"result": result}


# ----- OpenTelemetry Setup -----

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

# Setup OpenTelemetry
trace.set_tracer_provider(TracerProvider())
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",  # or Jaeger collector host
    agent_port=6831,
)
span_processor = BatchSpanProcessor(jaeger_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)
tracer = trace.get_tracer(__name__)
