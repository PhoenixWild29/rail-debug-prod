import logging
from typing import List


logger = logging.getLogger(__name__)


class RetrievalService:
    """Interface for retrieval services."""

    def retrieve_context(self, query: str, k: int = 5) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class WeaviateRetrievalService(RetrievalService):
    """Weaviate v4-style retrieval.

    Expects an existing collection named "RailDoc" with a text property "content".
    Uses SentenceTransformer embeddings computed client-side or server-side depending on
    your Weaviate setup. For simplicity, this implementation uses near_text when available.
    """

    def __init__(self, client):
        self.client = client
        try:
            self.collection = self.client.collections.get("RailDoc")
        except Exception:
            # Collection may not exist yet
            self.collection = None

    def retrieve_context(self, query: str, k: int = 5) -> str:
        if self.collection is None:
            try:
                self.collection = self.client.collections.get("RailDoc")
            except Exception:
                logger.warning("Weaviate collection 'RailDoc' not found")
                return ""

        try:
            # Prefer near_text if available (text2vec enabled); fallback to bm25 if configured
            results: List[str] = []
            try:
                out = self.collection.query.near_text(query=query, limit=k)
                for obj in out.objects:
                    content = obj.properties.get("content", "")
                    if content:
                        results.append(content)
            except Exception:
                # Try BM25 (if module enabled)
                out = self.collection.query.bm25(query=query, limit=k)
                for obj in out.objects:
                    content = obj.properties.get("content", "")
                    if content:
                        results.append(content)

            context = "\n".join(results)
            if len(context) > 2000:
                context = context[:2000] + " [truncated]"
            return context
        except Exception as e:
            logger.error(f"Weaviate retrieval error: {e}")
            return ""

