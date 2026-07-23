"""Static contracts for historical turn detail and explicit action preview."""

from pathlib import Path

STATIC_ROOT = Path("devtools/elfie_lab/static")


def test_timeline_uses_typed_decision_text_without_legacy_result_fallback() -> None:
    # Given: the timeline module source.
    source = (STATIC_ROOT / "timeline.js").read_text(encoding="utf-8")

    # When/Then: main copy comes only from typed speech and message projections.
    assert "decision.spoken_texts" in source
    assert "decision.message_texts" in source
    assert "result.speech" not in source
    assert "result.mutter" not in source
    assert "result.reason" not in source


def test_timeline_previews_exactly_one_explicit_action_without_card_bubbling() -> None:
    # Given: the timeline module source.
    source = (STATIC_ROOT / "timeline.js").read_text(encoding="utf-8")

    # When/Then: action controls are explicit and use the injected callback only.
    assert "export function configureTimeline" in source
    assert "event.stopPropagation()" in source
    assert "onPreviewIntent(intent)" in source
    assert "decision.action_intents" in source
    assert "motion_intents" in source
    assert "expression_intents" in source
    assert "if (!intents.length) return;" in source


def test_detail_reads_persisted_history_decision_and_execution_receipts() -> None:
    # Given: the detail module source.
    source = (STATIC_ROOT / "detail.js").read_text(encoding="utf-8")

    # When/Then: historical detail never substitutes live state or legacy result text.
    for field in (
        "turn.state_before",
        "turn.state_after",
        "turn.state_diff",
        "turn.decision",
        "output_receipts",
    ):
        assert field in source
    assert "turn.result.speech" not in source


def test_detail_exposes_current_state_without_reusing_a_historical_turn() -> None:
    # Given: the detail module source.
    source = (STATIC_ROOT / "detail.js").read_text(encoding="utf-8")

    # When/Then: the caller can explicitly render live state before a turn is selected.
    assert "export function renderCurrentState(currentState)" in source
    assert "renderCurrentState(state.session.current_state)" in source
    assert "state.selectedTurn = null" in source
    assert 'textContent = "当前状态"' in source


def test_detail_renders_preview_result_for_selected_intent() -> None:
    # Given: the detail panel and preview bridge sources.
    detail_source = (STATIC_ROOT / "detail.js").read_text(encoding="utf-8")
    result_source = (STATIC_ROOT / "detail-preview.js").read_text(encoding="utf-8")
    profile_source = (STATIC_ROOT / "profile.js").read_text(encoding="utf-8")

    # When/Then: the typed playback result is retained in the right panel.
    assert "recordPreviewResult" in result_source
    assert "动作回放" in result_source
    assert "previewResultSection(turn)" in detail_source
    assert "onPreviewResult" in profile_source
    assert "completePreviewRequest(message.request_id)" in profile_source
