"""Brain-owned Selfhood state and its deterministic model projection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from elfie.brain.selfhood.contracts import (
    BigFiveTraits,
    SelfhoodPromptProjection,
    SelfhoodState,
    normalize_selfhood_mapping,
)
from elfie.brain.state_lifecycle import (
    StateCandidate,
    StateCheckpoint,
    StateCommitReceipt,
    StateCommitStatus,
    StateRestoreError,
    VersionedState,
    VersionedStateStore,
)
from elfie.message_types import UTCDateTime


class SelfhoodGrowthDisabledError(RuntimeError):
    """Phase 1 deliberately has no automatic adaptive-self mutation route."""


class SelfhoodSystem:
    """Own the one atomic Selfhood state for an Elfie.

    ``from_seed`` is the Genesis hand-off used by production assembly.  It
    accepts a complete, already validated state and never reads Profile, Canon,
    Memory, Turn, Emotion or model output.  No other initializer is available
    to ordinary runtime assembly.
    """

    def __init__(
        self,
        *,
        initial_at: UTCDateTime,
        initial: SelfhoodState | None = None,
    ) -> None:
        state = initial or SelfhoodState.unknown(committed_at=initial_at)
        if state.complete and state.revision <= 0:
            state = state.model_copy(update={"revision": 1})
        self._identity_core = state.identity_core
        self._store = VersionedStateStore(
            VersionedState(
                revision=state.revision,
                committed_at=state.committed_at,
                source_event_ids=state.adaptive_self.source_event_ids,
                causation_id=None,
                value=state,
            )
        )

    @classmethod
    def from_seed(
        cls,
        seed: Mapping[str, Any],
        *,
        initial_at: UTCDateTime,
    ) -> SelfhoodSystem:
        """Load one complete Genesis-created Selfhood document.

        Missing or legacy-shaped documents fail closed.  No Profile/Canon or
        generic persona is consulted to repair them.
        """

        if not isinstance(seed, Mapping):
            raise ValueError("Selfhood seed must be a mapping")
        try:
            state_data = normalize_selfhood_mapping(seed)
            state_data.setdefault("state_schema_version", 1)
            state_data.setdefault("revision", 1)
            state_data.setdefault("committed_at", initial_at)
            state = SelfhoodState.model_validate(state_data)
        except Exception as error:  # noqa: BLE001 - contract boundary
            raise ValueError("invalid Selfhood state") from error
        if state.revision <= 0:
            state = state.model_copy(update={"revision": 1})
        if not state.complete:
            raise ValueError("Selfhood identity_core is incomplete")
        return cls(initial_at=initial_at, initial=state)

    def snapshot(self) -> SelfhoodState:
        """Return the latest committed state."""

        return self._store.snapshot().value

    def prompt_projection(self) -> SelfhoodPromptProjection:
        """Render a bounded natural-language projection without side effects."""

        state = self.snapshot()
        if not state.complete:
            raise ValueError("Selfhood identity_core is incomplete")
        return render_prompt_projection(state)

    def checkpoint(self) -> StateCheckpoint[SelfhoodState]:
        """Return a dedicated diagnostic checkpoint, not Brain continuity."""

        return self._store.checkpoint()

    def restore(self, checkpoint: StateCheckpoint[SelfhoodState]) -> None:
        self.validate_checkpoint(checkpoint)
        self._store.restore(checkpoint)

    def validate_checkpoint(self, checkpoint: StateCheckpoint[SelfhoodState]) -> None:
        if not isinstance(checkpoint.value, SelfhoodState):
            raise ValueError("invalid Selfhood checkpoint")
        if checkpoint.revision < self._store.snapshot().revision:
            raise StateRestoreError("selfhood checkpoint revision is older")
        if not checkpoint.value.complete:
            raise ValueError("Selfhood checkpoint identity_core is incomplete")
        if checkpoint.value.identity_core != self._identity_core:
            raise ValueError("Selfhood identity_core is immutable")

    def propose_update(self, *args, **kwargs):
        """Reject the old broad update API until the Memory proposal is designed."""

        del args, kwargs
        raise SelfhoodGrowthDisabledError(
            "adaptive_self updates are disabled until a MemorySelfhoodProposal contract exists"
        )

    def validate(self, candidate: StateCandidate[SelfhoodState]) -> StateCommitReceipt:
        return StateCommitReceipt(
            candidate_id=candidate.candidate_id,
            status=StateCommitStatus.REJECTED,
            revision=self._store.snapshot().revision,
            reason="selfhood_growth_disabled",
        )

    def commit(self, candidate: StateCandidate[SelfhoodState]) -> StateCommitReceipt:
        return self.validate(candidate)

    def big_five_dict(self) -> dict[str, float]:
        """Return the narrow trait projection needed by Emotion baselines."""

        return self.snapshot().adaptive_self.big_five.model_dump()

    def seed_data(self, *, display_name: str | None = None) -> dict[str, Any]:
        """Return the canonical state shape for diagnostics only."""

        del display_name
        return self.snapshot().model_dump(mode="python")


def render_prompt_projection(state: SelfhoodState) -> SelfhoodPromptProjection:
    """Deterministically map typed Selfhood to model-understandable Chinese."""

    core = state.identity_core
    adaptive = state.adaptive_self
    if not core.complete:
        raise ValueError("cannot render incomplete Selfhood")
    identity = (
        f"我是 {_slot(core.display_name)}，是一只 Elfie；我的正式物种是 "
        f"{_slot(core.species_name)}。"
        f"现在是 ElfieNest 的{_slot(core.resident_role)}。"
    )

    trait_lines = _trait_lines(adaptive.big_five)
    adaptive_lines = ["我的稳定相处与表达方式："]
    adaptive_lines.extend(f"- {line}" for line in trait_lines)
    _append_tendencies(
        adaptive_lines,
        "互动倾向",
        adaptive.interaction_tendency_ids,
        _INTERACTION_LABELS,
    )
    _append_tendencies(
        adaptive_lines,
        "应对与注意倾向",
        adaptive.coping_tendency_ids,
        _COPING_LABELS,
    )
    _append_tendencies(
        adaptive_lines,
        "表达倾向",
        adaptive.expression_tendency_ids,
        _EXPRESSION_LABELS,
    )
    _append_tendencies(adaptive_lines, "个人规范", adaptive.value_ids, _VALUE_LABELS)
    _append_tendencies(
        adaptive_lines,
        "可选口癖",
        adaptive.speech_marker_ids,
        _SPEECH_LABELS,
    )
    return SelfhoodPromptProjection(
        revision=state.revision,
        captured_at=state.committed_at,
        identity_core_text=identity,
        adaptive_self_text="\n".join(adaptive_lines),
    )


def _trait_lines(traits: BigFiveTraits) -> tuple[str, ...]:
    labels = (
        ("开放性", traits.openness, "喜欢探索新事物", "偏好熟悉且有依据的做法"),
        (
            "尽责性",
            traits.conscientiousness,
            "做事通常有条理并重视兑现",
            "会保留余地并避免仓促承诺",
        ),
        (
            "外向性",
            traits.extraversion,
            "更愿意主动交流和分享",
            "更偏好安静、短而清楚的交流",
        ),
        (
            "宜人性",
            traits.agreeableness,
            "通常温和、体谅他人",
            "会保持礼貌并清楚表达界限",
        ),
        (
            "敏感度",
            traits.neuroticism,
            "会留意风险和细微变化",
            "通常能保持平稳，再根据证据调整",
        ),
    )
    lines = []
    for label, value, high, low in labels:
        if value >= 0.66:
            lines.append(f"在{label}上，{high}。")
        elif value <= 0.33:
            lines.append(f"在{label}上，{low}。")
        else:
            lines.append(f"在{label}上，我会根据情境保持适度。")
    return tuple(lines)


def _append_tendencies(
    lines: list[str],
    label: str,
    values: Iterable[str],
    vocabulary: dict[str, str],
) -> None:
    # Only reviewed release vocabulary is rendered.  Unknown/opaque IDs stay
    # internal and cannot become arbitrary model instructions.
    items = tuple(vocabulary[value] for value in values if value in vocabulary)
    if items:
        lines.append(f"{label}：" + "；".join(items) + "。")


def _slot(value: str | None) -> str:
    """Quote a validated data slot so the model sees it as a fact, not a rule."""

    return f"〈{value or '未知'}〉"


_INTERACTION_LABELS = {
    "先观察边缘、声音和可离开的路径": "先观察环境边缘、声音和可离开的路径",
    "再询问陌生设备的具体用途": "会先询问陌生设备的具体用途",
    "先判断声音来源、距离和是否有同伴回应": "会先判断声音来源、距离和同伴回应",
    "再理解通信设备的用途": "会先理解通信设备的用途",
    "先观察边缘、反光、声音和运动轨迹": "会先观察边缘、反光、声音和运动轨迹",
    "接触并记忆后再把设备当作熟悉事物": "接触并记住后再把设备当作熟悉事物",
}
_COPING_LABELS = {
    "环境变化": "留意环境变化",
    "路径与空间边界": "留意路径与空间边界",
    "气味和方向": "留意气味和方向",
    "声音方向": "留意声音方向",
    "脚步与呼唤": "留意脚步与呼唤",
    "群体节奏和协作信号": "留意群体节奏和协作信号",
    "细微声音": "留意细微声音",
    "距离和高低差": "留意距离和高低差",
    "平衡与安静移动": "留意平衡与安静移动",
}
_EXPRESSION_LABELS = {
    "活泼好动": "表达可以活泼一些",
    "安静温顺": "表达通常安静温和",
    "好奇探索": "表达会带着好奇心",
    "胆小害羞": "表达会保留谨慎和害羞",
    "傲娇独立": "表达会保留独立感和轻微的傲娇",
    "完全随机": "表达保留个人差异",
    "独一无二": "表达保留个人差异",
}
_VALUE_LABELS = {
    "尊重自愿选择，不把猜测说成亲历。": "尊重自愿选择，不把猜测说成亲历",
    "不知道时说明不知道，并在真实接触中学习地球。": "不知道时说明不知道，并在真实接触中学习地球",
}
_SPEECH_LABELS = {
    marker: f"偶尔使用“{marker}”作为轻微语气标记"
    for marker in ("哒", "喵", "呢", "啦", "呀")
}


__all__ = (
    "SelfhoodGrowthDisabledError",
    "SelfhoodSystem",
    "render_prompt_projection",
)
