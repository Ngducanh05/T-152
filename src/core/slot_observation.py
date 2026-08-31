"""Pending, admin-verified observations for slots beside an active session."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.db_models import (
    ParkingSession,
    ParkingSlot,
    ParkingUser,
    RewardTransaction,
    SlotObservation,
)
from src.core.errors import DomainError
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.core.reward import RewardError, RewardService
from src.models.schemas import (
    ErrorCode,
    ParkingSessionStatus,
    RewardSourceType,
    SlotObservationStatus,
    SlotStatus,
    is_slot_id,
)


def adjacent_slot_ids(slot_id: str) -> tuple[str, ...]:
    """Return left/right neighbours on F1-F3 without crossing a five-slot row."""
    if not is_slot_id(slot_id):
        return ()
    floor_id, zone_and_number = slot_id.split("-", maxsplit=1)
    zone_id = zone_and_number[0]
    number = int(zone_and_number[1:])
    row_start = 1 if number <= 5 else 6
    row_end = row_start + 4
    return tuple(
        f"{floor_id}-{zone_id}{candidate:02d}"
        for candidate in (number - 1, number + 1)
        if row_start <= candidate <= row_end
    )


class SlotObservationError(DomainError):
    pass


class SlotObservationService:
    def __init__(
        self,
        session: AsyncSession,
        parking_state: ParkingStateService | None = None,
        *,
        reward_service: RewardService | None = None,
        settings: Settings | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.parking_state = parking_state or ParkingStateService(session)
        self.rewards = reward_service or RewardService(session, settings=self.settings, clock=self.clock)

    def _now(self) -> datetime:
        value = self.clock()
        if value.utcoffset() != timedelta(0):
            raise SlotObservationError(
                ErrorCode.INVALID_OBSERVATION_TRANSITION,
                "Observation clock must use UTC.",
            )
        return value

    async def create_observation(
        self,
        *,
        user_id: str,
        slot_id: str,
        observed_status: SlotStatus,
        expected_slot_version: int,
        observation_id: str | None = None,
        evidence_storage_path: str | None = None,
        evidence_content_type: str | None = None,
        evidence_size_bytes: int | None = None,
    ) -> SlotObservation:
        active_session, slot = await self._validate_create_request(
            user_id=user_id,
            slot_id=slot_id,
            observed_status=observed_status,
            expected_slot_version=expected_slot_version,
            lock=True,
        )
        now = self._now()
        observation = SlotObservation(
            id=observation_id or f"OBSERVATION-{uuid4()}",
            observer_user_id=user_id,
            observer_session_id=active_session.id,
            slot_id=slot_id,
            observed_status=observed_status,
            verification_status=SlotObservationStatus.PENDING,
            reward_points=0,
            observed_slot_version=slot.version,
            created_at=now,
            expires_at=now + timedelta(seconds=self.settings.observation_verification_ttl_seconds),
            verified_at=None,
            verified_by=None,
            rejection_reason=None,
            evidence_storage_path=evidence_storage_path,
            evidence_content_type=evidence_content_type,
            evidence_size_bytes=evidence_size_bytes,
            version=0,
        )
        self.session.add(observation)
        reward = await self.rewards.reserve_contribution_reward(
            user_id=user_id,
            source_type=RewardSourceType.ADJACENT_SLOT_OBSERVATION,
            source_reference=observation.id,
            requested_points=self.settings.adjacent_observation_reward_points,
            metadata={"slot_id": slot.id, "floor_id": slot.floor_id},
        )
        observation.reward_points = reward.points_delta if reward is not None else 0
        await self.session.flush()
        observation.reward_status = reward.status if reward is not None else None
        return observation

    async def preflight_create_observation(
        self,
        *,
        user_id: str,
        slot_id: str,
        observed_status: SlotStatus,
        expected_slot_version: int,
    ) -> None:
        """Reject obvious invalid uploads without retaining locks across storage I/O."""
        await self._validate_create_request(
            user_id=user_id,
            slot_id=slot_id,
            observed_status=observed_status,
            expected_slot_version=expected_slot_version,
            lock=False,
        )

    async def _validate_create_request(
        self,
        *,
        user_id: str,
        slot_id: str,
        observed_status: SlotStatus,
        expected_slot_version: int,
        lock: bool,
    ) -> tuple[ParkingSession, ParkingSlot]:
        if observed_status not in {SlotStatus.AVAILABLE, SlotStatus.OCCUPIED}:
            raise SlotObservationError(
                ErrorCode.INVALID_OBSERVATION_TRANSITION,
                "Observations only support AVAILABLE or OCCUPIED.",
            )
        if await self.session.get(ParkingUser, user_id) is None:
            raise SlotObservationError(
                ErrorCode.USER_NOT_FOUND,
                f"Parking user {user_id} was not found.",
            )
        active_session_snapshot = await self.session.scalar(
            select(ParkingSession).where(
                ParkingSession.user_id == user_id,
                ParkingSession.status == ParkingSessionStatus.ACTIVE,
            )
        )
        if active_session_snapshot is None:
            raise SlotObservationError(
                ErrorCode.ACTIVE_SESSION_NOT_FOUND,
                f"No active parking session exists for user {user_id}.",
            )
        if slot_id == active_session_snapshot.slot_id or slot_id not in adjacent_slot_ids(
            active_session_snapshot.slot_id
        ):
            raise SlotObservationError(
                ErrorCode.INVALID_OBSERVATION_TRANSITION,
                f"Parking slot {slot_id} is not adjacent to {active_session_snapshot.slot_id}.",
                details={"slot_id": slot_id, "parked_slot_id": active_session_snapshot.slot_id},
            )
        slot_query = select(ParkingSlot).where(ParkingSlot.id == slot_id)
        if lock:
            slot_query = slot_query.with_for_update()
        slot = await self.session.scalar(slot_query)
        if slot is None:
            raise SlotObservationError(ErrorCode.SLOT_NOT_FOUND, f"Parking slot {slot_id} was not found.")
        active_session_query = select(ParkingSession).where(ParkingSession.id == active_session_snapshot.id)
        if lock:
            active_session_query = active_session_query.with_for_update()
        active_session = await self.session.scalar(active_session_query)
        if active_session is None or active_session.status is not ParkingSessionStatus.ACTIVE:
            raise SlotObservationError(
                ErrorCode.ACTIVE_SESSION_NOT_FOUND,
                f"No active parking session exists for user {user_id}.",
            )
        if slot.status is SlotStatus.RESERVED:
            raise SlotObservationError(
                ErrorCode.INVALID_OBSERVATION_TRANSITION,
                "A reserved slot cannot be observed.",
                details={"slot_id": slot_id},
            )
        if slot.version != expected_slot_version:
            raise SlotObservationError(
                ErrorCode.OBSERVATION_VERSION_CONFLICT,
                f"Parking slot {slot_id} version changed.",
                details={
                    "expected_version": expected_slot_version,
                    "actual_version": slot.version,
                },
            )
        existing = await self.session.scalar(
            select(SlotObservation).where(
                SlotObservation.observer_session_id == active_session.id,
                SlotObservation.slot_id == slot_id,
            )
        )
        if existing is not None:
            raise SlotObservationError(
                ErrorCode.OBSERVATION_ALREADY_EXISTS,
                f"Session {active_session.id} already observed slot {slot_id}.",
                details={"observation_id": existing.id},
            )

        return active_session, slot

    async def expire_pending(self) -> int:
        now = self._now()
        observations = list(
            await self.session.scalars(
                select(SlotObservation)
                .where(
                    SlotObservation.verification_status == SlotObservationStatus.PENDING,
                    SlotObservation.expires_at <= now,
                )
                .with_for_update()
            )
        )
        for observation in observations:
            observation.verification_status = SlotObservationStatus.EXPIRED
            observation.version += 1
            await self.rewards.cancel_pending(RewardSourceType.ADJACENT_SLOT_OBSERVATION, observation.id)
        if observations:
            await self.session.flush()
        return len(observations)

    async def _attach_reward_status(self, observations: Sequence[SlotObservation]) -> None:
        ids = [observation.id for observation in observations]
        if not ids:
            return
        transactions = list(
            await self.session.scalars(
                select(RewardTransaction).where(
                    RewardTransaction.source_type == RewardSourceType.ADJACENT_SLOT_OBSERVATION,
                    RewardTransaction.source_reference.in_(ids),
                )
            )
        )
        by_source = {transaction.source_reference: transaction for transaction in transactions}
        for observation in observations:
            reward = by_source.get(observation.id)
            observation.reward_status = reward.status if reward is not None else None

    async def list_observations(
        self,
        *,
        status: SlotObservationStatus | None = None,
        floor_id: str | None = None,
        slot_id: str | None = None,
        user_id: str | None = None,
        limit: int = 20,
    ) -> Sequence[SlotObservation]:
        await self.expire_pending()
        query = select(SlotObservation)
        if floor_id is not None:
            query = query.join(ParkingSlot).where(ParkingSlot.floor_id == floor_id)
        if status is not None:
            query = query.where(SlotObservation.verification_status == status)
        if slot_id is not None:
            query = query.where(SlotObservation.slot_id == slot_id)
        if user_id is not None:
            query = query.where(SlotObservation.observer_user_id == user_id)
        observations = (
            await self.session.scalars(
                query.order_by(SlotObservation.created_at.desc(), SlotObservation.id.desc()).limit(limit)
            )
        ).all()
        await self._attach_reward_status(observations)
        return observations

    async def get_observation(self, observation_id: str, *, for_update: bool = False) -> SlotObservation:
        query = select(SlotObservation).where(SlotObservation.id == observation_id)
        if for_update:
            query = query.with_for_update()
        observation = await self.session.scalar(query)
        if observation is None:
            raise SlotObservationError(
                ErrorCode.OBSERVATION_NOT_FOUND,
                f"Slot observation {observation_id} was not found.",
            )
        await self._attach_reward_status([observation])
        return observation

    @staticmethod
    def _check_version(observation: SlotObservation, expected_version: int) -> None:
        if observation.version != expected_version:
            raise SlotObservationError(
                ErrorCode.OBSERVATION_VERSION_CONFLICT,
                f"Observation {observation.id} version changed.",
                details={
                    "expected_version": expected_version,
                    "actual_version": observation.version,
                },
            )

    async def verify_observation(
        self,
        observation_id: str,
        *,
        verified_by: str,
        expected_version: int,
    ) -> SlotObservation:
        observation_snapshot = await self.get_observation(observation_id)
        await self.parking_state.lock_slot(observation_snapshot.slot_id)
        observation = await self.get_observation(observation_id, for_update=True)
        if observation.verification_status is SlotObservationStatus.EXPIRED or observation.expires_at <= self._now():
            raise SlotObservationError(
                ErrorCode.OBSERVATION_EXPIRED,
                f"Observation {observation.id} has expired.",
            )
        self._check_version(observation, expected_version)
        if observation.verification_status is not SlotObservationStatus.PENDING:
            raise SlotObservationError(
                ErrorCode.INVALID_OBSERVATION_TRANSITION,
                f"Observation {observation.id} is already {observation.verification_status.value}.",
            )
        try:
            await self.parking_state.apply_verified_slot_observation(
                observation.slot_id,
                observed_status=observation.observed_status,
                admin_id=verified_by,
                observation_id=observation.id,
                expected_version=observation.observed_slot_version,
                now=self._now(),
            )
        except ParkingStateError as error:
            code = (
                ErrorCode.OBSERVATION_VERSION_CONFLICT
                if error.code is ErrorCode.SLOT_NOT_AVAILABLE
                else ErrorCode.INVALID_OBSERVATION_TRANSITION
            )
            raise SlotObservationError(code, error.message, details=error.details) from error
        observation.verification_status = SlotObservationStatus.VERIFIED
        observation.verified_at = self._now()
        observation.verified_by = verified_by
        observation.version += 1
        try:
            reward = await self.rewards.settle_pending(RewardSourceType.ADJACENT_SLOT_OBSERVATION, observation.id)
        except RewardError as error:
            raise SlotObservationError(error.code, error.message, details=error.details) from error
        observation.reward_status = reward.status if reward is not None else None
        await self.session.flush()
        return observation

    async def reject_observation(
        self,
        observation_id: str,
        *,
        rejected_by: str,
        reason: str | None,
        expected_version: int,
    ) -> SlotObservation:
        await self.expire_pending()
        observation = await self.get_observation(observation_id, for_update=True)
        if observation.verification_status is SlotObservationStatus.EXPIRED:
            raise SlotObservationError(
                ErrorCode.OBSERVATION_EXPIRED,
                f"Observation {observation.id} has expired.",
            )
        self._check_version(observation, expected_version)
        if observation.verification_status is not SlotObservationStatus.PENDING:
            raise SlotObservationError(
                ErrorCode.INVALID_OBSERVATION_TRANSITION,
                f"Observation {observation.id} is already {observation.verification_status.value}.",
            )
        observation.verification_status = SlotObservationStatus.REJECTED
        observation.verified_at = self._now()
        observation.verified_by = rejected_by
        observation.rejection_reason = reason.strip() if reason else None
        observation.version += 1
        reward = await self.rewards.cancel_pending(RewardSourceType.ADJACENT_SLOT_OBSERVATION, observation.id)
        observation.reward_status = reward.status if reward is not None else None
        await self.session.flush()
        return observation


__all__ = ["SlotObservationError", "SlotObservationService", "adjacent_slot_ids"]
