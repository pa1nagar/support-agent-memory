"""
Shared fixtures for all tests.
Uses mocking so tests run without real AWS or CockroachDB credentials.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Environment setup — must happen before any app imports
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def mock_env(monkeypatch_session):
    """Inject required env vars so Settings() doesn't raise on import."""
    monkeypatch_session.setenv("COCKROACHDB_URL", "postgresql://fake:fake@localhost:26257/testdb")
    monkeypatch_session.setenv("AWS_REGION", "us-east-1")
    monkeypatch_session.setenv("ENVIRONMENT", "test")
    monkeypatch_session.setenv("DEBUG_TOKEN", "test-debug-token-123")


@pytest.fixture(scope="session")
def monkeypatch_session():
    """Session-scoped monkeypatch (pytest only provides function-scoped by default)."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


# ---------------------------------------------------------------------------
# Mock DB manager
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_or_create_user.return_value = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "email": "test@example.com",
        "name": "Test User",
    }
    db.get_or_create_conversation.return_value = {
        "conv_id": "00000000-0000-0000-0000-000000000010",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "title": "Test conversation",
        "status": "active",
    }
    db.search_similar_messages.return_value = []
    db.get_user_context.return_value = {}
    db.get_recent_messages.return_value = []
    db.store_message.return_value = "00000000-0000-0000-0000-000000000100"
    db.log_memory_retrieval.return_value = None
    db.upsert_user_context.return_value = None
    db.health_check.return_value = True
    return db


# ---------------------------------------------------------------------------
# Mock Bedrock client
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_bedrock():
    bedrock = MagicMock()
    bedrock.generate_embedding.return_value = [0.1] * 1024
    bedrock.generate_response.return_value = "I can help you with that."
    bedrock.health_check.return_value = True
    return bedrock


# ---------------------------------------------------------------------------
# FastAPI test client with mocked dependencies
# ---------------------------------------------------------------------------

@pytest.fixture
def client(mock_db, mock_bedrock):
    """
    TestClient with database and Bedrock replaced by mocks.
    Tests run instantly with no network calls.
    """
    with patch("handler.get_db_manager", return_value=mock_db), \
         patch("handler.get_bedrock_client", return_value=mock_bedrock):
        from handler import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_user_id():
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def sample_conv_id():
    return "00000000-0000-0000-0000-000000000010"


@pytest.fixture
def sample_embedding():
    return [0.1] * 1024


@pytest.fixture
def sample_memory_row():
    """Simulates a row returned from search_similar_messages."""
    from datetime import datetime, timezone
    return {
        "msg_id": "00000000-0000-0000-0000-000000000100",
        "content": "I cannot log in to my dashboard",
        "role": "user",
        "created_at": datetime(2026, 7, 26, 10, 30, 0, tzinfo=timezone.utc),
        "similarity": 0.92,
    }
