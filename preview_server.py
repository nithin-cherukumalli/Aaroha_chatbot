from __future__ import annotations

import datetime
import os
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="AI Engineering Assistant - Frontend Preview")

# Mount actual static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Mock In-Memory State for realistic UI exploration
mock_documents = [
    {
        "id": "doc-01",
        "filename": "rag_architecture_guide.pdf",
        "type": "pdf",
        "status": "READY",
        "added_at": (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat(),
    },
    {
        "id": "doc-02",
        "filename": "chunking_strategies_handbook.docx",
        "type": "docx",
        "status": "AWAITING_APPROVAL",
        "added_at": (datetime.datetime.now() - datetime.timedelta(hours=5)).isoformat(),
    },
    {
        "id": "doc-03",
        "filename": "eval_framework_best_practices.txt",
        "type": "txt",
        "status": "READY",
        "added_at": (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat(),
    },
    {
        "id": "doc-04",
        "filename": "scanned_legacy_notes.pdf",
        "type": "pdf",
        "status": "OCR_REQUIRED",
        "added_at": (datetime.datetime.now() - datetime.timedelta(hours=2)).isoformat(),
    },
]

mock_questions = [
    {
        "id": "q-01",
        "question": "What is the recommended overlap percentage for recursive token chunking?",
        "state": "open",
        "created_at": (datetime.datetime.now() - datetime.timedelta(hours=3)).isoformat(),
    },
    {
        "id": "q-02",
        "question": "How do we handle multi-hop retrieval with private vector collections?",
        "state": "resolved",
        "created_at": (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat(),
    },
]

@app.get("/", include_in_schema=False)
async def home():
    return FileResponse("app/static/index.html")

@app.get("/api/v1/identity")
async def get_identity():
    return {
        "data": {
            "email": "curator@example.com",
            "role": "curator"
        }
    }

@app.post("/api/v1/chat")
async def chat(request: Request):
    body = await request.json()
    q = body.get("question", "")
    
    groq_api_key = os.environ.get("LLM_API_KEY")
    if not groq_api_key and Path(".env").exists():
        for line in Path(".env").read_text().splitlines():
            if line.startswith("LLM_API_KEY="):
                groq_api_key = line.split("=", 1)[1].strip()
                break
    answer = None
    filename = "rag_architecture_guide.pdf"
    page = 1

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "openai/gpt-oss-120b",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are an AI Engineering Knowledge Assistant. Answer the question accurately, "
                                "concisely, and with a focus on production AI engineering, retrieval, embeddings, "
                                "and evaluation best practices."
                            ),
                        },
                        {"role": "user", "content": q},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 500,
                },
            )
            if res.status_code == 200:
                answer = res.json()["choices"][0]["message"]["content"]
    except Exception:
        pass

    if not answer:
        if "chunk" in q.lower():
            answer = "For typical retrieval tasks, chunk sizes of 150-300 tokens with 20-40 token overlap balance semantic coherence with embedding precision. Small chunks preserve focused context, while larger chunks prevent sentence fragmentation."
            filename = "chunking_strategies_handbook.docx"
            page = 2
        elif "grounded" in q.lower():
            answer = "An answer is grounded when every claim is strictly derived from retrieved, approved source excerpts rather than generative hallucinations. If insufficient context exists, the model must decline rather than speculate."
            filename = "rag_architecture_guide.pdf"
            page = 4
        elif "embedding" in q.lower():
            answer = "Embeddings convert textual chunks into dense vector representations. During query time, the query vector is compared against document vectors using cosine similarity in Qdrant to find the top-k most semantically relevant passages."
            filename = "eval_framework_best_practices.txt"
            page = 1
        else:
            answer = f"Based on the approved knowledge base: The retrieval pipeline matches approved documents to your query '{q}' and synthesizes an answer strictly grounded in the indexed materials."

    return {
        "data": {
            "answer": answer,
            "mode": "answer_from_documents",
            "citations": [
                {
                    "label": "[1]",
                    "filename": filename,
                    "page": page,
                    "section": "Core Architecture",
                    "excerpt": "Grounded AI engineering requires strict retrieval gating, verifiable source citations, and deterministic boundary evaluation across all ingested documents."
                }
            ]
        }
    }

@app.get("/api/v1/documents")
async def list_documents():
    return {"data": mock_documents}

@app.post("/api/v1/documents")
async def upload_documents(file: UploadFile = File(...), content_mode: str = Form("general_document")):
    new_doc = {
        "id": f"doc-{len(mock_documents) + 1:02d}",
        "filename": file.filename,
        "type": file.filename.split(".")[-1].lower() if "." in file.filename else "txt",
        "status": "AWAITING_APPROVAL",
        "added_at": datetime.datetime.now().isoformat(),
    }
    mock_documents.insert(0, new_doc)
    return {"data": new_doc}

@app.post("/api/v1/documents/{doc_id}/approve")
async def approve_document(doc_id: str):
    for doc in mock_documents:
        if doc["id"] == doc_id:
            doc["status"] = "READY"
            return {"data": doc}
    return JSONResponse(status_code=404, content={"error": {"user_message": "Document not found"}})

@app.post("/api/v1/documents/{doc_id}/retry")
async def retry_document(doc_id: str):
    for doc in mock_documents:
        if doc["id"] == doc_id:
            doc["status"] = "AWAITING_APPROVAL"
            return {"data": doc}
    return JSONResponse(status_code=404, content={"error": {"user_message": "Document not found"}})

@app.patch("/api/v1/documents/{doc_id}")
async def patch_document(doc_id: str, request: Request):
    body = await request.json()
    action = body.get("action")
    for doc in mock_documents:
        if doc["id"] == doc_id:
            if action == "delete":
                doc["status"] = "DELETED"
            elif action == "deactivate":
                doc["status"] = "INACTIVE"
            elif action == "reactivate":
                doc["status"] = "READY"
            return {"data": doc}
    return JSONResponse(status_code=404, content={"error": {"user_message": "Document not found"}})

@app.get("/api/v1/pending-questions")
async def list_questions():
    return {"data": mock_questions}

@app.patch("/api/v1/pending-questions/{q_id}")
async def resolve_question(q_id: str, request: Request):
    body = await request.json()
    for q in mock_questions:
        if q["id"] == q_id:
            q["state"] = body.get("state", "resolved")
            return {"data": q}
    return JSONResponse(status_code=404, content={"error": {"user_message": "Question not found"}})

@app.post("/api/v1/auth/session")
async def auth_session(request: Request):
    return {"data": {"status": "authenticated"}}

if __name__ == "__main__":
    uvicorn.run("preview_server:app", host="127.0.0.1", port=8000, reload=True)
