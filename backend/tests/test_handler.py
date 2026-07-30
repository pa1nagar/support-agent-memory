"""
Tests for handler.py — API endpoints and helper functions.
All DB and Bedrock calls are mocked.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_healthy_when_all_up(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data

    def test_degraded_when_bedrock_down(self, client, mock_db, mock_bedrock):
        mock_bedrock.health_check.return_value = False
        with patch("handler.get_db_manager", return_value=mock_db), \
             patch("handler.get_bedrock_client", return_value=mock_bedrock):
            from handler import app
            from fastapi.testclient import TestClient
            with TestClient(app, raise_server_exceptions=False) as c:
                response = c.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"

    def test_unhealthy_when_db_down(self, client, mock_db, mock_bedrock):
        mock_db.health_check.return_value = False
        with patch("handler.get_db_manager", return_value=mock_db), \
             patch("handler.get_bedrock_client", return_value=mock_bedrock):
            from handler import app
            from fastapi.testclient import TestClient
            with TestClient(app, raise_server_exceptions=False) as c:
                response = c.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "unhealthy"


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

class TestChatEndpoint:
    def test_basic_chat_returns_200(self, client):
        response = client.post("/chat", json={
            "user_id": "test-user-1",
            "message": "Hello, I need help",
        })
        assert response.status_code == 200

    def test_chat_response_has_required_fields(self, client):
        response = client.post("/chat", json={
            "user_id": "test-user-1",
            "message": "Hello",
        })
        data = response.json()
        assert "response" in data
        assert "conversation_id" in data
        assert "memories_used" in data
        assert "processing_time_ms" in data

    def test_chat_response_text_matches_mock(self, client, mock_bedrock):
        mock_bedrock.generate_response.return_value = "Mock agent response here."
        response = client.post("/chat", json={
            "user_id": "test-user-1",
            "message": "What is my issue?",
        })
        assert response.json()["response"] == "Mock agent response here."

    def test_chat_with_existing_conversation_id(self, client, mock_db):
        mock_db.get_or_create_conversation.return_value = {
            "conv_id": "aaaaaaaa-0000-0000-0000-000000000001",
            "user_id": "test-user-1",
            "title": "Existing conv",
            "status": "active",
        }
        response = client.post("/chat", json={
            "user_id": "test-user-1",
            "message": "Follow up question",
            "conversation_id": "aaaaaaaa-0000-0000-0000-000000000001",
        })
        assert response.status_code == 200
        assert response.json()["conversation_id"] == "aaaaaaaa-0000-0000-0000-000000000001"

    def test_chat_with_memories_returns_them(self, client, mock_db, sample_memory_row):
        mock_db.search_similar_messages.return_value = [sample_memory_row]
        response = client.post("/chat", json={
            "user_id": "test-user-1",
            "message": "Still having login issues",
        })
        data = response.json()
        assert len(data["memories_used"]) == 1
        assert data["memories_used"][0]["confidence"] == 0.92
        assert "log in" in data["memories_used"][0]["content"]

    def test_chat_stores_user_message(self, client, mock_db):
        client.post("/chat", json={
            "user_id": "test-user-1",
            "message": "Test message",
        })
        calls = [call for call in mock_db.store_message.call_args_list
                 if call.args[2] == "user" or call.kwargs.get("role") == "user"]
        assert len(calls) >= 1

    def test_chat_stores_assistant_message(self, client, mock_db):
        client.post("/chat", json={
            "user_id": "test-user-1",
            "message": "Test message",
        })
        calls = [call for call in mock_db.store_message.call_args_list
                 if call.args[2] == "assistant" or call.kwargs.get("role") == "assistant"]
        assert len(calls) >= 1

    def test_chat_generates_embedding_once_for_user_message(self, client, mock_bedrock):
        """Embedding for the user message should be generated exactly once (reused)."""
        client.post("/chat", json={
            "user_id": "test-user-1",
            "message": "Test message",
        })
        # Called once for user message + once for assistant response = 2 total
        # NOT 3 (old bug where it was called 3 times)
        assert mock_bedrock.generate_embedding.call_count == 2

    def test_chat_rejects_empty_message(self, client):
        response = client.post("/chat", json={
            "user_id": "test-user-1",
            "message": "",
        })
        assert response.status_code == 422

    def test_chat_rejects_message_too_long(self, client):
        response = client.post("/chat", json={
            "user_id": "test-user-1",
            "message": "x" * 5001,
        })
        assert response.status_code == 422

    def test_chat_rejects_missing_user_id(self, client):
        response = client.post("/chat", json={
            "message": "Hello",
        })
        assert response.status_code == 422

    def test_chat_continues_when_memory_retrieval_fails(self, client, mock_db, mock_bedrock):
        """If vector search fails, chat should still return a response."""
        mock_db.search_similar_messages.side_effect = Exception("DB connection lost")
        response = client.post("/chat", json={
            "user_id": "test-user-1",
            "message": "Hello",
        })
        assert response.status_code == 200
        assert response.json()["memories_used"] == []

    def test_chat_processing_time_is_positive(self, client):
        response = client.post("/chat", json={
            "user_id": "test-user-1",
            "message": "Hello",
        })
        assert response.json()["processing_time_ms"] >= 0


# ---------------------------------------------------------------------------
# Memory debug endpoint
# ---------------------------------------------------------------------------

class TestMemoryDebug:
    def test_blocked_without_token(self, client):
        response = client.get("/memory-debug/test-user-1")
        assert response.status_code == 403

    def test_blocked_with_wrong_token(self, client):
        response = client.get("/memory-debug/test-user-1?token=wrong-token")
        assert response.status_code == 403

    def test_accessible_with_correct_token(self, client, mock_db, mock_bedrock):
        import os
        token = os.environ.get("DEBUG_TOKEN", "test-debug-token-123")
        response = client.get(f"/memory-debug/test-user-1?token={token}")
        assert response.status_code == 200

    def test_returns_memory_data(self, client, mock_db, mock_bedrock, sample_memory_row):
        import os
        mock_db.search_similar_messages.return_value = [sample_memory_row]
        token = os.environ.get("DEBUG_TOKEN", "test-debug-token-123")
        response = client.get(f"/memory-debug/test-user-1?token={token}")
        data = response.json()
        assert "memories" in data
        assert "user_context" in data
        assert data["memories_found"] == 1

    def test_rejects_user_id_too_long(self, client):
        import os
        token = os.environ.get("DEBUG_TOKEN", "test-debug-token-123")
        long_id = "x" * 129
        response = client.get(f"/memory-debug/{long_id}?token={token}")
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------

class TestRoot:
    def test_root_returns_200(self, client):
        # When frontend doesn't exist, returns JSON health response
        response = client.get("/")
        assert response.status_code in (200, 404)  # 200 if frontend exists, varies otherwise
