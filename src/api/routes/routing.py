"""Shortest-route API backed by the core Routing Service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import require_authenticated_or_demo
from src.api.errors import domain_http_error
from src.core.database import get_db_session
from src.core.routing import RoutingError, RoutingService
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import FloorScopedId, RouteMode, RouteResult

router = APIRouter(
    prefix="/routes",
    tags=["Routing"],
    dependencies=[Depends(require_authenticated_or_demo)],
)
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_node_id: FloorScopedId
    destination_node_id: FloorScopedId
    mode: RouteMode


class RouteResponse(RouteResult):
    start_node_id: FloorScopedId
    destination_node_id: FloorScopedId


def _domain_error(error: RoutingError) -> HTTPException:
    return domain_http_error(error)


@router.post(
    "",
    response_model=SuccessResponse[RouteResponse],
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def shortest_route(
    request: RouteRequest,
    session: SessionDependency,
) -> SuccessResponse[RouteResponse]:
    try:
        route = await RoutingService(session).get_route(
            request.start_node_id,
            request.destination_node_id,
            mode=request.mode,
        )
    except RoutingError as error:
        raise _domain_error(error) from error

    return SuccessResponse(
        data=RouteResponse(
            start_node_id=request.start_node_id,
            destination_node_id=request.destination_node_id,
            **route.model_dump(),
        )
    )


__all__ = ["router"]
