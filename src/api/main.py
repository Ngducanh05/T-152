import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.memory import InMemorySaver
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from src.agents.graph import build_graph
from src.api.routes import api_router
from src.core.config import Settings, get_settings
from src.core.logging import configure_logging

REQUEST_ID_HEADER = "X-Request-ID"
logger = logging.getLogger(__name__)


def _resolve_request_id(header_value: str | None) -> str:
    if header_value:
        candidate = header_value.strip()
        try:
            UUID(candidate)
        except (ValueError, AttributeError):
            pass
        else:
            return candidate
    return str(uuid4())


def _get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    return request_id or str(uuid4())


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "request_id": _get_request_id(request),
            },
        },
    )


def create_app(
    settings: Settings | None = None,
    *,
    agent_override: Any | None = None,
) -> FastAPI:
    application_settings = settings or get_settings()
    configure_logging(application_settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        checkpointer = InMemorySaver() if application_settings.agent_enabled else None
        application.state.agent_checkpointer = checkpointer
        application.state.agent = None
        if application_settings.agent_enabled:
            application.state.agent = (
                agent_override
                if agent_override is not None
                else build_graph(checkpointer=checkpointer)
            )
        application.state.agent_thread_owners = {}
        application.state.agent_thread_locks = {}
        application.state.agent_thread_last_access = {}
        application.state.agent_thread_deletions = {}
        application.state.agent_thread_cleanup_tasks = set()
        application.state.agent_thread_registry_lock = asyncio.Lock()
        application.state.agent_thread_ttl_seconds = (
            application_settings.agent_thread_ttl_seconds
        )
        application.state.agent_chat_timeout_seconds = (
            application_settings.llm_timeout_seconds
        )
        try:
            yield
        finally:
            cleanup_tasks = list(application.state.agent_thread_cleanup_tasks)
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)

    application = FastAPI(
        title=application_settings.app_name,
        version=application_settings.app_version,
        debug=application_settings.debug,
        lifespan=lifespan,
    )
    application.state.settings = application_settings

    application.add_middleware(
        CORSMiddleware,
        allow_origins=application_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def request_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = _resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        started_at = perf_counter()

        try:
            response = await call_next(request)
        except Exception as error:  # noqa: BLE001 - HTTP boundary returns safe envelope
            logger.error(
                "request_failed request_id=%s method=%s path=%s exception_type=%s",
                request_id,
                request.method,
                request.url.path,
                type(error).__name__,
            )
            response = _error_response(
                request,
                status_code=500,
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected server error occurred.",
            )

        duration_ms = (perf_counter() - started_at) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_completed request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        code = f"HTTP_{exc.status_code}"
        message = str(exc.detail)
        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("code", code))
            message = str(exc.detail.get("message", "Request failed."))
        return _error_response(
            request,
            status_code=exc.status_code,
            code=code,
            message=message,
            headers=exc.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request validation failed.",
        )

    application.include_router(
        api_router,
        prefix="/api/v1",
    )

    @application.get("/health", tags=["Health"])
    async def application_health(request: Request) -> dict[str, str]:
        return {
            "status": "ok",
            "service": application_settings.app_name,
            "version": application_settings.app_version,
            "environment": application_settings.environment,
            "request_id": _get_request_id(request),
        }

    return application


app = create_app()
