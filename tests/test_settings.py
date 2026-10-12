from __future__ import annotations

import pytest

from app.settings import Settings


def test_production_rejects_missing_infrastructure():
    with pytest.raises(ValueError, match="production requires"):
        Settings(app_env="production", database_url="postgresql+psycopg://u:p@db/app")


def test_overlap_cannot_exceed_chunk_size():
    with pytest.raises(ValueError, match="CHUNK_OVERLAP"):
        Settings(
            database_url="postgresql+psycopg://u:p@db/app",
            chunk_target_tokens=100,
            chunk_overlap_tokens=100,
        )


def test_openai_embedding_requires_its_own_credentials():
    with pytest.raises(ValueError, match="openai-compatible embeddings"):
        Settings(
            database_url="postgresql+psycopg://u:p@db/app", embedding_provider="openai_compatible"
        )
