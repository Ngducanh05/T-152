"""Time-only parking completion benefit composition."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.api.routes.sessions import _completed_response
from src.models.schemas import ParkingSessionStatus


def parking_session(*, parked_at: datetime, completed_at: datetime):
    return SimpleNamespace(
        id="SESSION-001",
        user_id="USER-001",
        vehicle_id="VEHICLE-001",
        slot_id="F1-D01",
        status=ParkingSessionStatus.COMPLETED,
        parked_at=parked_at,
        completed_at=completed_at,
    )


@pytest.mark.parametrize(
    ("elapsed_seconds", "voucher_minutes", "expected_free", "expected_billable"),
    [
        (4_650, None, 0.0, 77.5),
        (4_650, 47, 47.0, 30.5),
        (1_800, 47, 30.0, 0.0),
        (-60, 47, 0.0, 0.0),
    ],
)
def test_completion_composes_exact_time_without_rounding_or_money(
    elapsed_seconds: int,
    voucher_minutes: int | None,
    expected_free: float,
    expected_billable: float,
):
    parked_at = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
    completed_at = datetime.fromtimestamp(
        parked_at.timestamp() + elapsed_seconds,
        tz=UTC,
    )
    voucher = (
        SimpleNamespace(id="VOUCHER-001", free_minutes_snapshot=voucher_minutes)
        if voucher_minutes is not None
        else None
    )

    response = _completed_response(
        parking_session(parked_at=parked_at, completed_at=completed_at),
        voucher,
    )

    assert response.time_benefit.total_minutes == max(0, elapsed_seconds) / 60
    assert response.time_benefit.free_minutes == expected_free
    assert response.time_benefit.billable_minutes == expected_billable
    assert response.time_benefit.voucher_id == (
        "VOUCHER-001" if voucher is not None else None
    )
    payload = response.model_dump(mode="json")
    assert set(payload["time_benefit"]) == {
        "voucher_id",
        "total_minutes",
        "free_minutes",
        "billable_minutes",
    }
    assert not {"price", "amount", "currency", "payment"} & set(payload)
