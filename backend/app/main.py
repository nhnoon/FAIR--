"""FastAPI entry point.

Dev:   uvicorn app.main:app --reload                       (from backend/)
Prod:  uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers
"""

from __future__ import annotations

import logging
import time

from fastapi import Depends, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .analyzer import analyze
from .config import Settings, get_settings, load_env_file
from .meta_client import MetaClient, ModelError
from .ratelimit import RateLimiter
from .schemas import AnalyzeRequest, AnalyzeResponse, ErrorResponse, HealthResponse

load_env_file()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("fair.api")

_startup = get_settings()
app = FastAPI(
    title="FAIR (تَبَيَّن) API",
    version="0.1.0",
    docs_url="/docs" if _startup.api_docs_enabled else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _startup.api_docs_enabled else None,
)
_limiter = RateLimiter(_startup.rate_limit_per_minute, _startup.daily_analysis_limit)


def _error(status: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body)


@app.middleware("http")
async def _limit_body_size(request: Request, call_next):
    # Reject oversized bodies before they are read into memory.
    length = request.headers.get("content-length")
    if length is not None:
        try:
            too_big = int(length) > _startup.max_body_bytes
        except ValueError:
            return _error(400, "invalid_request", "Invalid Content-Length header.")
        if too_big:
            return _error(413, "payload_too_large", "The request body is too large.")
    return await call_next(request)


# Added last = outermost, so every response (including 413/429/500) carries CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_startup.cors_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    max_age=600,
)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"], "type": e["type"]}
        for e in exc.errors()
    ]
    return _error(422, "invalid_request", "The request body is invalid.", details)


@app.exception_handler(ModelError)
async def _model_error(_: Request, exc: ModelError) -> JSONResponse:
    return _error(exc.http_status, exc.code, exc.message)


@app.exception_handler(Exception)
async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error: %s", type(exc).__name__)
    return _error(500, "internal_error", "An unexpected server error occurred.")


def get_meta_client(settings: Settings = Depends(get_settings)) -> MetaClient:
    return MetaClient(settings)


def get_rate_limiter() -> RateLimiter:
    return _limiter


def _client_key(request: Request) -> str:
    # With --proxy-headers behind a trusted proxy, request.client is the real client IP.
    return request.client.host if request.client else "unknown"


@app.get("/api/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        model=settings.model,
        base_url=settings.base_url,
        model_configured=settings.api_key_present,
        live_calls_enabled=settings.live_calls_enabled,
    )


@app.post(
    "/api/analyze",
    response_model=AnalyzeResponse,
    responses={
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def analyze_offer(
    body: AnalyzeRequest,
    request: Request,
    client: MetaClient = Depends(get_meta_client),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    client.check_ready()  # config errors first: they cost nothing and are not rate limited
    limiter.check(_client_key(request))
    started = time.perf_counter()
    try:
        result = await run_in_threadpool(analyze, body, client)
    except ModelError as exc:
        log.info("analyze failed code=%s ms=%d", exc.code, (time.perf_counter() - started) * 1000)
        raise
    except Exception as exc:  # handled here so the response still passes through CORS
        log.exception("analyze crashed: %s", type(exc).__name__)
        return _error(500, "internal_error", "An unexpected server error occurred.")
    # Metadata only: user text and model output are never logged.
    log.info(
        "analyze ok verdict=%s downgraded=%s rejected=%d ms=%d",
        result.verdict,
        result.verdict_downgraded,
        len(result.rejected_facts),
        (time.perf_counter() - started) * 1000,
    )
    return result
