"""
Configuration management for Support Agent Memory
"""

from typing import Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "support-agent-memory"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=False)

    # CockroachDB — COCKROACHDB_URL required; DATABASE_URL accepted as alias
    COCKROACHDB_URL: Optional[str] = Field(default=None)
    DATABASE_URL: Optional[str] = Field(default=None)

    DB_POOL_SIZE: int = Field(default=5)
    DB_MAX_OVERFLOW: int = Field(default=10)

    # AWS Bedrock
    AWS_REGION: str = Field(default="us-east-1")
    BEDROCK_MODEL_ID: str = Field(default="us.anthropic.claude-sonnet-4-6")
    BEDROCK_EMBEDDING_MODEL_ID: str = Field(default="amazon.titan-embed-text-v2:0")

    # Memory
    MEMORY_RETRIEVAL_LIMIT: int = Field(default=5)
    MEMORY_SIMILARITY_THRESHOLD: float = Field(default=0.7)

    # API
    CORS_ORIGINS: str = Field(default="*")
    MAX_REQUEST_SIZE: int = Field(default=1048576)

    # Logging
    LOG_LEVEL: str = Field(default="INFO")

    @model_validator(mode="after")
    def resolve_db_url(self) -> "Settings":
        """Accept DATABASE_URL as a fallback for COCKROACHDB_URL."""
        if not self.COCKROACHDB_URL and self.DATABASE_URL:
            self.COCKROACHDB_URL = self.DATABASE_URL
        if not self.COCKROACHDB_URL:
            raise ValueError("COCKROACHDB_URL (or DATABASE_URL) must be set")
        return self

    @field_validator("MEMORY_SIMILARITY_THRESHOLD")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("MEMORY_SIMILARITY_THRESHOLD must be between 0 and 1")
        return v

    def get_cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    model_config = {"env_file": ".env", "case_sensitive": True}


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


settings = get_settings()
