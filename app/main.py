from __future__ import annotations

import logging
import uuid
from asyncio import Event, create_task
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.providers import ProviderError
from app.api.routes import router
from app.composition import Container
from app.services.core import AppError
from app.settings import get_settings
from app.worker import worker_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = Container(get_settings())
    app.state.container = container
    # The profile row is durable; this never resets a collection or reindexes at startup.
    await container.knowledge.ensure_active_profile()
    stop = Event()
    task = (
        create_task(worker_loop(container, stop))
        if container.settings.ingestion_runner == "embedded"
        else None
    )
    try:
        yield
    finally:
        stop.set()
        if task:
            task.cancel()
            with suppress(Exception):
                await task


app = FastAPI(title="AI Engineering Knowledge Assistant", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(router)


def error_response(code: str, message: str, status: int, retryable: bool = False) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "user_message": message,
                "retryable": retryable,
                "request_id": str(uuid.uuid4()),
            }
        },
    )


@app.exception_handler(AppError)
async def app_error(_: Request, exc: AppError):
    return error_response(exc.code, exc.user_message, exc.status_code, exc.retryable)


@app.exception_handler(ProviderError)
async def provider_error(_: Request, exc: ProviderError):
    return error_response(exc.code, exc.user_message, 503, exc.retryable)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, __: RequestValidationError):
    return error_response("validation_error", "Check the submitted information and try again.", 422)


@app.exception_handler(Exception)
async def unhandled_error(_: Request, exc: Exception):
    logging.getLogger(__name__).exception("Unhandled application error", exc_info=exc)
    return error_response(
        "internal_error", "The requested action could not be completed.", 500, True
    )


@app.get("/health/live")
async def liveness():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def home():
    from fastapi.responses import FileResponse

    return FileResponse("app/static/index.html")
