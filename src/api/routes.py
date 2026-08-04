from fastapi import APIRouter, Depends, HTTPException, status

from src.agents.graph import agent
from src.models.auth import CurrentUser
from src.models.common import SuccessResponse
from src.models.schemas import ChatRequest, ChatResponse
from src.services.auth_service import get_current_user
from src.services.database import check_database_connection

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Chat với AI agent."""
    try:
        result = await agent.ainvoke({"query": request.message})
        return ChatResponse(
            response=result.get("response", ""),
            analysis=result.get("analysis", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
