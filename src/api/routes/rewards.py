"""Reward catalog, deterministic redemption, and the owned voucher wallet."""

from typing import Annotated

from fastapi import APIRouter, Header, status
from pydantic import BaseModel, ConfigDict

from src.api.dependencies import ParkingUserDependency, SessionDependency, resolve_parking_user_id
from src.api.errors import domain_http_error
from src.core.errors import DomainError
from src.core.idempotency import IdempotencyService
from src.core.reward_redemption import RewardCatalogService, RewardRedemptionService
from src.core.voucher import VoucherService
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import EntityId, ParkingVoucher, RewardCatalogItem, RewardRedemption, RewardRedemptionResult

router = APIRouter(prefix="/rewards", tags=["Rewards"])
ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


class RedeemRewardVoucherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: EntityId
    catalog_item_id: EntityId


def _catalog(item: object) -> RewardCatalogItem:
    return RewardCatalogItem.model_validate(item, from_attributes=True)


def _voucher(item: object) -> ParkingVoucher:
    return ParkingVoucher.model_validate(item, from_attributes=True)


def _redemption(item: object) -> RewardRedemption:
    return RewardRedemption.model_validate(item, from_attributes=True)


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


__all__ = ["router"]
