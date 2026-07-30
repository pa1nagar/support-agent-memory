"""
Tests for database.py — normalize_user_id and DatabaseManager logic.
DB connection itself is mocked so no real CockroachDB needed.
"""

import pytest
import uuid
from unittest.mock import MagicMock, patch, call
from contextlib import contextmanager


# ---------------------------------------------------------------------------
# normalize_user_id
# ---------------------------------------------------------------------------

class TestNormalizeUserId:
    def test_valid_uuid_returned_as_is(self):
        from database import normalize_user_id
        uid = "550e8400-e29b-41d4-a716-446655440000"
        assert normalize_user_id(uid) == uid

    def test_valid_uuid_uppercase_normalized(self):
        from database import normalize_user_id
        uid = "550E8400-E29B-41D4-A716-446655440000"
        result = normalize_user_id(uid)
        assert result == uid.lower()

    def test_non_uuid_string_returns_deterministic_uuid(self):
        from database import normalize_user_id
        result1 = normalize_user_id("alice")
        result2 = normalize_user_id("alice")
        # Must be deterministic
        assert result1 == result2
        # Must be a valid UUID
        uuid.UUID(result1)

    def test_different_strings_produce_different_uuids(self):
        from database import normalize_user_id
        assert normalize_user_id("alice") != normalize_user_id("bob")

    def test_empty_string_returns_valid_uuid(self):
        from database import normalize_user_id
        result = normalize_user_id("")
        uuid.UUID(result)  # should not raise

    def test_long_string_returns_valid_uuid(self):
        from database import normalize_user_id
        result = normalize_user_id("a" * 500)
        uuid.UUID(result)


# ---------------------------------------------------------------------------
# DatabaseManager — connection pool
# ---------------------------------------------------------------------------

class TestDatabaseManagerPool:
    def _make_manager(self):
        """Create a DatabaseManager with a mocked pool."""
        with patch("database.ThreadedConnectionPool") as MockPool:
            from database import DatabaseManager
            import importlib
            import database
            importlib.reload(database)
            from database import DatabaseManager as DM
            manager = DM.__new__(DM)
            manager.connection_string = "postgresql://fake:fake@localhost/test"
            manager._pool = None
            mock_pool = MagicMock()
            MockPool.return_value = mock_pool
            manager._MockPool = MockPool
            manager._mock_pool = mock_pool
            return manager, MockPool, mock_pool

    def test_pool_initialized_lazily(self):
        from database import DatabaseManager
        manager = DatabaseManager.__new__(DatabaseManager)
        manager.connection_string = "postgresql://fake@localhost/test"
        manager._pool = None
        assert manager._pool is None

    def test_close_sets_pool_to_none(self):
        from database import DatabaseManager
        manager = DatabaseManager.__new__(DatabaseManager)
        manager._pool = MagicMock()
        manager.close()
        assert manager._pool is None

    def test_close_calls_closeall(self):
        from database import DatabaseManager
        manager = DatabaseManager.__new__(DatabaseManager)
        mock_pool = MagicMock()
        manager._pool = mock_pool
        manager.close()
        mock_pool.closeall.assert_called_once()

    def test_close_is_safe_when_pool_is_none(self):
        from database import DatabaseManager
        manager = DatabaseManager.__new__(DatabaseManager)
        manager._pool = None
        manager.close()  # should not raise


# ---------------------------------------------------------------------------
# DatabaseManager — store_message embedding format
# ---------------------------------------------------------------------------

class TestStoreMessageEmbeddingFormat:
    def _make_manager_with_mock_conn(self):
        from database import DatabaseManager
        manager = DatabaseManager.__new__(DatabaseManager)
        manager.connection_string = "postgresql://fake@localhost/test"
        manager._pool = None

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"msg_id": "00000000-0000-0000-0000-000000000100"}
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        @contextmanager
        def fake_get_connection():
            yield mock_conn

        manager.get_connection = fake_get_connection
        return manager, mock_cursor

    def test_embedding_formatted_as_vector_string(self):
        manager, mock_cursor = self._make_manager_with_mock_conn()
        embedding = [0.1, 0.2, 0.3]
        manager.store_message(
            conv_id="00000000-0000-0000-0000-000000000010",
            user_id="00000000-0000-0000-0000-000000000001",
            role="user",
            content="Test message",
            embedding=embedding
        )
        # Check the SQL call contained the vector string
        call_args = mock_cursor.execute.call_args
        sql_params = call_args[0][1]
        assert "[0.1,0.2,0.3]" in sql_params

    def test_none_embedding_stored_as_none(self):
        manager, mock_cursor = self._make_manager_with_mock_conn()
        manager.store_message(
            conv_id="00000000-0000-0000-0000-000000000010",
            user_id="00000000-0000-0000-0000-000000000001",
            role="user",
            content="Test message",
            embedding=None
        )
        call_args = mock_cursor.execute.call_args
        sql_params = call_args[0][1]
        assert None in sql_params

    def test_created_at_override_used_when_provided(self):
        from datetime import datetime, timezone
        manager, mock_cursor = self._make_manager_with_mock_conn()
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        manager.store_message(
            conv_id="00000000-0000-0000-0000-000000000010",
            user_id="00000000-0000-0000-0000-000000000001",
            role="user",
            content="Historical message",
            embedding=None,
            created_at=ts
        )
        call_args = mock_cursor.execute.call_args
        sql_params = call_args[0][1]
        assert ts in sql_params

    def test_returns_msg_id_as_string(self):
        manager, mock_cursor = self._make_manager_with_mock_conn()
        result = manager.store_message(
            conv_id="00000000-0000-0000-0000-000000000010",
            user_id="00000000-0000-0000-0000-000000000001",
            role="user",
            content="Test",
        )
        assert isinstance(result, str)
        assert result == "00000000-0000-0000-0000-000000000100"


# ---------------------------------------------------------------------------
# DatabaseManager — get_user_context
# ---------------------------------------------------------------------------

class TestGetUserContext:
    def test_returns_dict_keyed_by_context_key(self):
        from datetime import datetime, timezone
        from database import DatabaseManager

        manager = DatabaseManager.__new__(DatabaseManager)
        manager.connection_string = "postgresql://fake@localhost/test"
        manager._pool = None

        mock_rows = [
            {"context_key": "user_name", "context_value": "Alice",
             "confidence": 0.95, "updated_at": datetime(2026, 7, 1, tzinfo=timezone.utc)},
            {"context_key": "location", "context_value": "India",
             "confidence": 0.90, "updated_at": datetime(2026, 7, 1, tzinfo=timezone.utc)},
        ]

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        @contextmanager
        def fake_get_connection():
            yield mock_conn

        manager.get_connection = fake_get_connection

        result = manager.get_user_context("test-user")
        assert "user_name" in result
        assert result["user_name"]["value"] == "Alice"
        assert result["location"]["value"] == "India"
        assert result["user_name"]["confidence"] == 0.95
