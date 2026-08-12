"""API v1 route composition."""

from fastapi import APIRouter

from src.api.routes.auth import router as auth_router
from src.api.routes.health import router as health_router
from src.api.routes.parking import router as parking_router
from src.api.routes.routing import router as routing_router
from src.api.routes.simulator import router as simulator_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(health_router)
api_router.include_router(parking_router)
api_router.include_router(routing_router)
api_router.include_router(simulator_router)

__all__ = ["api_router"]
