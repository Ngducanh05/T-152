"""Reward catalog, deterministic redemption, and the owned voucher wallet."""

from typing import Annotated

from fastapi import APIRouter, Header, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError

from src.api.dependencies import ParkingUserDependency, SessionDependency, resolve_parking_user_id
from src.api.errors import domain_http_error
from src.core.config import get_settings
from src.core.errors import DomainError
from src.core.idempotency import IdempotencyService
from src.core.reward import RewardService
from src.core.reward_redemption import RewardCatalogService, RewardRedemptionService
from src.core.slot_observation import SlotObservationService
from src.core.voucher import VoucherService
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import (
    EntityId,
    ErrorCode,
    ParkingVoucher,
    RewardCatalogItem,
    RewardRedemption,
    RewardRedemptionResult,
    RewardTransaction,
)

router = APIRouter(prefix="/rewards", tags=["Rewards"])
ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


class RedeemRewardVoucherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: EntityId
    catalog_item_id: EntityId


class ApplyRewardVoucherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: EntityId
    session_id: EntityId


def _catalog(item: object) -> RewardCatalogItem:
    return RewardCatalogItem.model_validate(item, from_attributes=True)


def _voucher(item: object) -> ParkingVoucher:
    return ParkingVoucher.model_validate(item, from_attributes=True)


def _redemption(item: object) -> RewardRedemption:
    return RewardRedemption.model_validate(item, from_attributes=True)


def _integrity_constraint_name(error: IntegrityError) -> str | None:
    original = error.orig
    name = getattr(original, "constraint_name", None)
    if isinstance(name, str):
        return name
    diagnostic = getattr(original, "diag", None)
    name = getattr(diagnostic, "constraint_name", None)
    if isinstance(name, str):
        return name
    cause = getattr(original, "__cause__", None)
    name = getattr(cause, "constraint_name", None)
    return name if isinstance(name, str) else None


@router.get("/catalog", response_model=SuccessResponse[list[RewardCatalogItem]])
async def reward_catalog(session: SessionDependency) -> SuccessResponse[list[RewardCatalogItem]]:
    return SuccessResponse(data=[_catalog(item) for item in await RewardCatalogService(session).list_active()])


@router.post(
    "/redemptions",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[RewardRedemptionResult],
    responses=ERROR_RESPONSES,
)
async def redeem_reward_voucher(
    request: RedeemRewardVoucherRequest,
    session: SessionDependency,
    current_user: ParkingUserDependency,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128)] = None,
) -> SuccessResponse[RewardRedemptionResult]:
    user_id = resolve_parking_user_id(request.user_id, current_user)
    if not get_settings().rewards_redemption_enabled:
        raise domain_http_error(
            DomainError(ErrorCode.REDEMPTION_DISABLED, "Reward redemption is disabled."),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    try:
        async with session.begin():
            idempotency = IdempotencyService(session)
            claim = await idempotency.claim(
                user_id=user_id,
                operation="redeem_reward_voucher",
                key=idempotency_key,
                payload={"catalog_item_id": request.catalog_item_id},
            )
            replay = idempotency.replay(claim)
            if replay is not None:
                result = RewardRedemptionResult.model_validate(replay)
            else:
                redemption, voucher, balance = await RewardRedemptionService(session).redeem(
                    user_id=user_id, catalog_item_id=request.catalog_item_id
                )
                result = RewardRedemptionResult(
                    redemption=_redemption(redemption), voucher=_voucher(voucher), available_points=balance
                )
                await idempotency.complete(claim, result.model_dump(mode="json"))
    except DomainError as error:
        raise domain_http_error(error) from error
    return SuccessResponse(data=result)


@router.get(
    "/users/{user_id}/ledger",
    response_model=SuccessResponse[list[RewardTransaction]],
    responses=ERROR_RESPONSES,
)
async def user_reward_ledger(
    user_id: str, session: SessionDependency, current_user: ParkingUserDependency
) -> SuccessResponse[list[RewardTransaction]]:
    user_id = resolve_parking_user_id(user_id, current_user)
    try:
        async with session.begin():
            await SlotObservationService(session).expire_pending()
        ledger = await RewardService(session).list_user_ledger(user_id)
    except DomainError as error:
        raise domain_http_error(error) from error
    return SuccessResponse(
        data=[RewardTransaction.model_validate(item, from_attributes=True) for item in ledger]
    )


@router.get(
    "/users/{user_id}/vouchers", response_model=SuccessResponse[list[ParkingVoucher]], responses=ERROR_RESPONSES
)
async def user_vouchers(
    user_id: str, session: SessionDependency, current_user: ParkingUserDependency
) -> SuccessResponse[list[ParkingVoucher]]:
    user_id = resolve_parking_user_id(user_id, current_user)
    try:
        async with session.begin():
            service = VoucherService(session)
            await service.expire_stale(user_id)
            vouchers = await service.list_user_vouchers(user_id)
    except DomainError as error:
        raise domain_http_error(error) from error
    return SuccessResponse(data=[_voucher(item) for item in vouchers])


@router.post(
    "/vouchers/{voucher_id}/apply",
    response_model=SuccessResponse[ParkingVoucher],
    responses=ERROR_RESPONSES,
)
async def apply_reward_voucher(
    voucher_id: str,
    request: ApplyRewardVoucherRequest,
    session: SessionDependency,
    current_user: ParkingUserDependency,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128)] = None,
) -> SuccessResponse[ParkingVoucher]:
    user_id = resolve_parking_user_id(request.user_id, current_user)
    try:
        async with session.begin():
            idempotency = IdempotencyService(session)
            claim = await idempotency.claim(
                user_id=user_id,
                operation="apply_reward_voucher",
                key=idempotency_key,
                payload={"voucher_id": voucher_id, "session_id": request.session_id},
            )
            replay = idempotency.replay(claim)
            if replay is not None:
                result = ParkingVoucher.model_validate(replay)
            else:
                voucher = await VoucherService(session).apply_to_session(
                    user_id=user_id, voucher_id=voucher_id, session_id=request.session_id
                )
                result = _voucher(voucher)
                await idempotency.complete(claim, result.model_dump(mode="json"))
    except IntegrityError as error:
        if _integrity_constraint_name(error) != "uq_parking_vouchers_applied_session":
            raise
        raise domain_http_error(
            DomainError(ErrorCode.INVALID_TRANSITION, "A voucher is already applied to this parking session."),
            status_code=status.HTTP_409_CONFLICT,
        ) from error
    except DomainError as error:
        raise domain_http_error(error) from error
    return SuccessResponse(data=result)


__all__ = ["router"]
