from datetime import datetime, timezone
from types import SimpleNamespace

from elfie.brain.reasoning.coordinator_turn import CoordinatorTurnFactory
from elfie.brain.selfhood.contracts import (
    BigFiveTraits,
    ProfileAnchorSnapshot,
    SelfhoodSnapshot,
)


def test_fast_prompt_contains_canon_identity_and_unknown_boundary() -> None:
    compiled = SimpleNamespace(
        profile_anchors=ProfileAnchorSnapshot(
            revision=1,
            captured_at=datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc),
            elfie_id="elfie-1",
            display_name="Lumi",
            species_id="fox",
            species_canon_id="saevi",
            species_name="Saevi",
            species_shape="fox-like",
            home_world_id="elfaria",
            home_world_name="Elfaria",
            home_region_id="mistyville",
            home_region_name="迷雾镇（Mistyville）",
            civilization_relation_to_earth="Elfaria 的跨世界技术整体低于地球。",
            earth_arrival_statement="地球侧工程人员建造并稳定了传送阵。",
            earth_home_name="ElfieNest",
            earth_home_role="地球生活的基地和家；身份和记忆属于 Elfie 自己。",
            knowledge_boundaries=("未知区域不能由模型自动补齐。",),
        ),
        selfhood=SelfhoodSnapshot(
            revision=0,
            captured_at=datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc),
            profile_revision=1,
            big_five=BigFiveTraits(),
            behavior_anchors=("先观察边缘、声音和可离开的路径。",),
        ),
    )

    prompt = CoordinatorTurnFactory._identity_context(compiled)

    assert "Saevi" in prompt
    assert "Elfaria" in prompt
    assert "传送阵" in prompt
    assert "ElfieNest" in prompt
    assert "不知道" in prompt
    assert "身份、身体和记忆属于你自己" in prompt
    assert "先观察边缘" in prompt
