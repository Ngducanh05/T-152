"""Read-only ParkSmart parking-state and canonical-map routes."""

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from starlette.datastructures import UploadFile

from src.api.dependencies import (
    ParkingUserDependency,
    SessionDependency,
    SettingsDependency,
    resolve_parking_user_id,
)
from src.api.errors import domain_http_error
from src.core.config import get_settings
from src.core.db_models import (
    MapEdge as MapEdgeRecord,
)
from src.core.db_models import (
    MapNode as MapNodeRecord,
)
from src.core.db_models import (
    ParkingReservation as ParkingReservationRecord,
)
from src.core.db_models import (
    ParkingSession as ParkingSessionRecord,
)
from src.core.db_models import (
    ParkingSlot as ParkingSlotRecord,
)
from src.core.location import LocationService
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.core.reward import RewardService
from src.core.slot_observation import SlotObservationError, SlotObservationService
from src.models.common import SuccessResponse
from src.models.schemas import (
    ErrorCode,
    FloorId,
    MapEdge,
    MapNode,
    ParkingReservation,
    ParkingSessionStatus,
    ParkingSlot,
    ParkingSlotDefinition,
    ReservationStatus,
    RewardConfiguration,
    RewardSummary,
    SlotId,
    SlotObservation,
    SlotStatus,
    ZoneId,
)
from src.services.image_evidence import ImageEvidenceStorage, read_bounded_image, validate_image

router = APIRouter(prefix="/parking", tags=["Parking"])
logger = logging.getLogger(__name__)


class ParkingStatusResponse(BaseModel):
    total: int
    available: int
    reserved: int
    occupied: int
    by_zone: dict[str, dict[SlotStatus, int]]


class ParkingMapResponse(BaseModel):
    nodes: list[MapNode]
    edges: list[MapEdge]
    slots: list[ParkingSlotDefinition]


class ParkingSnapshotResponse(BaseModel):
    slots: list[ParkingSlot]
    status: ParkingStatusResponse
    state_version: int = Field(ge=0)


class ActiveParkingSessionResponse(BaseModel):
    session_id: str
    vehicle_id: str
    slot_id: SlotId
    destination_node_id: SlotId


class LocationStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    node_id: str


class UserParkingStateResponse(BaseModel):
    current_location: LocationStateResponse | None
    active_reservation: ParkingReservation | None
    active_session: ActiveParkingSessionResponse | None
    reward_summary: RewardSummary
    reward_configuration: RewardConfiguration


class AdjacentSlotObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)
    observed_status: Literal[SlotStatus.AVAILABLE, SlotStatus.OCCUPIED]
    expected_slot_version: int = Field(ge=0)


_OBSERVATION_TEXT_PROPERTIES: dict[str, dict[str, object]] = {
    "user_id": {"type": "string", "minLength": 1},
    "observed_status": {"type": "string", "enum": [SlotStatus.AVAILABLE.value, SlotStatus.OCCUPIED.value]},
    "expected_slot_version": {"type": "integer", "minimum": 0},
}
_OBSERVATION_OPENAPI_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": _OBSERVATION_TEXT_PROPERTIES,
                "required": ["user_id", "observed_status", "expected_slot_version"],
                "additionalProperties": False,
            }
        },
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "properties": {**_OBSERVATION_TEXT_PROPERTIES, "evidence": {"type": "string", "format": "binary"}},
                "required": ["user_id", "observed_status", "expected_slot_version"],
                "additionalProperties": False,
            }
        },
    },
}


def _slot_response(slot: object) -> ParkingSlot:
    return ParkingSlot.model_validate(slot, from_attributes=True)


def _domain_error(error: ParkingStateError) -> HTTPException:
    return domain_http_error(error)


def _observation_error(error: SlotObservationError) -> HTTPException:
    return domain_http_error(
        error,
        status_code=(409 if error.code is ErrorCode.ACTIVE_SESSION_NOT_FOUND else None),
    )


@router.get("/status", response_model=SuccessResponse[ParkingStatusResponse])
async def parking_status(
    session: SessionDependency,
) -> SuccessResponse[ParkingStatusResponse]:
    status = await ParkingStateService(session).get_parking_status()
    return SuccessResponse(data=ParkingStatusResponse.model_validate(status, from_attributes=True))


@router.get("/slots", response_model=SuccessResponse[list[ParkingSlot]])
async def parking_slots(
    session: SessionDependency,
    floor_id: Annotated[FloorId | None, Query()] = None,
    zone_id: Annotated[ZoneId | None, Query()] = None,
    status: Annotated[SlotStatus | None, Query()] = None,
    has_charger: Annotated[bool | None, Query()] = None,
    is_accessible: Annotated[bool | None, Query()] = None,
) -> SuccessResponse[list[ParkingSlot]]:
    slots = await ParkingStateService(session).list_slots(
        zone_id=zone_id,
        status=status,
        has_charger=has_charger,
        is_accessible=is_accessible,
    )
    if floor_id is not None:
        slots = [slot for slot in slots if slot.floor_id == floor_id]
    return SuccessResponse(data=[_slot_response(slot) for slot in slots])


@router.get("/slots/{slot_id}", response_model=SuccessResponse[ParkingSlot])
async def parking_slot(
    slot_id: SlotId,
    session: SessionDependency,
) -> SuccessResponse[ParkingSlot]:
    try:
        slot = await ParkingStateService(session).get_slot(slot_id)
    except ParkingStateError as error:
        raise _domain_error(error) from error
    return SuccessResponse(data=_slot_response(slot))


@router.post(
    "/slots/{slot_id}/observation",
    response_model=SuccessResponse[SlotObservation],
    openapi_extra={"requestBody": _OBSERVATION_OPENAPI_REQUEST_BODY},
)
async def observe_adjacent_parking_slot(
    slot_id: SlotId,
    http_request: Request,
    session: SessionDependency,
    current_user: ParkingUserDependency,
    settings: SettingsDependency,
) -> SuccessResponse[SlotObservation]:
    content_type = http_request.headers.get("content-type", "")
    content_length = http_request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = None
        if declared_length is not None and declared_length > settings.report_evidence_max_bytes + 64 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail={
                    "code": ErrorCode.OBSERVATION_EVIDENCE_TOO_LARGE.value,
                    "message": "Observation evidence must not exceed the configured size limit.",
                },
            )
    evidence_upload: UploadFile | None = None
    try:
        if content_type.startswith("multipart/form-data"):
            try:
                form = await http_request.form(max_files=1, max_fields=4, max_part_size=2048)
                evidence = form.get("evidence")
                if evidence is not None and not isinstance(evidence, UploadFile):
                    raise ValueError("evidence must be an uploaded file")
                evidence_upload = evidence
                payload = AdjacentSlotObservationRequest(
                    user_id=str(form.get("user_id") or ""),
                    observed_status=form.get("observed_status"),
                    expected_slot_version=form.get("expected_slot_version"),
                )
            except (ValidationError, ValueError) as error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={"code": "VALIDATION_ERROR", "message": "Request validation failed."},
                ) from error
        else:
            try:
                payload = AdjacentSlotObservationRequest.model_validate(await http_request.json())
            except (ValidationError, ValueError) as error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={"code": "VALIDATION_ERROR", "message": "Request validation failed."},
                ) from error

        user_id = resolve_parking_user_id(payload.user_id, current_user)
        evidence_bytes: bytes | None = None
        normalized_content_type: str | None = None
        if evidence_upload is not None:
            evidence_bytes = await read_bounded_image(
                evidence_upload,
                max_bytes=settings.report_evidence_max_bytes,
                too_large_code=ErrorCode.OBSERVATION_EVIDENCE_TOO_LARGE.value,
                label="Observation evidence",
            )
            normalized_content_type = validate_image(
                content_type=evidence_upload.content_type,
                data=evidence_bytes,
                max_bytes=settings.report_evidence_max_bytes,
                invalid_code=ErrorCode.OBSERVATION_EVIDENCE_INVALID.value,
                too_large_code=ErrorCode.OBSERVATION_EVIDENCE_TOO_LARGE.value,
                label="Observation evidence",
            )

        observation_id = f"OBSERVATION-{uuid4()}"
        storage = ImageEvidenceStorage(
            settings,
            namespace="slot-observations",
            invalid_code=ErrorCode.OBSERVATION_EVIDENCE_INVALID.value,
            too_large_code=ErrorCode.OBSERVATION_EVIDENCE_TOO_LARGE.value,
            label="Observation evidence",
        )
        async with session.begin():
            await SlotObservationService(session, settings=settings).preflight_create_observation(
                user_id=user_id,
                slot_id=slot_id,
                observed_status=payload.observed_status,
                expected_slot_version=payload.expected_slot_version,
            )
        stored_evidence = None
        if evidence_bytes is not None and normalized_content_type is not None:
            stored_evidence = await storage.upload(
                object_id=observation_id,
                data=evidence_bytes,
                content_type=normalized_content_type,
                allow_demo_fallback=current_user is None,
            )

        async def cleanup_uploaded_evidence() -> None:
            if stored_evidence is None:
                return
            try:
                deleted = await storage.delete(stored_evidence.storage_path)
            except Exception:
                deleted = False
            if not deleted:
                # The original create failure remains authoritative.  Log one
                # best-effort cleanup failure for the orphaned private object.
                logger.warning(
                    "slot_observation_evidence_cleanup_failed observation_id=%s request_id=%s",
                    observation_id,
                    getattr(http_request.state, "request_id", "unknown"),
                )

        try:
            async with session.begin():
                observation = await SlotObservationService(session, settings=settings).create_observation(
                    user_id=user_id,
                    slot_id=slot_id,
                    observed_status=payload.observed_status,
                    expected_slot_version=payload.expected_slot_version,
                    observation_id=observation_id,
                    evidence_storage_path=(stored_evidence.storage_path if stored_evidence is not None else None),
                    evidence_content_type=(stored_evidence.content_type if stored_evidence is not None else None),
                    evidence_size_bytes=(stored_evidence.size_bytes if stored_evidence is not None else None),
                )
        except Exception:
            await cleanup_uploaded_evidence()
            raise
    except SlotObservationError as error:
        raise _observation_error(error) from error
    finally:
        if evidence_upload is not None:
            await evidence_upload.close()
    logger.info(
        "adjacent_slot_observation slot_id=%s actor_id=%s observed_status=%s outcome=success",
        slot_id,
        user_id,
        payload.observed_status.value,
    )
    return SuccessResponse(
        data=SlotObservation.model_validate(observation, from_attributes=True),
        message="Observation submitted for verification.",
    )


@router.get("/map", response_model=SuccessResponse[ParkingMapResponse])
async def parking_map(
    session: SessionDependency,
    response: Response,
) -> SuccessResponse[ParkingMapResponse]:
    nodes = list(await session.scalars(select(MapNodeRecord).order_by(MapNodeRecord.id)))
    edges = list(await session.scalars(select(MapEdgeRecord).order_by(MapEdgeRecord.from_node, MapEdgeRecord.to_node)))
    slots = list(await session.scalars(select(ParkingSlotRecord).order_by(ParkingSlotRecord.id)))
    response.headers["Cache-Control"] = "public, max-age=3600"
    return SuccessResponse(
        data=ParkingMapResponse(
            nodes=[MapNode.model_validate(node, from_attributes=True) for node in nodes],
            edges=[MapEdge.model_validate(edge, from_attributes=True) for edge in edges],
            slots=[ParkingSlotDefinition.model_validate(slot, from_attributes=True) for slot in slots],
        )
    )


@router.get("/snapshot", response_model=SuccessResponse[ParkingSnapshotResponse])
async def parking_snapshot(
    session: SessionDependency,
) -> SuccessResponse[ParkingSnapshotResponse]:
    state = ParkingStateService(session)
    slots = await state.list_slots()
    status = state.summarize_slots(slots)
    return SuccessResponse(
        data=ParkingSnapshotResponse(
            slots=[_slot_response(slot) for slot in slots],
            status=ParkingStatusResponse.model_validate(status, from_attributes=True),
            state_version=sum(slot.version for slot in slots),
        )
    )


@router.get(
    "/users/{user_id}/state",
    response_model=SuccessResponse[UserParkingStateResponse],
)
async def user_parking_state(
    user_id: str,
    session: SessionDependency,
    current_user: ParkingUserDependency,
) -> SuccessResponse[UserParkingStateResponse]:
    user_id = resolve_parking_user_id(user_id, current_user)
    user = await LocationService(session).get_location_state(user_id)
    now = datetime.now(UTC)
    reservation = await session.scalar(
        select(ParkingReservationRecord).where(
            ParkingReservationRecord.user_id == user_id,
            ParkingReservationRecord.status == ReservationStatus.ACTIVE,
            ParkingReservationRecord.expires_at > now,
        )
    )
    parking_session = await session.scalar(
        select(ParkingSessionRecord).where(
            ParkingSessionRecord.user_id == user_id,
            ParkingSessionRecord.status == ParkingSessionStatus.ACTIVE,
        )
    )
    reward_summary = await RewardService(session).get_summary(user_id)
    settings = get_settings()
    return SuccessResponse(
        data=UserParkingStateResponse(
            current_location=(
                LocationStateResponse(
                    user_id=user_id,
                    node_id=user.current_node_id,
                )
                if user.current_node_id is not None
                else None
            ),
            active_reservation=(
                ParkingReservation.model_validate(reservation, from_attributes=True)
                if reservation is not None
                else None
            ),
            active_session=(
                ActiveParkingSessionResponse(
                    session_id=parking_session.id,
                    vehicle_id=parking_session.vehicle_id,
                    slot_id=parking_session.slot_id,
                    destination_node_id=parking_session.slot_id,
                )
                if parking_session is not None
                else None
            ),
            reward_summary=reward_summary,
            reward_configuration=RewardConfiguration(
                adjacent_observation_reward_points=(settings.adjacent_observation_reward_points),
            wrong_parking_report_reward_points=(settings.wrong_parking_report_reward_points),
            contribution_daily_points_limit=(settings.contribution_daily_points_limit),
            redemption_enabled=settings.rewards_redemption_enabled,
        ),
        )
    )
