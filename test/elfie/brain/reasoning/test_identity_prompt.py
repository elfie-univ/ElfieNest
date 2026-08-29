from datetime import datetime, timezone
from types import SimpleNamespace

from elfie.brain.activity.context import ActivityContext
from elfie.brain.emotion.contracts import EmotionSnapshot, EmotionValue
from elfie.brain.energy.contracts import EnergySnapshot
from elfie.brain.orientation.contracts import OrientationSnapshot
from elfie.brain.reasoning.coordinator_turn import CoordinatorTurnFactory
from elfie.brain.selfhood.contracts import (
    BigFiveTraits,
    ProfileAnchorSnapshot,
    SelfhoodSnapshot,
    SelfhoodSpeechStyle,
)
from elfie.message_types import ActorRef


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


def test_fast_prompt_uses_brain_state_and_does_not_repeat_current_message() -> None:
    now = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)
    owner = ActorRef(actor_id="owner-1", source_kind="owner")
    elfie = ActorRef(actor_id="elfie-1", source_kind="elfie")
    current_text = "今晚提醒我带钥匙"
    compiled = SimpleNamespace(
        profile_anchors=ProfileAnchorSnapshot(
            revision=1,
            captured_at=now,
            elfie_id="elfie-1",
            display_name="Lumi",
            species_id="fox",
        ),
        selfhood=SelfhoodSnapshot(
            revision=1,
            captured_at=now,
            profile_revision=1,
            big_five=BigFiveTraits(openness=0.8, agreeableness=0.7),
            self_description="安静、好奇，而且会认真兑现承诺",
            speech_style=SelfhoodSpeechStyle(verbal_tick="呀"),
            norms=("不把没有完成的事说成已经完成。",),
            identity_facts=("主人喜欢被叫作站长。",),
        ),
        events=(
            SimpleNamespace(
                event_id="current-owner-message",
                modality="social:message",
                actor=owner,
                occurred_at=now,
                content=current_text,
            ),
        ),
        conversation=(
            SimpleNamespace(
                event_id="previous-owner-message",
                actor=owner,
                occurred_at=now,
                content="我喜欢蓝色。",
            ),
            SimpleNamespace(
                event_id="previous-elfie-reply",
                actor=elfie,
                occurred_at=now,
                content="我记住啦。",
            ),
            SimpleNamespace(
                event_id="current-owner-message",
                actor=owner,
                occurred_at=now,
                content=current_text,
            ),
        ),
        memories=(
            SimpleNamespace(content="主人此前说过自己喜欢蓝色。", relevance=0.9),
            SimpleNamespace(content="主人常在傍晚散步。", relevance=0.8),
            SimpleNamespace(content="主人喜欢安静的房间。", relevance=0.7),
            SimpleNamespace(content="主人曾经照顾过一只猫。", relevance=0.6),
            SimpleNamespace(content="主人把这段经历称为重要回忆。", relevance=0.5),
        ),
        emotion=EmotionSnapshot(
            revision=1,
            captured_at=now,
            values=(
                EmotionValue(name="attachment", intensity=0.62),
                EmotionValue(name="happiness", intensity=0.41),
            ),
            dominant="attachment",
        ),
        homeostasis=EnergySnapshot(
            revision=1,
            captured_at=now,
            energy=72.0,
            fatigue=18.0,
            sleeping=False,
            cognitive_mode="normal",
            available_cognitive_budget=60.0,
            normal_budget_available=50.0,
            emergency_reserve_available=10.0,
        ),
        orientation=OrientationSnapshot(
            revision=1,
            captured_at=now,
            location="客厅",
            location_source="observation",
            active_channel_id="chat",
            active_conversation_id="owner-chat",
            freshness="current",
        ),
        activities=ActivityContext(
            revision=0,
            captured_at=now,
            items=(),
        ),
        capabilities=SimpleNamespace(revision=3),
    )

    system_prompt, user_prompt = CoordinatorTurnFactory._model_prompts(
        compiled,
        fast_owner_reply=True,
    )

    assert "SELF_EXPRESSION_POLICY" in system_prompt
    assert "不把没有完成的事说成已经完成" in system_prompt
    assert "CURRENT_BRAIN_STATE" in system_prompt
    assert "attachment" in system_prompt
    assert "energy=72" in system_prompt
    assert "客厅" in system_prompt
    assert "RELEVANT_MEMORY" in user_prompt
    assert "此前说过自己喜欢蓝色" in user_prompt
    assert "重要回忆" in user_prompt
    assert "owner: 我喜欢蓝色" in user_prompt
    assert "elfie: 我记住啦" in user_prompt
    assert user_prompt.count(current_text) == 1
