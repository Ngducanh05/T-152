from src.core.route_guidance import vietnamese_route_guidance


def test_d06_guidance_uses_real_turns_without_internal_node_names():
    guidance = vietnamese_route_guidance(
        ["F1-ENTRANCE", "F1-CP1", "F1-CP2", "F1-D-W", "F1-D06"],
        76,
    )

    assert "đi thẳng" in guidance
    assert "Ở ngã tư phía trước, rẽ phải" in guidance
    assert "rẽ trái vào ô D06" in guidance
    assert "76 m" in guidance
    assert "CP1" not in guidance
    assert "CP2" not in guidance
    assert "D-W" not in guidance


def test_floor_change_guidance_uses_everyday_direction_without_ramp_term():
    guidance = vietnamese_route_guidance(
        ["F1-CP3", "F1-RAMP", "F2-RAMP", "F2-A-W", "F2-A01"],
        48,
    )

    assert "Đi đường dốc xuống tầng 2" in guidance
    assert "ramp" not in guidance.lower()
    assert "checkpoint" not in guidance.lower()
    assert "CP3" not in guidance
