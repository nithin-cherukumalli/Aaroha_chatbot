from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID


class Role(StrEnum):
    STUDENT = "student"
    CURATOR = "curator"


class DocumentState(StrEnum):
    UPLOADING = "UPLOADING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    READY = "READY"
    FAILED = "FAILED"
    OCR_REQUIRED = "OCR_REQUIRED"
    INACTIVE = "INACTIVE"
    DELETING = "DELETING"
    DELETED = "DELETED"


class ContentMode(StrEnum):
    GENERAL_DOCUMENT = "general_document"
    CURATED_QA = "curated_qa"
    QUESTIONS_ONLY = "questions_only"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class DenseVector:
    values: list[float]
    profile_fingerprint: str


@dataclass(frozen=True)
class InferenceText:
    text: str
    profile_fingerprint: str


VectorInput = DenseVector | InferenceText


@dataclass(frozen=True)
class EmbeddingProfile:
    provider: str
    model: str
    dimensions: int
    fingerprint: str
    tokenizer_model: str
    max_input_tokens: int = 256


@dataclass(frozen=True)
class IndexProfile:
    id: UUID
    collection_name: str
    fingerprint: str
    dimensions: int
    distance: str = "cosine"


@dataclass(frozen=True)
class IndexPoint:
    id: str
    vector: VectorInput
    payload: dict


@dataclass(frozen=True)
class SearchFilters:
    profile_id: str
    document_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchHit:
    passage_id: str
    document_id: str
    score: float
    payload: dict


@dataclass(frozen=True)
class HealthResult:
    name: str
    ok: bool
    detail: str | None = None


@dataclass(frozen=True)
class GenerationRequest:
    messages: list[dict[str, str]]
    temperature: float
    max_output_tokens: int


@dataclass(frozen=True)
class GenerationResult:
    text: str
    model: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class SourceLocation:
    page: int | None = None
    section: str | None = None
    line_start: int | None = None
    line_end: int | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    warnings: list[str]
    locations: list[tuple[int, int, SourceLocation]]
