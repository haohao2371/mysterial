"""Application-wide configuration loaded from environment variables / .env file."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings class – all values can be overridden via environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Neo4j ──────────────────────────────────────────────────────────
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="password")

    # ── Qdrant ─────────────────────────────────────────────────────────
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)
    qdrant_collection: str = Field(default="mysterial")

    # ── Embedding model ────────────────────────────────────────────────
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    embedding_dim: int = Field(default=384)

    # ── LLM (optional, for mapping validation) ─────────────────────────
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")

    # ── API server ─────────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    debug: bool = Field(default=False)

    # ── Ingestion ──────────────────────────────────────────────────────
    workspace_dir: str = Field(default="/tmp/mysterial/repos")
    max_file_size_bytes: int = Field(default=1_000_000)
    supported_languages: list[str] = Field(default=["python", "javascript", "typescript"])


settings = Settings()
