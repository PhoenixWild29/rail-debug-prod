import os
import logging
from typing import Optional

from langchain_openai import ChatOpenAI

# Import new analyzer classes
try:
    from ..agents.quantized_analyzer import QuantizedAnalyzerService
    from ..agents.dspy_analyzer import DSPyRAG
except ImportError:
    QuantizedAnalyzerService = None
    DSPyRAG = None


logger = logging.getLogger(__name__)


def build_retriever():
    """Build Weaviate retriever if env is configured; otherwise return None.

    Uses weaviate-client v4 API via `weaviate.connect_to_weaviate` (or similar),
    but defers gracefully if unavailable or misconfigured.
    """
    weaviate_url = os.getenv("WEAVIATE_URL")
    api_key = os.getenv("WEAVIATE_API_KEY")
    if not weaviate_url or not api_key:
        logger.info("WEAVIATE_URL/WEAVIATE_API_KEY not set; retrieval disabled")
        return None

    try:
        import weaviate

        # Prefer v4 connect helpers; fall back to Client if present
        client = None
        try:
            # Attempt v4 connection helper
            client = weaviate.connect_to_weaviate(
                http_host=weaviate_url.replace("https://", "").replace("http://", ""),
                http_secure=weaviate_url.startswith("https://"),
                auth_credentials=weaviate.AuthApiKey(api_key=api_key),
            )
        except Exception:
            try:
                client = weaviate.Client(weaviate_url, auth_client_secret=weaviate.AuthApiKey(api_key))
            except Exception:
                client = None

        if client is None:
            logger.warning("Failed to initialize Weaviate client; retrieval disabled")
            return None

        from ..services.retrieval import WeaviateRetrievalService

        return WeaviateRetrievalService(client)
    except Exception as e:
        logger.warning(f"Weaviate init error: {e} Retrieval disabled.")
        return None


def build_analyzer():
    analyzer_type = os.getenv("ANALYZER_TYPE", "openai")  # Options: openai, quantized, dspy

    if analyzer_type == "quantized":
        model_path = os.getenv("QUANTIZED_MODEL_PATH", "./models/rail-debug-model.gguf")
        return QuantizedAnalyzerService(model_path)
    elif analyzer_type == "dspy":
        return DSPyRAG()
    else:  # Default to OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            logger.info("OPENAI_API_KEY not set; analyzer disabled")
            return None
        try:
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
            from ..agents.analyzer import AnalyzerService

            return AnalyzerService(llm)
        except Exception as e:
            logger.warning(f"Analyzer init error: {e}")
            return None

