from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    public_base_url: str = "http://localhost:8000"
    ingestion_runner: Literal["embedded", "separate", "disabled"] = "embedded"
    temp_dir: Path = Path("/tmp/ai-engineering")
    session_secret: SecretStr = SecretStr("development-only-change-me-please-32chars")
    database_url: str
    db_pool_size: int = Field(default=3, ge=1, le=20)
    db_max_overflow: int = Field(default=2, ge=0, le=20)
    supabase_url: str | None = None
    supabase_publishable_key: SecretStr | None = None
    supabase_secret_key: SecretStr | None = None
    supabase_storage_bucket: str = "knowledge-documents"
    auth_provider: Literal["supabase"] = "supabase"
    allow_public_signup: bool = False
    save_chat_history: bool = False
    vector_db_provider: Literal["qdrant"] = "qdrant"
    qdrant_url: str | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_collection_prefix: str = "ai_engineering"
    qdrant_timeout_seconds: int = Field(default=20, ge=1, le=120)
    embedding_provider: Literal["qdrant_cloud", "openai_compatible"] = "qdrant_cloud"
    embedding_model: str = "sentence-transformers/all-minilm-l6-v2"
    embedding_model_revision: str = ""
    embedding_dimensions: int = Field(default=384, ge=1)
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    embedding_tokenizer_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = None
    llm_provider: Literal["openai_compatible"] = "openai_compatible"
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openrouter/free"
    llm_api_key: SecretStr | None = None
    llm_temperature: float = Field(default=0.1, ge=0, le=2)
    llm_max_output_tokens: int = Field(default=700, ge=64, le=8000)
    llm_max_input_tokens: int = Field(default=4096, ge=512)
    llm_timeout_seconds: int = Field(default=45, ge=1, le=120)
    llm_free_only: bool = True
    allow_free_router_in_production: bool = False
    chunk_target_tokens: int = Field(default=180, ge=20)
    chunk_overlap_tokens: int = Field(default=30, ge=0)
    retrieval_candidate_k: int = Field(default=20, ge=1, le=100)
    retrieval_context_k: int = Field(default=5, ge=1, le=10)
    retrieval_min_cosine_score: float = Field(default=0.35, ge=-1, le=1)
    max_context_characters: int = Field(default=6000, ge=100)
    max_query_characters: int = Field(default=2000, ge=20)
    max_upload_mb: int = Field(default=10, ge=1, le=100)
    max_pdf_pages: int = Field(default=200, ge=1)
    max_extracted_characters: int = Field(default=1_000_000, ge=1000)
    worker_concurrency: int = Field(default=1, ge=1, le=4)
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    job_lease_seconds: int = Field(default=120, ge=30, le=3600)
    provider_max_retries: int = Field(default=2, ge=0, le=5)
    chat_requests_per_user_per_minute: int = Field(default=10, ge=1, le=100)
    log_level: str = "INFO"

    @model_validator(mode="after")
    def validate_contract(self) -> Settings:
        if self.chunk_overlap_tokens >= self.chunk_target_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_TARGET_TOKENS")
        if self.chunk_target_tokens > 256:
            raise ValueError("chunk target exceeds default hosted MiniLM input limit")
        if self.app_env == "production":
            required = [self.database_url, self.supabase_url, self.qdrant_url]
            if not all(required) or not self.supabase_secret_key or not self.qdrant_api_key:
                raise ValueError(
                    "production requires database, Supabase storage and Qdrant settings"
                )
            if not self.llm_api_key or len(self.session_secret.get_secret_value()) < 32:
                raise ValueError(
                    "production requires LLM_API_KEY and a 32+ character SESSION_SECRET"
                )
            if self.ingestion_runner == "embedded":
                raise ValueError("production must use a separate worker")
            if self.llm_model == "openrouter/free" and not self.allow_free_router_in_production:
                raise ValueError(
                    "openrouter/free is blocked in production unless explicitly allowed"
                )
        if self.embedding_provider == "openai_compatible" and (
            not self.embedding_base_url or not self.embedding_api_key
        ):
            raise ValueError("openai-compatible embeddings require EMBEDDING_BASE_URL and API key")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
