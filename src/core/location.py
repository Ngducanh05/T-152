"""Confirmed user locations backed by canonical database node IDs."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import MapNode, ParkingSlot, ParkingUser
from src.models.schemas import ErrorCode, MapNodeType

_CONFIRMABLE_NODE_TYPES = frozenset(
    {
        MapNodeType.ENTRANCE,
        MapNodeType.EXIT,
        MapNodeType.CHECKPOINT,
        MapNodeType.ELEVATOR,
        MapNodeType.SLOT,
    }
)


class LocationError(Exception):
    """Core location error with a stable API-independent error code."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class LocationService:
    """Validate and persist user-confirmed canonical map locations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def confirm_location(self, user_id: str, node_id: str) -> str:
        node = await self.session.get(MapNode, node_id)
        if node is None:
            raise LocationError(
                ErrorCode.ROUTE_NODE_NOT_FOUND,
                f"Location node {node_id} was not found",
                details={"node_id": node_id},
            )
        if node.type not in _CONFIRMABLE_NODE_TYPES:
            raise LocationError(
                ErrorCode.INVALID_TRANSITION,
                f"Node {node_id} is an internal routing aisle and cannot be confirmed",
                details={"node_id": node_id, "node_type": node.type.value},
            )
        if node.type is MapNodeType.SLOT:
            slot = await self.session.get(ParkingSlot, node_id)
            if slot is None:
                raise LocationError(
                    ErrorCode.SLOT_NOT_FOUND,
                    f"Parking slot {node_id} was not found",
                    details={"slot_id": node_id},
                )

        user = await self._lock_user(user_id)
        user.current_node_id = node_id
        await self.session.flush()
        return node_id

    async def get_current_location(self, user_id: str) -> str | None:
        user = await self.session.get(ParkingUser, user_id)
        if user is None:
            self._raise_user_not_found(user_id)
        return user.current_node_id

    async def _lock_user(self, user_id: str) -> ParkingUser:
        user = await self.session.scalar(
            select(ParkingUser).where(ParkingUser.id == user_id).with_for_update()
        )
        if user is None:
            self._raise_user_not_found(user_id)
        return user

    @staticmethod
    def _raise_user_not_found(user_id: str) -> None:
        raise LocationError(
            ErrorCode.INVALID_TRANSITION,
            f"Parking user {user_id} was not found",
            details={"user_id": user_id},
        )


async def confirm_location(
    session: AsyncSession,
    user_id: str,
    node_id: str,
) -> str:
    return await LocationService(session).confirm_location(user_id, node_id)


async def get_current_location(
    session: AsyncSession,
    user_id: str,
) -> str | None:
    return await LocationService(session).get_current_location(user_id)


__all__ = [
    "LocationError",
    "LocationService",
    "confirm_location",
    "get_current_location",
]
