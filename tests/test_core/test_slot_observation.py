from src.core.slot_observation import adjacent_slot_ids


def test_adjacent_slot_ids_stay_in_the_same_physical_row():
    assert adjacent_slot_ids("F1-A01") == ("F1-A02",)
    assert adjacent_slot_ids("F1-A03") == ("F1-A02", "F1-A04")
    assert adjacent_slot_ids("F1-A05") == ("F1-A04",)
    assert adjacent_slot_ids("F1-D06") == ("F1-D07",)
    assert adjacent_slot_ids("F1-D08") == ("F1-D07", "F1-D09")
    assert adjacent_slot_ids("F1-D10") == ("F1-D09",)
    assert adjacent_slot_ids("F2-D03") == ("F2-D02", "F2-D04")
    assert adjacent_slot_ids("F3-A05") == ("F3-A04",)
    assert adjacent_slot_ids("F1-B06") == ("F1-B07",)
    assert "F1-A06" not in adjacent_slot_ids("F1-A05")
    assert "F1-A05" not in adjacent_slot_ids("F1-A06")
    assert adjacent_slot_ids("F4-A01") == ()
    assert adjacent_slot_ids("F1-Z99") == ()
