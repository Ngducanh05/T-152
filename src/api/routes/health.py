"""Health routes retained during the feature-router split."""

from fastapi import APIRouter, HTTPException

from src.core.database import check_database_connection
from src.models.common import SuccessResponse

router = APIRouter(tags=["Health"])


@router.get("/health/database", response_model=SuccessResponse[dict[str, str]])
async def database_health() -> SuccessResponse[dict[str, str]]:
    try:
        await check_database_connection()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": "Database connection failed.",
            },
        ) from exc

    return SuccessResponse(
        data={"database": "connected"},
        message="Database is available.",
    )
