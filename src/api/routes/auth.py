from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import CredentialsDependency
from src.core.database import get_db_session
from src.core.db_models import AppRoleEnum, ParkingUser, Profile, Vehicle
from src.models.auth import CurrentUser
from src.models.common import SuccessResponse
<<<<<<< HEAD
from src.services.auth_service import get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])
=======
from src.services.auth_service import (
    _auth_error,
    get_current_user,
    verify_supabase_access_token,
)

router = APIRouter(prefix="/auth", tags=["Auth"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


class AddVehicleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plate_number: str = Field(min_length=2, max_length=32)
    requires_charging: bool = False

    @field_validator("plate_number")
    @classmethod
    def normalize_plate(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) < 2:
            raise ValueError("plate_number is invalid")
        return normalized


async def _new_parking_user_id(session: AsyncSession) -> str:
    for _attempt in range(10):
        user_id = f"USER-{uuid4()}"
        if await session.get(ParkingUser, user_id) is None:
            return user_id
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "ID_GENERATION_FAILED", "message": "Could not allocate user id."},
    )


async def _new_vehicle_id(session: AsyncSession) -> str:
    for _attempt in range(10):
        vehicle_id = f"VEHICLE-{uuid4()}"
        if await session.get(Vehicle, vehicle_id) is None:
            return vehicle_id
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "ID_GENERATION_FAILED", "message": "Could not allocate vehicle id."},
    )
>>>>>>> feat/phase11-role-based-auth


@router.get("/me", response_model=SuccessResponse[CurrentUser])
async def me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> SuccessResponse[CurrentUser]:
    return SuccessResponse(data=current_user, message="Current user loaded.")


<<<<<<< HEAD
=======
@router.post("/onboarding", response_model=SuccessResponse[CurrentUser])
async def onboard_authenticated_user(
    credentials: CredentialsDependency,
    session: SessionDependency,
) -> SuccessResponse[CurrentUser]:
    if credentials is None:
        raise _auth_error(status.HTTP_401_UNAUTHORIZED, "AUTH_REQUIRED", "Authentication is required.")

    auth_user = await verify_supabase_access_token(credentials.credentials)
    try:
        auth_user_id = UUID(str(auth_user["id"]))
    except (KeyError, TypeError, ValueError) as error:
        raise _auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN",
            "The access token is invalid or expired.",
        ) from error

    async with session.begin():
        existing = await session.scalar(select(Profile).where(Profile.id == auth_user_id))
        if existing is not None:
            return SuccessResponse(
                data=await get_current_user(credentials, session),
                message="Existing ParkSmart profile loaded.",
            )

        email = str(auth_user.get("email") or "") or None
        full_name = None
        metadata = auth_user.get("user_metadata")
        if isinstance(metadata, dict):
            raw_name = metadata.get("full_name") or metadata.get("name")
            full_name = str(raw_name).strip() if raw_name else None
        display_name = full_name or email or "ParkSmart User"
        parking_user_id = await _new_parking_user_id(session)
        session.add(ParkingUser(id=parking_user_id, display_name=display_name))
        session.add(
            Profile(
                id=auth_user_id,
                email=email,
                full_name=full_name,
                app_role=AppRoleEnum.USER,
                parking_user_id=parking_user_id,
                default_vehicle_id=None,
            )
        )
        await session.flush()

    return SuccessResponse(
        data=await get_current_user(credentials, session),
        message="ParkSmart profile created.",
    )


@router.post("/vehicles", response_model=SuccessResponse[CurrentUser])
async def add_first_vehicle(
    payload: AddVehicleRequest,
    credentials: CredentialsDependency,
    session: SessionDependency,
) -> SuccessResponse[CurrentUser]:
    current_user = await get_current_user(credentials, session)
    if current_user.parking_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PARKING_IDENTITY_NOT_LINKED",
                "message": "This user profile is not linked to a parking identity.",
            },
        )

    profile = await session.get(Profile, current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROFILE_NOT_FOUND", "message": "The ParkSmart profile does not exist."},
        )

    vehicle = Vehicle(
        id=await _new_vehicle_id(session),
        user_id=current_user.parking_user_id,
        plate_number=payload.plate_number,
        requires_charging=payload.requires_charging,
    )
    session.add(vehicle)
    if profile.default_vehicle_id is None:
        profile.default_vehicle_id = vehicle.id
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "VEHICLE_ALREADY_EXISTS",
                "message": "A vehicle with this plate number already exists.",
            },
        ) from error

    return SuccessResponse(
        data=await get_current_user(credentials, session),
        message="Vehicle added.",
    )


>>>>>>> feat/phase11-role-based-auth
__all__ = ["router"]
