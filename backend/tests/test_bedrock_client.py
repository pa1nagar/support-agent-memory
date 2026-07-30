"""
Tests for bedrock_client.py — system prompt building and response parsing logic.
All actual AWS calls are mocked.
"""

import pytest
import json
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _build_system_prompt
# ---------------------------------------------------------------------------

class TestBuildSystemPrompt:
    def _get_client(self):
        with patch("boto3.client"):
            from bedrock_client import BedrockClient
            client = BedrockClient.__new__(BedrockClient)
            client.llm_model_id = "us.anthropic.claude-sonnet-4-6"
            client.embedding_model_id = "amazon.titan-embed-text-v2:0"
            return client

    def test_prompt_contains_agent_identity(self):
        client = self._get_client()
        prompt = client._build_system_prompt([], None)
        assert "support agent" in prompt.lower()

    def test_prompt_includes_user_name_in_header(self):
        client = self._get_client()
        user_context = {
            "user_name": {"value": "Alice", "confidence": 0.95, "updated_at": "2026-07-01"}
        }
        prompt = client._build_system_prompt([], user_context)
        assert "Alice" in prompt
        # Name should appear early (in header, before body)
        assert prompt.index("Alice") < prompt.index("support agent")

    def test_prompt_includes_location(self):
        client = self._get_client()
        user_context = {
            "location": {"value": "India", "confidence": 0.90, "updated_at": "2026-07-01"}
        }
        prompt = client._build_system_prompt([], user_context)
        assert "India" in prompt

    def test_prompt_includes_all_user_context_keys(self):
        client = self._get_client()
        user_context = {
            "product_tier": {"value": "Enterprise", "confidence": 1.0, "updated_at": "2026-07-01"},
            "preferred_contact": {"value": "email", "confidence": 0.85, "updated_at": "2026-07-01"},
        }
        prompt = client._build_system_prompt([], user_context)
        assert "product_tier" in prompt
        assert "Enterprise" in prompt
        assert "preferred_contact" in prompt

    def test_prompt_includes_retrieved_memories(self):
        client = self._get_client()
        memories = [
            {
                "content": "I cannot log in to my dashboard",
                "created_at": "2026-07-26T10:30:00Z",
                "similarity": 0.92,
                "role": "user"
            }
        ]
        prompt = client._build_system_prompt(memories, None)
        assert "log in" in prompt
        assert "2026-07-26" in prompt
        assert "92%" in prompt

    def test_prompt_without_context_or_memories(self):
        client = self._get_client()
        prompt = client._build_system_prompt([], None)
        assert len(prompt) > 50
        assert "Guidelines" in prompt

    def test_prompt_returns_string(self):
        client = self._get_client()
        result = client._build_system_prompt([], {})
        assert isinstance(result, str)

    def test_multiple_memories_numbered(self):
        client = self._get_client()
        memories = [
            {"content": "First issue", "created_at": "2026-07-01", "similarity": 0.9, "role": "user"},
            {"content": "Second issue", "created_at": "2026-07-02", "similarity": 0.8, "role": "user"},
        ]
        prompt = client._build_system_prompt(memories, None)
        assert "1." in prompt
        assert "2." in prompt


# ---------------------------------------------------------------------------
# generate_embedding — mocked AWS call
# ---------------------------------------------------------------------------

class TestGenerateEmbedding:
    def _get_client_with_mock_boto(self, response_embedding=None):
        if response_embedding is None:
            response_embedding = [0.1] * 1024

        mock_boto_client = MagicMock()
        mock_response_body = json.dumps({"embedding": response_embedding}).encode()
        mock_boto_client.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=mock_response_body))
        }

        with patch("boto3.client", return_value=mock_boto_client):
            from bedrock_client import BedrockClient
            import importlib
            import bedrock_client as bc
            importlib.reload(bc)
            client = bc.BedrockClient.__new__(bc.BedrockClient)
            client.client = mock_boto_client
            client.embedding_model_id = "amazon.titan-embed-text-v2:0"
            client.llm_model_id = "us.anthropic.claude-sonnet-4-6"
            return client

    def test_returns_list_of_floats(self):
        client = self._get_client_with_mock_boto()
        result = client.generate_embedding("hello world")
        assert isinstance(result, list)
        assert all(isinstance(x, float) for x in result)

    def test_returns_1024_dimensions(self):
        client = self._get_client_with_mock_boto()
        result = client.generate_embedding("hello world")
        assert len(result) == 1024

    def test_request_body_has_correct_format(self):
        client = self._get_client_with_mock_boto()
        client.generate_embedding("test input")
        call_kwargs = client.client.invoke_model.call_args.kwargs
        body = json.loads(call_kwargs["body"])
        assert body["inputText"] == "test input"
        assert body["dimensions"] == 1024
        assert body["normalize"] is True

    def test_raises_on_empty_embedding_response(self):
        client = self._get_client_with_mock_boto(response_embedding=None)
        mock_body = json.dumps({}).encode()
        client.client.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=mock_body))
        }
        with pytest.raises(ValueError, match="No embedding returned"):
            client.generate_embedding("test")


# ---------------------------------------------------------------------------
# generate_response — Claude message format validation
# ---------------------------------------------------------------------------

class TestGenerateResponseClaude:
    def _get_claude_client(self, response_text="Test response"):
        mock_boto_client = MagicMock()
        mock_body = json.dumps({
            "content": [{"text": response_text}]
        }).encode()
        mock_boto_client.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=mock_body))
        }

        with patch("boto3.client", return_value=mock_boto_client):
            from bedrock_client import BedrockClient
            client = BedrockClient.__new__(BedrockClient)
            client.client = mock_boto_client
            client.embedding_model_id = "amazon.titan-embed-text-v2:0"
            client.llm_model_id = "us.anthropic.claude-sonnet-4-6"
            return client

    def test_claude_returns_response_text(self):
        client = self._get_claude_client("Hello, how can I help?")
        result = client.generate_response("Hi", [], None, None)
        assert result == "Hello, how can I help?"

    def test_claude_request_starts_with_user_message(self):
        client = self._get_claude_client()
        client.generate_response("My question", [], None, None)
        call_kwargs = client.client.invoke_model.call_args.kwargs
        body = json.loads(call_kwargs["body"])
        messages = body["messages"]
        assert len(messages) > 0
        assert messages[0]["role"] == "user"

    def test_claude_request_has_system_prompt(self):
        client = self._get_claude_client()
        client.generate_response("My question", [], None, None)
        call_kwargs = client.client.invoke_model.call_args.kwargs
        body = json.loads(call_kwargs["body"])
        assert "system" in body
        assert len(body["system"]) > 0

    def test_claude_no_consecutive_same_roles(self):
        """After merging, no two consecutive messages should have the same role."""
        client = self._get_claude_client()
        recent = [
            {"role": "user", "content": "First"},
            {"role": "user", "content": "Second"},   # consecutive — should be merged
            {"role": "assistant", "content": "Reply"},
        ]
        client.generate_response("Third", [], None, recent_messages=recent)
        call_kwargs = client.client.invoke_model.call_args.kwargs
        body = json.loads(call_kwargs["body"])
        messages = body["messages"]
        for i in range(len(messages) - 1):
            assert messages[i]["role"] != messages[i + 1]["role"], \
                f"Consecutive same roles at index {i}: {messages[i]['role']}"

    def test_claude_messages_start_with_user(self):
        """Claude API requires first message to be from user."""
        client = self._get_claude_client()
        recent = [
            {"role": "assistant", "content": "Leading assistant"},  # should be stripped
            {"role": "user", "content": "User follows"},
        ]
        client.generate_response("Current", [], None, recent_messages=recent)
        call_kwargs = client.client.invoke_model.call_args.kwargs
        body = json.loads(call_kwargs["body"])
        messages = body["messages"]
        assert messages[0]["role"] == "user"
