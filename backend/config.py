"""
Configuration management for Support Agent Memory
Loads settings from environment variables and AWS Secrets Manager
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application
    APP_NAME: str = "support-agent-memory"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # CockroachDB Connection
    COCKROACHDB_URL: str = Field(..., env="COCKROACHDB_URL")
    # Also support DATABASE_URL for compatibility
    DATABASE_URL: Optional[str] = Field(default=None, env="DATABASE_URL")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Use DATABASE_URL if COCKROACHDB_URL not set
        if not self.COCKROACHDB_URL and self.DATABASE_URL:
            self.COCKROACHDB_URL = self.DATABASE_URL
    
    DB_POOL_SIZE: int = Field(default=5, env="DB_POOL_SIZE")
    DB_MAX_OVERFLOW: int = Field(default=10, env="DB_MAX_OVERFLOW")
    
    # AWS Bedrock
    AWS_REGION: str = Field(default="us-east-1", env="AWS_REGION")
    BEDROCK_MODEL_ID: str = Field(
        default="amazon.titan-text-premier-v1:0",  # Amazon Titan Text Premier (immediately available)
        env="BEDROCK_MODEL_ID"
    )
    BEDROCK_EMBEDDING_MODEL_ID: str = Field(
        default="amazon.titan-embed-text-v2:0",
        env="BEDROCK_EMBEDDING_MODEL_ID"
    )
    
    # Memory Retrieval Settings
    MEMORY_RETRIEVAL_LIMIT: int = Field(default=5, env="MEMORY_RETRIEVAL_LIMIT")
    MEMORY_SIMILARITY_THRESHOLD: float = Field(
        default=0.7,
        env="MEMORY_SIMILARITY_THRESHOLD"
    )  # 0.0 to 1.0
    
    # API Settings
    CORS_ORIGINS: str = Field(default="*", env="CORS_ORIGINS")
    MAX_REQUEST_SIZE: int = Field(default=1048576, env="MAX_REQUEST_SIZE")  # 1MB
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Secrets (loaded from AWS Secrets Manager in production)
    COCKROACHDB_PASSWORD: Optional[str] = Field(default=None, env="COCKROACHDB_PASSWORD")
    
    def get_cors_origins_list(self):
        """Parse comma-separated CORS origins"""
        if isinstance(self.CORS_ORIGINS, str):
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        return [self.CORS_ORIGINS]
    
    @validator("MEMORY_SIMILARITY_THRESHOLD")
    def validate_similarity_threshold(cls, v):
        """Ensure similarity threshold is between 0 and 1"""
        if not 0 <= v <= 1:
            raise ValueError("MEMORY_SIMILARITY_THRESHOLD must be between 0 and 1")
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Quick access
settings = get_settings()
