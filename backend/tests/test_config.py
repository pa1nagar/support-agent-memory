"""
Tests for config.py — Settings validation.
"""

import pytest
from unittest.mock import patch
import os


class TestSettings:
    def test_valid_config_loads(self):
        with patch.dict(os.environ, {
            "COCKROACHDB_URL": "postgresql://user:pass@host:26257/db",
            "AWS_REGION": "us-east-1",
        }):
            from config import Settings
            s = Settings()
            assert s.COCKROACHDB_URL == "postgresql://user:pass@host:26257/db"

    def test_database_url_fallback(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://user:pass@host:26257/db",
        }, clear=False):
            # Remove COCKROACHDB_URL if set
            env = {k: v for k, v in os.environ.items() if k != "COCKROACHDB_URL"}
            env["DATABASE_URL"] = "postgresql://user:pass@host:26257/db"
            with patch.dict(os.environ, env, clear=True):
                from config import Settings
                s = Settings()
                assert s.COCKROACHDB_URL == "postgresql://user:pass@host:26257/db"

    def test_missing_db_url_raises(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("COCKROACHDB_URL", "DATABASE_URL")}
        with patch.dict(os.environ, env, clear=True):
            from config import Settings
            with pytest.raises(Exception):
                Settings()

    def test_similarity_threshold_must_be_0_to_1(self):
        with patch.dict(os.environ, {
            "COCKROACHDB_URL": "postgresql://user:pass@host:26257/db",
            "MEMORY_SIMILARITY_THRESHOLD": "1.5",
        }):
            from config import Settings
            with pytest.raises(Exception):
                Settings()

    def test_similarity_threshold_boundary_values(self):
        for value in ["0.0", "1.0", "0.7"]:
            with patch.dict(os.environ, {
                "COCKROACHDB_URL": "postgresql://user:pass@host:26257/db",
                "MEMORY_SIMILARITY_THRESHOLD": value,
            }):
                from config import Settings
                s = Settings()
                assert 0.0 <= s.MEMORY_SIMILARITY_THRESHOLD <= 1.0

    def test_default_values(self):
        with patch.dict(os.environ, {
            "COCKROACHDB_URL": "postgresql://user:pass@host:26257/db",
        }):
            from config import Settings
            s = Settings()
            assert s.MEMORY_RETRIEVAL_LIMIT == 5
            assert s.MEMORY_SIMILARITY_THRESHOLD == 0.7
            assert s.AWS_REGION == "us-east-1"
            assert s.LOG_LEVEL == "INFO"

    def test_cors_origins_list_parsing(self):
        with patch.dict(os.environ, {
            "COCKROACHDB_URL": "postgresql://user:pass@host:26257/db",
            "CORS_ORIGINS": "https://app.example.com,https://admin.example.com",
        }):
            from config import Settings
            s = Settings()
            origins = s.get_cors_origins_list()
            assert len(origins) == 2
            assert "https://app.example.com" in origins

    def test_cors_origins_single_wildcard(self):
        with patch.dict(os.environ, {
            "COCKROACHDB_URL": "postgresql://user:pass@host:26257/db",
            "CORS_ORIGINS": "*",
        }):
            from config import Settings
            s = Settings()
            assert s.get_cors_origins_list() == ["*"]
