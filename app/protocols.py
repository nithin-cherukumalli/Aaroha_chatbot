from __future__ import annotations

from typing import Protocol

from app.domain import (
    EmbeddingProfile,
    GenerationRequest,
    GenerationResult,
    HealthResult,
    IndexPoint,
    IndexProfile,
    SearchFilters,
    SearchHit,
    VectorInput,
)


class DocumentStorage(Protocol):
    async def put(self, object_key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, object_key: str) -> bytes: ...
    async def delete(self, object_key: str) -> None: ...


class EmbeddingStrategy(Protocol):
    def profile(self) -> EmbeddingProfile: ...
    async def prepare_documents(self, texts: list[str]) -> list[VectorInput]: ...
    async def prepare_query(self, text: str) -> VectorInput: ...


class RetrievalIndex(Protocol):
    async def ensure_index(self, profile: IndexProfile) -> None: ...
    async def upsert(self, index_name: str, points: list[IndexPoint]) -> None: ...
    async def search(
        self, index_name: str, query: VectorInput, limit: int, filters: SearchFilters
    ) -> list[SearchHit]: ...
    async def delete_document(self, index_name: str, document_id: str) -> None: ...
    async def health(self) -> HealthResult: ...


class LLMProvider(Protocol):
    async def generate(self, request: GenerationRequest) -> GenerationResult: ...


class IdentityProvider(Protocol):
    async def verify_access_token(self, token: str) -> tuple[str, str | None]: ...
