import pytest
from pydantic import TypeAdapter, ValidationError

from src.models.schemas import SlotId, is_slot_id, normalize_vehicle_plate


@pytest.mark.parametrize("slot_id", ["F1-A01", "F2-C09", "F3-D10"])
def test_canonical_slot_id_accepts_all_supported_floors(slot_id: str) -> None:
    assert TypeAdapter(SlotId).validate_python(slot_id) == slot_id
    assert is_slot_id(slot_id)


@pytest.mark.parametrize(
    "slot_id",
    ["F0-A01", "F4-A01", "F1-E01", "F1-A00", "F1-A11", "F1-A1", "F1-A01-extra"],
)
def test_canonical_slot_id_rejects_non_domain_ids(slot_id: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(SlotId).validate_python(slot_id)
    assert not is_slot_id(slot_id)


@pytest.mark.parametrize("plate", ["51A-12345", "51A 12345", "51a.12345", "51A_12345"])
def test_plate_identity_normalization_collapses_harmless_formatting(plate: str) -> None:
    _display, normalized = normalize_vehicle_plate(plate)
    assert normalized == "51A12345"
