"""User contribution history and authoritative ParkSmart Points summaries."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.db_models import SlotObservation, WrongParkingReport
from src.core.reward import RewardError, RewardService
from src.core.slot_observation import SlotObservationService
from src.models.common import SuccessResponse
from src.models.schemas import (
    ContributionRecord,
    RewardConfiguration,
    RewardSourceType,
    RewardSummary,
)

router = APIRouter(tags=["Contributions", "Rewards"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


def _reward_error(error: RewardError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": error.code.value, "message": error.message},
    )


@router.get(
    "/contributions/users/{user_id}",
    response_model=SuccessResponse[list[ContributionRecord]],
)
async def user_contributions(
    user_id: str,
    session: SessionDependency,
) -> SuccessResponse[list[ContributionRecord]]:
    async with session.begin():
        await SlotObservationService(session).expire_pending()
    rewards = RewardService(session)
    try:
        transactions = list(await rewards.list_user_transactions(user_id))
    except RewardError as error:
        raise _reward_error(error) from error

    records: dict[tuple[RewardSourceType, str], ContributionRecord] = {}
    for transaction in transactions:
        slot_id = str(transaction.transaction_metadata.get("slot_id", ""))
        floor_id = str(transaction.transaction_metadata.get("floor_id", ""))
        if not slot_id or floor_id not in {"F1", "F2", "F3"}:
            continue
        records[(transaction.source_type, transaction.source_reference)] = (
            ContributionRecord(
                id=transaction.id,
                source_type=transaction.source_type,
                source_reference=transaction.source_reference,
                observer_session_id=None,
                floor_id=floor_id,  # type: ignore[arg-type]
                slot_id=slot_id,
                points=transaction.points,
                status=transaction.status,
                created_at=transaction.created_at,
                settled_at=transaction.settled_at,
            )
        )

    observations = (
        await session.scalars(
            select(SlotObservation).where(SlotObservation.observer_user_id == user_id)
        )
    ).all()
    reports = (
        await session.scalars(
            select(WrongParkingReport).where(WrongParkingReport.reporter_user_id == user_id)
        )
    ).all()
    contributions = [
        (item, RewardSourceType.ADJACENT_SLOT_OBSERVATION) for item in observations
    ] + [(item, RewardSourceType.WRONG_PARKING_REPORT) for item in reports]
    for contribution, source_type in contributions:
        key = (source_type, contribution.id)
        if key in records:
            if source_type is RewardSourceType.ADJACENT_SLOT_OBSERVATION:
                records[key] = records[key].model_copy(
                    update={
                        "observer_session_id": contribution.observer_session_id
                    }
                )
            continue
        records[key] = ContributionRecord(
            id=contribution.id,
            source_type=source_type,
            source_reference=contribution.id,
            observer_session_id=(
                contribution.observer_session_id
                if source_type is RewardSourceType.ADJACENT_SLOT_OBSERVATION
                else None
            ),
            floor_id=contribution.slot_id[:2],  # type: ignore[arg-type]
            slot_id=contribution.slot_id,
            points=0,
            status=None,
            created_at=contribution.created_at,
            settled_at=None,
        )
    ordered = sorted(
        records.values(), key=lambda item: (item.created_at, item.id), reverse=True
    )
    return SuccessResponse(data=ordered)


@router.get(
    "/rewards/users/{user_id}/summary",
    response_model=SuccessResponse[RewardSummary],
)
async def user_reward_summary(
    user_id: str,
    session: SessionDependency,
) -> SuccessResponse[RewardSummary]:
    async with session.begin():
        await SlotObservationService(session).expire_pending()
    try:
        summary = await RewardService(session).get_summary(user_id)
    except RewardError as error:
        raise _reward_error(error) from error
    return SuccessResponse(data=summary)


@router.get(
    "/rewards/configuration",
    response_model=SuccessResponse[RewardConfiguration],
)
async def reward_configuration() -> SuccessResponse[RewardConfiguration]:
    settings = get_settings()
    return SuccessResponse(
        data=RewardConfiguration(
            adjacent_observation_reward_points=(
                settings.adjacent_observation_reward_points
            ),
            wrong_parking_report_reward_points=(
                settings.wrong_parking_report_reward_points
            ),
            contribution_daily_points_limit=(
                settings.contribution_daily_points_limit
            ),
        )
    )


__all__ = ["router"]
