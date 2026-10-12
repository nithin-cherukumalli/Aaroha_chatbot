from __future__ import annotations

from app.adapters.providers import (
    OpenAICompatibleEmbeddingStrategy,
    OpenAICompatibleLLMProvider,
    QdrantCloudEmbeddingStrategy,
    QdrantRetrievalIndex,
    SupabaseDocumentStorage,
    SupabaseIdentityProvider,
)
from app.database import make_session_factory
from app.services.core import KnowledgeService
from app.settings import Settings


class Container:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sessions = make_session_factory(settings)
        self.storage = SupabaseDocumentStorage(settings)
        self.embeddings = (
            QdrantCloudEmbeddingStrategy(settings)
            if settings.embedding_provider == "qdrant_cloud"
            else OpenAICompatibleEmbeddingStrategy(settings)
        )
        self.index = QdrantRetrievalIndex(settings)
        self.llm = OpenAICompatibleLLMProvider(settings)
        self.identity = SupabaseIdentityProvider(settings)
        self.knowledge = KnowledgeService(
            settings, self.sessions, self.storage, self.embeddings, self.index, self.llm
        )
