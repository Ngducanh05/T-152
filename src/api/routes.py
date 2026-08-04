from fastapi import APIRouter, Depends, HTTPException, status

<<<<<<< HEAD
from src.agents.graph import agent
from src.models.auth import CurrentUser
from src.models.common import SuccessResponse
from src.models.schemas import ChatRequest, ChatResponse
from src.services.auth_service import get_current_user
from src.services.database import check_database_connection

router = APIRouter()
=======
from src.models.common import SuccessResponse
from src.services.database import check_database_connection
>>>>>>> 7bfdef8664e5fb388c432168789d837cc6c3dcb0


api_router = APIRouter()


@api_router.get(
    "/health/database",
    response_model=SuccessResponse[dict[str, str]],
    tags=["Health"],
)
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

<<<<<<< HEAD

@router.get("/status")
async def agent_status():
    """Kiểm tra trạng thái agent."""
    return {"status": "ready", "agent": "LangGraph Agent v1.0"}


@router.get("/health/database")
async def database_health() -> dict[str, str]:
    """Check PostgreSQL connectivity without exposing connection details."""
    try:
        await check_database_connection()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": "Database is unavailable.",
            },
        )

    return {"status": "ok", "database": "connected"}


@router.get("/me", response_model=SuccessResponse[CurrentUser], tags=["Authentication"])
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
) -> SuccessResponse[CurrentUser]:
    """Return the authenticated ParkSmart user and application role."""
    return SuccessResponse(data=current_user, message="Current user loaded.")
=======
    return SuccessResponse(
        data={"database": "connected"},
        message="Database is available.",
    )
>>>>>>> 7bfdef8664e5fb388c432168789d837cc6c3dcb0
