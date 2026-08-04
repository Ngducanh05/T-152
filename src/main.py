from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import api_router
from src.config import get_settings


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    api_router,
    prefix="/api/v1",
)


@app.get("/health", tags=["Health"])
async def application_health() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.app_env,
    }