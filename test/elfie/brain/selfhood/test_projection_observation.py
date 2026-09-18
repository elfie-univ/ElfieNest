"""The frozen Selfhood projection read per Turn emits one read-only record."""

from __future__ import annotations

from elfie.brain.observation import ObservationStatus
from elfie.brain.selfhood.contracts import SelfhoodPromptProjection
from test.elfie.brain.reasoning.test_run_controller_observation import (
    NOW,
    _build,
    _CollectorSink,
    _controller,
    _frame,
    _StaticContextSource,
)

CUSTOM_PROJECTION = SelfhoodPromptProjection(
    revision=9,
    captured_at=NOW,
    identity_core_text="我是阿狸，正式物种是赤狐，现在是 ElfieNest 的首批居民。",
    adaptive_self_text="遇到冲突先降温，再用平静的语气说出事实。",
)


def test_projection_snapshot_records_the_exact_projection_read() -> None:
    sink = _CollectorSink()
    controller = _controller(sink, _StaticContextSource(selfhood=CUSTOM_PROJECTION))

    _build(controller, _frame(frame_id="frame-selfhood", content="在吗"))

    projections = sink.of("selfhood", "projection_snapshot")
    assert len(projections) == 1
    event = projections[0]
    assert event.boundary == "selfhood"
    assert event.status is ObservationStatus.completed
    assert event.turn_id == "turn-run-ctrl"
    assert event.frame_id == "frame-selfhood"
    payload = event.payload
    assert payload.revision == 9
    assert payload.projected_at == CUSTOM_PROJECTION.captured_at
    assert payload.identity_core_text == CUSTOM_PROJECTION.identity_core_text
    assert payload.adaptive_self_text == CUSTOM_PROJECTION.adaptive_self_text


def test_projection_record_is_read_only_across_turns() -> None:
    sink = _CollectorSink()
    controller = _controller(sink, _StaticContextSource(selfhood=CUSTOM_PROJECTION))

    for index in range(2):
        _build(controller, _frame(frame_id=f"frame-selfhood-{index}", content="嗯"))

    projections = sink.of("selfhood", "projection_snapshot")
    assert len(projections) == 2
    assert [event.frame_id for event in projections] == [
        "frame-selfhood-0",
        "frame-selfhood-1",
    ]
    assert CUSTOM_PROJECTION.revision == 9
    assert CUSTOM_PROJECTION.captured_at == NOW
