from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # must be before importing rag so env vars are available

import rag  # noqa: E402

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


@asynccontextmanager
async def lifespan(app: FastAPI):
    rag.init()  # loads embedding model + ensures Qdrant collection exists
    yield


app = FastAPI(title="Aaroha RAG", lifespan=lifespan)


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse("static/index.html")


@app.get("/manage", include_in_schema=False)
async def manage():
    return FileResponse("static/manage.html")


# Mount static AFTER routes so FastAPI route matching takes priority
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    try:
        chunks = rag.ingest(file.filename or "upload", data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"filename": file.filename, "chunks": chunks}


@app.get("/documents")
def documents():
    return {"documents": rag.list_documents()}


@app.delete("/documents/{filename:path}")
def delete(filename: str):
    rag.delete_document(filename)
    return {"deleted": filename}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    question: str


@app.post("/chat")
async def chat(req: ChatRequest):
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty.")
    try:
        return await rag.answer(req.question.strip())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
