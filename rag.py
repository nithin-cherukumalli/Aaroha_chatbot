"""
RAG core: extract → chunk → embed → index → search → answer.
Swap embed() or answer() internals to use paid APIs without touching main.py.
"""
from __future__ import annotations

import io
import os
import uuid
from pathlib import Path

import httpx
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
COLLECTION = os.getenv("COLLECTION_NAME", "aaroha_rag")

# sentence-transformers/all-MiniLM-L6-v2 → 384 dims
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBED_DIM = int(os.getenv("EMBED_DIM", "384"))

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_API_KEY = os.environ["LLM_API_KEY"]
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "700"))

CHUNK_WORDS = int(os.getenv("CHUNK_WORDS", "200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP_WORDS", "30"))
TOP_K = int(os.getenv("RETRIEVAL_CONTEXT_K", "5"))

# ---------------------------------------------------------------------------
# Singletons (loaded once at startup via init())
# ---------------------------------------------------------------------------
_embedder: TextEmbedding | None = None
_qdrant: QdrantClient | None = None


def init() -> None:
    global _embedder, _qdrant
    _embedder = TextEmbedding(EMBED_MODEL)
    _qdrant = QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY or None,
        timeout=20,
    )
    if not _qdrant.collection_exists(COLLECTION):
        _qdrant.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
    # Payload index on filename is required for filtered deletes and scrolls.
    # create_payload_index is idempotent — safe to call on every startup.
    _qdrant.create_payload_index(
        COLLECTION,
        field_name="filename",
        field_schema="keyword",
    )


# ---------------------------------------------------------------------------
# Embedding
# To switch to OpenAI embeddings later, replace just this function.
# ---------------------------------------------------------------------------
def _embed(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _embedder.embed(texts)]


# ---------------------------------------------------------------------------
# Document extraction
# ---------------------------------------------------------------------------
def extract_text(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".txt":
        return data.decode("utf-8", errors="ignore")
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if ext == ".docx":
        from docx import Document
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError(f"Unsupported file type '{ext}'. Use PDF, TXT, or DOCX.")


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
def _chunk(text: str) -> list[str]:
    words = text.split()
    step = max(1, CHUNK_WORDS - CHUNK_OVERLAP)
    return [
        " ".join(words[i : i + CHUNK_WORDS])
        for i in range(0, len(words), step)
        if words[i : i + CHUNK_WORDS]
    ]


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------
def ingest(filename: str, data: bytes) -> int:
    text = extract_text(filename, data)
    chunks = _chunk(text)
    if not chunks:
        return 0
    vectors = _embed(chunks)
    points = [
        PointStruct(
            # Deterministic ID → re-uploading same file overwrites cleanly
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{filename}:{i}")),
            vector=vec,
            payload={"filename": filename, "text": chunk_text, "chunk_index": i},
        )
        for i, (chunk_text, vec) in enumerate(zip(chunks, vectors))
    ]
    _qdrant.upsert(COLLECTION, points=points, wait=True)
    return len(chunks)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def search(question: str) -> list[dict]:
    vec = _embed([question])[0]
    result = _qdrant.query_points(
        collection_name=COLLECTION,
        query=vec,
        limit=TOP_K,
        with_payload=True,
    )
    return [
        {
            "text": h.payload["text"],
            "filename": h.payload["filename"],
            "score": round(h.score, 3),
        }
        for h in result.points
    ]


# ---------------------------------------------------------------------------
# LLM answer
# To switch to a different LLM, replace just this function.
# ---------------------------------------------------------------------------
async def answer(question: str) -> dict:
    hits = search(question)
    if not hits:
        return {
            "answer": "No relevant documents found. Please upload some documents first.",
            "sources": [],
        }

    context = "\n\n".join(
        f"[{i+1}] (from {h['filename']}):\n{h['text']}"
        for i, h in enumerate(hits)
    )
    system_prompt = (
        "You are a helpful assistant. Answer the user's question using only the "
        "provided source excerpts. Cite each claim as [1], [2], etc. "
        "Write in clear, plain prose. Do not use markdown, asterisks, bullet points, "
        "or any special formatting — just plain sentences and paragraphs. "
        "If the sources don't contain the answer, say so clearly.\n\n"
        f"Sources:\n{context}"
    )

    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                "temperature": LLM_TEMPERATURE,
                "max_tokens": LLM_MAX_TOKENS,
            },
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"LLM API error {resp.status_code}: {resp.text[:400]}"
        )
    text = resp.json()["choices"][0]["message"]["content"]
    sources = sorted({h["filename"] for h in hits})
    return {"answer": text, "sources": sources}


# ---------------------------------------------------------------------------
# Document management
# ---------------------------------------------------------------------------
def list_documents() -> list[dict]:
    counts: dict[str, int] = {}
    offset = None
    while True:
        points, offset = _qdrant.scroll(
            COLLECTION, limit=256, offset=offset, with_payload=["filename"]
        )
        for p in points:
            fname = p.payload.get("filename", "unknown")
            counts[fname] = counts.get(fname, 0) + 1
        if offset is None:
            break
    return [{"filename": k, "chunks": v} for k, v in sorted(counts.items())]


def delete_document(filename: str) -> None:
    _qdrant.delete(
        COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="filename", match=MatchValue(value=filename))]
        ),
    )
