"""Deterministic read-only parking-slot recommendation service."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import MapEdge, MapNode, ParkingUser
from src.core.parking_state import ParkingStateService
from src.core.routing import RoutingError, RoutingService
from src.models.schemas import (
    ErrorCode,
    RecommendationCandidate,
    RecommendationRequest,
    RecommendationResult,
    SlotStatus,
)

ELEVATOR_NODE_ID = "F1-ELEVATOR"
EXIT_NODE_ID = "F1-EXIT"


class RecommendationError(Exception):
    """Core recommendation error with a stable API-independent error code."""

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


@dataclass(frozen=True, slots=True)
class _ScoredCandidate:
    slot_id: str
    raw_score: float
    distance_m: float
    reasons: tuple[str, ...]


class RecommendationService:
    """Filter one parking-state snapshot and score reachable available slots."""

    def __init__(
        self,
        session: AsyncSession,
        parking_state: ParkingStateService,
        routing: RoutingService,
    ) -> None:
        self.session = session
        self.parking_state = parking_state
        self.routing = routing

    async def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        await self._validate_user(request.user_id)
        start_node = await self._get_start_node(request.start_node_id)
        slots = await self.parking_state.list_slots()
        parking_state_version = sum(slot.version for slot in slots)
        max_distance = await self._enabled_graph_distance_bound()

        scored: list[_ScoredCandidate] = []
        for slot in slots:
            if slot.status is not SlotStatus.AVAILABLE:
                continue
            if slot.floor_id != start_node.floor_id:
                continue
            if request.charging_required and not slot.has_charger:
                continue
            if request.accessible_required and not slot.is_accessible:
                continue

            candidate = await self._score_candidate(
                slot.id,
                has_charger=slot.has_charger,
                is_accessible=slot.is_accessible,
                request=request,
                max_distance=max_distance,
            )
            if candidate is not None:
                scored.append(candidate)

        scored.sort(
            key=lambda candidate: (
                -candidate.raw_score,
                candidate.distance_m,
                candidate.slot_id,
            )
        )
        return RecommendationResult(
            recommendations=[
                RecommendationCandidate(
                    slot_id=candidate.slot_id,
                    score=candidate.raw_score,
                    distance_m=candidate.distance_m,
                    reasons=list(candidate.reasons),
                )
                for candidate in scored[: request.limit]
            ],
            parking_state_version=parking_state_version,
        )

    async def _score_candidate(
        self,
        slot_id: str,
        *,
        has_charger: bool,
        is_accessible: bool,
        request: RecommendationRequest,
        max_distance: float,
    ) -> _ScoredCandidate | None:
        if max_distance <= 0:
            return None
        try:
            distance = (
                await self.routing.get_route(request.start_node_id, slot_id)
            ).distance_m
            exit_distance = (
                await self.routing.get_route(slot_id, EXIT_NODE_ID)
            ).distance_m
            elevator_distance = None
            if request.near_elevator:
                elevator_distance = (
                    await self.routing.get_route(slot_id, ELEVATOR_NODE_ID)
                ).distance_m
        except RoutingError as error:
            if error.code is ErrorCode.ROUTE_NOT_FOUND:
                return None
            raise RecommendationError(error.code, error.message, details=error.details) from error

        distance_score = self._normalized_score(distance, max_distance)
        exit_score = self._normalized_score(exit_distance, max_distance)
        if request.near_elevator:
            assert elevator_distance is not None
            elevator_score = self._normalized_score(elevator_distance, max_distance)
            raw_score = 100 * (
                0.50 * distance_score
                + 0.30 * elevator_score
                + 0.20 * exit_score
            )
        else:
            raw_score = 100 * (0.75 * distance_score + 0.25 * exit_score)

        return _ScoredCandidate(
            slot_id=slot_id,
            raw_score=raw_score,
            distance_m=distance,
            reasons=self._candidate_reasons(
                has_charger=has_charger,
                is_accessible=is_accessible,
                near_elevator=request.near_elevator,
            ),
        )

    async def _validate_user(self, user_id: str) -> None:
        if await self.session.get(ParkingUser, user_id) is None:
            raise RecommendationError(
                ErrorCode.INVALID_TRANSITION,
                f"Parking user {user_id} was not found",
                details={"user_id": user_id},
            )

    async def _get_start_node(self, start_node_id: str) -> MapNode:
        node = await self.session.get(MapNode, start_node_id)
        if node is None:
            raise RecommendationError(
                ErrorCode.ROUTE_NODE_NOT_FOUND,
                f"Route node {start_node_id} was not found",
                details={"node_ids": [start_node_id]},
            )
        return node

    async def _enabled_graph_distance_bound(self) -> float:
        return float(
            await self.session.scalar(
                select(func.coalesce(func.sum(MapEdge.distance_m), 0.0)).where(
                    MapEdge.enabled.is_(True)
                )
            )
            or 0.0
        )

    @staticmethod
    def _normalized_score(distance: float, max_distance: float) -> float:
        return 1.0 - min(distance / max_distance, 1.0)

    @staticmethod
    def _candidate_reasons(
        *,
        has_charger: bool,
        is_accessible: bool,
        near_elevator: bool,
    ) -> tuple[str, ...]:
        reasons = ["Slot is available"]
        if has_charger:
            reasons.append("EV charging is available")
        if is_accessible:
            reasons.append("Accessible parking requirement is satisfied")
        if near_elevator:
            reasons.append("Elevator proximity is included in the score")
        return tuple(reasons)


async def recommend_parking_slots(
    session: AsyncSession,
    parking_state: ParkingStateService,
    routing: RoutingService,
    request: RecommendationRequest,
) -> RecommendationResult:
    return await RecommendationService(session, parking_state, routing).recommend(request)


__all__ = [
    "RecommendationError",
    "RecommendationService",
    "recommend_parking_slots",
]
