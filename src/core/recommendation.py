"""Read-only deterministic parking-slot recommendation."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import ParkingUser
from src.core.errors import DomainError
from src.core.parking_state import ParkingStateService
from src.core.routing import RoutingError, RoutingGraph, RoutingService
from src.models.schemas import (
    ErrorCode,
    ParkingSlot,
    RecommendationCandidate,
    RecommendationRequest,
    RecommendationResult,
    RouteMode,
    SlotStatus,
)

EXIT_NODE_ID = "F1-EXIT"


def _elevator_node_id(floor_id: str) -> str:
    return f"{floor_id}-ELEVATOR"


class RecommendationError(DomainError):
    """Core recommendation error with a stable API-independent error code."""


@dataclass(frozen=True, slots=True)
class _ScoredCandidate:
    slot_id: str
    raw_score: float
    distance_m: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ReachableCandidate:
    slot_id: str
    has_charger: bool
    is_accessible: bool
    distance_m: float
    exit_distance_m: float
    elevator_distance_m: float | None


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
        vehicle_graph = await self.routing.load_graph(mode=RouteMode.VEHICLE)
        self._validate_start_node(vehicle_graph, request.start_node_id)
        pedestrian_graph = await self.routing.load_graph(mode=RouteMode.PEDESTRIAN) if request.near_elevator else None
        slots = await self.parking_state.list_slots()
        parking_state_version = sum(slot.version for slot in slots)

        eligible_slots = [
            slot
            for slot in slots
            if slot.status is SlotStatus.AVAILABLE
            and (request.floor_id is None or slot.floor_id == request.floor_id)
            and (request.zone_id is None or slot.zone_id == request.zone_id)
            and (not request.charging_required or slot.has_charger)
            and (not request.accessible_required or slot.is_accessible)
        ]
        if not eligible_slots:
            return RecommendationResult(
                recommendations=[],
                parking_state_version=parking_state_version,
            )

        reachable = self._reachable_candidates(
            vehicle_graph,
            pedestrian_graph,
            eligible_slots,
            request,
        )
        max_distance = self._max_relevant_distance(reachable)
        scored = [self._score_candidate(candidate, request, max_distance) for candidate in reachable]

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

    def _reachable_candidates(
        self,
        vehicle_graph: RoutingGraph,
        pedestrian_graph: RoutingGraph | None,
        slots: list[ParkingSlot],
        request: RecommendationRequest,
    ) -> list[_ReachableCandidate]:
        try:
            from_start = self.routing.shortest_distances(
                vehicle_graph,
                request.start_node_id,
            )
            to_exit = self.routing.shortest_distances(
                vehicle_graph,
                EXIT_NODE_ID,
                reverse=True,
            )
            to_elevator_by_floor = {}
            if request.near_elevator and pedestrian_graph is not None:
                for floor_id in sorted({slot.floor_id for slot in slots}):
                    elevator_node_id = _elevator_node_id(floor_id)
                    if elevator_node_id in pedestrian_graph.nodes:
                        to_elevator_by_floor[floor_id] = self.routing.shortest_distances(
                            pedestrian_graph,
                            elevator_node_id,
                            reverse=True,
                        )
        except RoutingError as error:
            raise RecommendationError(error.code, error.message, details=error.details) from error

        reachable: list[_ReachableCandidate] = []
        for slot in slots:
            slot_id = slot.id
            distance = from_start.get(slot_id)
            exit_distance = to_exit.get(slot_id)
            elevator_distances = to_elevator_by_floor.get(slot.floor_id)
            elevator_distance = elevator_distances.get(slot_id) if elevator_distances is not None else None
            if distance is None or exit_distance is None:
                continue
            if request.near_elevator and elevator_distance is None:
                continue
            reachable.append(
                _ReachableCandidate(
                    slot_id=slot_id,
                    has_charger=slot.has_charger,
                    is_accessible=slot.is_accessible,
                    distance_m=distance,
                    exit_distance_m=exit_distance,
                    elevator_distance_m=elevator_distance,
                )
            )
        return reachable

    def _score_candidate(
        self,
        candidate: _ReachableCandidate,
        request: RecommendationRequest,
        max_distance: float,
    ) -> _ScoredCandidate:
        distance_score = self._normalized_score(candidate.distance_m, max_distance)
        exit_score = self._normalized_score(candidate.exit_distance_m, max_distance)
        if request.near_elevator:
            assert candidate.elevator_distance_m is not None
            elevator_score = self._normalized_score(
                candidate.elevator_distance_m,
                max_distance,
            )
            raw_score = 100 * (0.50 * distance_score + 0.30 * elevator_score + 0.20 * exit_score)
        else:
            raw_score = 100 * (0.75 * distance_score + 0.25 * exit_score)

        return _ScoredCandidate(
            slot_id=candidate.slot_id,
            raw_score=raw_score,
            distance_m=candidate.distance_m,
            reasons=self._candidate_reasons(
                has_charger=candidate.has_charger,
                is_accessible=candidate.is_accessible,
                near_elevator=request.near_elevator,
            ),
        )

    async def _validate_user(self, user_id: str) -> None:
        if await self.session.get(ParkingUser, user_id) is None:
            raise RecommendationError(
                ErrorCode.USER_NOT_FOUND,
                f"Parking user {user_id} was not found",
                details={"user_id": user_id},
            )

    @staticmethod
    def _validate_start_node(graph: RoutingGraph, start_node_id: str) -> None:
        if start_node_id not in graph.nodes:
            raise RecommendationError(
                ErrorCode.ROUTE_NODE_NOT_FOUND,
                f"Route node {start_node_id} was not found",
                details={"node_ids": [start_node_id]},
            )

    @staticmethod
    def _max_relevant_distance(candidates: list[_ReachableCandidate]) -> float:
        distances = [
            distance
            for candidate in candidates
            for distance in (
                candidate.distance_m,
                candidate.exit_distance_m,
                candidate.elevator_distance_m,
            )
            if distance is not None
        ]
        return max(distances, default=0.0)

    @staticmethod
    def _normalized_score(distance: float, max_distance: float) -> float:
        if max_distance <= 0:
            return 1.0
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
