from __future__ import annotations

import hashlib
from collections import defaultdict

import httpx

from app.domain import (
    DenseVector,
    EmbeddingProfile,
    GenerationRequest,
    GenerationResult,
    HealthResult,
    IndexPoint,
    IndexProfile,
    InferenceText,
    SearchFilters,
    SearchHit,
    VectorInput,
)
from app.protocols import (
    DocumentStorage,
    EmbeddingStrategy,
    IdentityProvider,
    LLMProvider,
    RetrievalIndex,
)
from app.settings import Settings


class ProviderError(RuntimeError):
    def __init__(self, code: str, user_message: str, retryable: bool = False):
        super().__init__(user_message)
        self.code, self.user_message, self.retryable = code, user_message, retryable


class SupabaseDocumentStorage(DocumentStorage):
    def __init__(self, settings: Settings):
        self._base = (settings.supabase_url or "").rstrip("/")
        self._bucket = settings.supabase_storage_bucket
        self._key = (
            settings.supabase_secret_key.get_secret_value() if settings.supabase_secret_key else ""
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "apikey": self._key}

    async def put(self, object_key: str, data: bytes, content_type: str) -> None:
        url = f"{self._base}/storage/v1/object/{self._bucket}/{object_key}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                headers={**self._headers, "Content-Type": content_type, "x-upsert": "false"},
                content=data,
            )
        if response.status_code >= 300:
            raise ProviderError(
                "storage_upload_failed",
                "Document storage is unavailable.",
                response.status_code >= 500,
            )

    async def get(self, object_key: str) -> bytes:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self._base}/storage/v1/object/{self._bucket}/{object_key}", headers=self._headers
            )
        if response.status_code != 200:
            raise ProviderError(
                "storage_download_failed",
                "Document storage is unavailable.",
                response.status_code >= 500,
            )
        return response.content

    async def delete(self, object_key: str) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.delete(
                f"{self._base}/storage/v1/object/{self._bucket}/{object_key}", headers=self._headers
            )
        if response.status_code >= 300:
            raise ProviderError(
                "storage_delete_failed",
                "Document storage cleanup failed.",
                response.status_code >= 500,
            )


class QdrantCloudEmbeddingStrategy(EmbeddingStrategy):
    def __init__(self, settings: Settings):
        fingerprint = hashlib.sha256(
            f"qdrant_cloud|{settings.embedding_model}|{settings.embedding_dimensions}|v1".encode()
        ).hexdigest()
        self._profile = EmbeddingProfile(
            "qdrant_cloud",
            settings.embedding_model,
            settings.embedding_dimensions,
            fingerprint,
            settings.embedding_tokenizer_model,
        )

    def profile(self) -> EmbeddingProfile:
        return self._profile

    async def prepare_documents(self, texts: list[str]) -> list[VectorInput]:
        return [InferenceText(text, self._profile.fingerprint) for text in texts]

    async def prepare_query(self, text: str) -> VectorInput:
        return InferenceText(text, self._profile.fingerprint)


class OpenAICompatibleEmbeddingStrategy(EmbeddingStrategy):
    def __init__(self, settings: Settings):
        self.settings = settings
        fingerprint = hashlib.sha256(
            f"openai|{settings.embedding_base_url}|{settings.embedding_model}|{settings.embedding_dimensions}|v1".encode()
        ).hexdigest()
        self._profile = EmbeddingProfile(
            "openai_compatible",
            settings.embedding_model,
            settings.embedding_dimensions,
            fingerprint,
            settings.embedding_tokenizer_model,
        )

    def profile(self) -> EmbeddingProfile:
        return self._profile

    async def _embed(self, texts: list[str]) -> list[VectorInput]:
        headers = {"Authorization": f"Bearer {self.settings.embedding_api_key.get_secret_value()}"}
        async with httpx.AsyncClient(timeout=self.settings.qdrant_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.embedding_base_url.rstrip('/')}/embeddings",
                headers=headers,
                json={"model": self.settings.embedding_model, "input": texts},
            )
        if response.status_code >= 300:
            raise ProviderError(
                "embedding_failed",
                "The embedding provider is unavailable.",
                response.status_code >= 500 or response.status_code == 429,
            )
        values = [
            DenseVector(row["embedding"], self._profile.fingerprint)
            for row in response.json()["data"]
        ]
        if any(len(vector.values) != self._profile.dimensions for vector in values):
            raise ProviderError(
                "embedding_incompatible", "Embedding dimensions do not match the active index."
            )
        return values

    async def prepare_documents(self, texts: list[str]) -> list[VectorInput]:
        return await self._embed(texts)

    async def prepare_query(self, text: str) -> VectorInput:
        return (await self._embed([text]))[0]


class QdrantRetrievalIndex(RetrievalIndex):
    def __init__(self, settings: Settings):
        from qdrant_client import AsyncQdrantClient

        self._models = __import__("qdrant_client.models", fromlist=["models"])
        self._client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
            timeout=settings.qdrant_timeout_seconds,
        )
        self._embedding_model = settings.embedding_model

    async def ensure_index(self, profile: IndexProfile) -> None:
        models = self._models
        exists = await self._client.collection_exists(profile.collection_name)
        if not exists:
            await self._client.create_collection(
                profile.collection_name,
                vectors_config=models.VectorParams(
                    size=profile.dimensions, distance=models.Distance.COSINE
                ),
            )
            for field in ("document_id", "index_profile_id", "passage_id"):
                await self._client.create_payload_index(
                    profile.collection_name,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )

    async def upsert(self, index_name: str, points: list[IndexPoint]) -> None:
        models = self._models
        converted = []
        for point in points:
            vector = point.vector
            if isinstance(vector, InferenceText):
                vector = models.Document(text=vector.text, model=point.payload["embedding_model"])
            else:
                vector = vector.values
            converted.append(models.PointStruct(id=point.id, vector=vector, payload=point.payload))
        await self._client.upsert(index_name, points=converted, wait=True)

    async def search(
        self, index_name: str, query: VectorInput, limit: int, filters: SearchFilters
    ) -> list[SearchHit]:
        models = self._models
        query_value = (
            models.Document(text=query.text, model=self._embedding_model)
            if isinstance(query, InferenceText)
            else query.values
        )
        result = await self._client.query_points(
            index_name,
            query=query_value,
            limit=limit,
            with_payload=True,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="index_profile_id", match=models.MatchValue(value=filters.profile_id)
                    )
                ]
            ),
        )
        return [
            SearchHit(
                str(point.payload["passage_id"]),
                str(point.payload["document_id"]),
                float(point.score),
                dict(point.payload),
            )
            for point in result.points
        ]

    async def delete_document(self, index_name: str, document_id: str) -> None:
        models = self._models
        await self._client.delete(
            index_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id", match=models.MatchValue(value=document_id)
                        )
                    ]
                )
            ),
        )

    async def health(self) -> HealthResult:
        try:
            await self._client.get_collections()
            return HealthResult("qdrant", True)
        except Exception:
            return HealthResult("qdrant", False, "unavailable")


class OpenAICompatibleLLMProvider(LLMProvider):
    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.llm_model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "llm_timeout", "The answer provider timed out. Please retry.", True
            ) from exc
        if response.status_code >= 300:
            raise ProviderError(
                "llm_unavailable",
                "The answer provider is temporarily unavailable.",
                response.status_code in {429, 500, 502, 503, 504},
            )
        body = response.json()
        return GenerationResult(
            body["choices"][0]["message"]["content"],
            body.get("model"),
            body.get("usage", {}).get("prompt_tokens"),
            body.get("usage", {}).get("completion_tokens"),
        )


class SupabaseIdentityProvider(IdentityProvider):
    def __init__(self, settings: Settings):
        self._base = (settings.supabase_url or "").rstrip("/")
        self._key = (
            settings.supabase_publishable_key.get_secret_value()
            if settings.supabase_publishable_key
            else ""
        )

    async def verify_access_token(self, token: str) -> tuple[str, str | None]:
        clean_token = token.strip()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self._base}/auth/v1/user",
                headers={"apikey": self._key, "Authorization": f"Bearer {clean_token}"},
            )
        if response.status_code != 200:
            raise ProviderError(
                "invalid_session", "Your session has expired. Please sign in again."
            )
        user = response.json()
        return str(user["id"]), user.get("email")


class InMemoryStorage(DocumentStorage):
    def __init__(self):
        self.items: dict[str, bytes] = {}

    async def put(self, object_key: str, data: bytes, content_type: str) -> None:
        self.items[object_key] = data

    async def get(self, object_key: str) -> bytes:
        return self.items[object_key]

    async def delete(self, object_key: str) -> None:
        self.items.pop(object_key, None)


class InMemoryIndex(RetrievalIndex):
    def __init__(self):
        self.points: dict[str, dict[str, IndexPoint]] = defaultdict(dict)

    async def ensure_index(self, profile: IndexProfile) -> None:
        self.points.setdefault(profile.collection_name, {})

    async def upsert(self, index_name: str, points: list[IndexPoint]) -> None:
        self.points[index_name].update({point.id: point for point in points})

    async def search(
        self, index_name: str, query: VectorInput, limit: int, filters: SearchFilters
    ) -> list[SearchHit]:
        text = query.text.lower() if isinstance(query, InferenceText) else ""
        scored = []
        for point in self.points[index_name].values():
            if point.payload.get("index_profile_id") != filters.profile_id:
                continue
            candidate = point.vector.text.lower() if isinstance(point.vector, InferenceText) else ""
            score = len(set(text.split()) & set(candidate.split())) / max(1, len(set(text.split())))
            scored.append(
                SearchHit(
                    point.payload["passage_id"], point.payload["document_id"], score, point.payload
                )
            )
        return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]

    async def delete_document(self, index_name: str, document_id: str) -> None:
        self.points[index_name] = {
            key: value
            for key, value in self.points[index_name].items()
            if value.payload.get("document_id") != document_id
        }

    async def health(self) -> HealthResult:
        return HealthResult("qdrant", True)
