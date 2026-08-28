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
from opentelemetry import trace
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from src.agents.graph import build_graph
from src.api.routes import api_router
from src.core.config import Settings, get_settings
from src.core.logging import bind_request_id, configure_logging, reset_request_id
from src.core.observability import (
    ObservabilityRuntime,
    bind_observability_runtime,
    configure_langsmith,
    reset_observability_runtime,
)
from src.core.reservation_expiry import run_reservation_expiry_worker
from src.services.auth_service import SupabaseTokenVerifier

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
    details: dict[str, object] | None = None,
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
                **({"details": details} if details is not None else {}),
            },
        },
    )


def create_app(
    settings: Settings | None = None,
    *,
    agent_override: Any | None = None,
) -> FastAPI:
    application_settings = settings or get_settings()
    configure_logging(
        application_settings.log_level,
        application_settings.log_format,
        service=application_settings.otel_service_name,
        environment=application_settings.environment,
        service_version=application_settings.service_version or application_settings.otel_service_version,
    )
    configure_langsmith(application_settings)
    observability = ObservabilityRuntime(application_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        checkpointer = InMemorySaver() if application_settings.agent_enabled else None
        application.state.auth_token_verifier = SupabaseTokenVerifier(application_settings)
        application.state.agent_checkpointer = checkpointer
        application.state.agent = None
        if application_settings.agent_enabled:
            application.state.agent = (
                agent_override
                if agent_override is not None
                else build_graph(
                    checkpointer=checkpointer,
                    max_steps=application_settings.agent_max_steps,
                )
            )
        application.state.agent_thread_owners = {}
        application.state.agent_thread_locks = {}
        application.state.agent_thread_last_access = {}
        application.state.agent_thread_deletions = {}
        application.state.agent_thread_cleanup_tasks = set()
        application.state.agent_thread_registry_lock = asyncio.Lock()
        application.state.agent_thread_ttl_seconds = application_settings.agent_thread_ttl_seconds
        application.state.agent_chat_timeout_seconds = application_settings.llm_timeout_seconds
        expiry_engine = create_async_engine(application_settings.database_url)
        application.state.observability.instrument_sqlalchemy_engine(expiry_engine.sync_engine)
        expiry_session_factory = async_sessionmaker(expiry_engine, expire_on_commit=False)
        expiry_stop_event = asyncio.Event()
        expiry_task = asyncio.create_task(
            run_reservation_expiry_worker(
                expiry_stop_event,
                settings=application_settings,
                session_factory=expiry_session_factory,
                observability=application.state.observability,
            )
        )
        try:
            yield
        finally:
            expiry_stop_event.set()
            await expiry_task
            await expiry_engine.dispose()
            await application.state.auth_token_verifier.aclose()
            cleanup_tasks = list(application.state.agent_thread_cleanup_tasks)
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            application.state.observability.shutdown()

    application = FastAPI(
        title=application_settings.app_name,
        version=application_settings.app_version,
        debug=application_settings.debug,
        lifespan=lifespan,
    )
    application.state.settings = application_settings
    application.state.observability = observability

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
        request_id_token = bind_request_id(request_id)
        observability_token = bind_observability_runtime(application.state.observability)
        try:
            with observability.start_http_server_span(
                method=request.method,
                path=request.url.path,
                headers=request.headers,
            ) as span:
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
                    if span is not None:
                        span.set_status(trace.Status(trace.StatusCode.ERROR))
                        span.set_attribute("error.type", type(error).__name__)
                    response = _error_response(
                        request,
                        status_code=500,
                        code="INTERNAL_SERVER_ERROR",
                        message="An unexpected server error occurred.",
                    )

                duration_ms = (perf_counter() - started_at) * 1000
                if span is not None:
                    span.set_attribute("http.response.status_code", response.status_code)
                    span.set_attribute("parksmart.request_id", request_id)
                response.headers[REQUEST_ID_HEADER] = request_id
                if trace_id := observability.trace_id_for_span(span):
                    response.headers["X-Trace-ID"] = trace_id
                logger.info(
                    "request_completed request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
                    request_id,
                    request.method,
                    request.url.path,
                    response.status_code,
                    duration_ms,
                )
                return response
        finally:
            reset_observability_runtime(observability_token)
            reset_request_id(request_id_token)

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
            details = exc.detail.get("details")
        else:
            details = None
        return _error_response(
            request,
            status_code=exc.status_code,
            code=code,
            message=message,
            details=details if isinstance(details, dict) else None,
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
