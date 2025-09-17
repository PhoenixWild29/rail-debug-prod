import pytest
from fastapi.testclient import TestClient
from app.main import app, get_retrieval_service, get_analyzer_service


class FakeRetriever:
    def retrieve_context(self, query: str, k: int = 5) -> str:
        return "fake rail context"


class FakeAnalyzer:
    def analyze(self, query: str, context: str, few_shot_examples):
        return f"Analyzed: {query} | Ctx: {context}"


def test_debug_rail_code():
    # Override DI to avoid external services
    app.dependency_overrides[get_retrieval_service] = lambda: FakeRetriever()
    app.dependency_overrides[get_analyzer_service] = lambda: FakeAnalyzer()

    client = TestClient(app)
    response = client.post(
        "/debug-rail-code",
        json={
            "query": "Why does this rail code fail?",
            "few_shot_examples": [{"input": "Sensor error", "output": "Check sensor wiring."}],
            "docs": ["Rail sensor code guide.", "Control algorithm wiki."],
        },
    )
    assert response.status_code == 200
    j = response.json()
    assert "result" in j and j["result"].startswith("Analyzed:")

    # Cleanup overrides
    app.dependency_overrides = {}
