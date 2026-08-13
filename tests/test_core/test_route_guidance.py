from src.core.route_guidance import vietnamese_route_guidance


def test_d06_guidance_uses_real_turns_without_internal_node_names():
    guidance = vietnamese_route_guidance(
        ["F1-ENTRANCE", "F1-CP1", "F1-CP2", "F1-D-W", "F1-D06"],
        76,
    )

    assert "đi thẳng" in guidance
    assert "rẽ phải" in guidance
    assert "rẽ trái vào ô D06" in guidance
    assert "76 m" in guidance
    assert "CP1" not in guidance
    assert "CP2" not in guidance
    assert "D-W" not in guidance
