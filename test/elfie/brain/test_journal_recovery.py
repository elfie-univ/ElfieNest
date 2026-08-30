"""Restart recovery across durable Activity and Brain journal stores."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Condition
from time import monotonic

from pydantic import TypeAdapter

from elfie import ElfieFactory
from elfie.brain.activity.system import (
    ActivityDraft,
    ActivityState,
    ActivityStep,
    ActivityStepKind,
    ExecutionScope,
)
from elfie.brain.continuity import BrainContinuityCheckpoint
from elfie.brain.journal import BrainJournalKind
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationResult,
    StructuredOutputMode,
)
from elfie.communication import CommunicationHub
from elfie.factory import ElfieAssembly
from elfie.message_types import ActivityId, EventId
from elfie.profile import create_visual_profile
from infrastructure.persistence.activity import SQLiteActivityStoreAdapter
from infrastructure.persistence.brain_journal import SQLiteBrainJournalAdapter
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from test.elfie.test_cognitive_lifecycle import RecordingChannel, _owner_message

NOW = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)


class FailingModel:
    """Recovery is synchronous and must not depend on a successful model call."""

    def capabilities(self) -> ModelGenerationCapabilities:
        return ModelGenerationCapabilities(
            provider="test",
            model_key="test/unavailable",
            supports_json_schema=True,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=128,
        )

    def generate(self, request):
        del request
        raise RuntimeError("model unavailable")

    def abandon(self, request) -> None:
        del request


class RecordingReplyModel:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.requests = []
        self._condition = Condition()

    def capabilities(self) -> ModelGenerationCapabilities:
        return ModelGenerationCapabilities(
            provider="test",
            model_key="test/plain",
            supports_json_schema=True,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=512,
        )

    def generate(self, request) -> ModelGenerationResult:
        with self._condition:
            self.requests.append(request)
            self._condition.notify_all()
        return ModelGenerationResult(
            text=self.reply,
            selected_mode=StructuredOutputMode.PLAIN_TEXT,
            provider="test",
            model_key="test/plain",
        )

    def abandon(self, request) -> None:
        del request

    def wait_for_prompt(self, text: str, *, timeout: float):
        deadline = monotonic() + timeout
        with self._condition:
            while True:
                matching = tuple(
                    request for request in self.requests if text in request.user_prompt
                )
                if matching:
                    return matching[-1]
                remaining = deadline - monotonic()
                if remaining <= 0 or not self._condition.wait(remaining):
                    raise TimeoutError(f"model prompt did not contain: {text}")


def _running_activity(store: SQLiteActivityStoreAdapter) -> None:
    draft = ActivityDraft(
        activity_id=ActivityId("activity-running"),
        goal="整理已知事实",
        success_criteria="内部步骤完成",
        steps=(
            ActivityStep(
                step_id=EventId("activity-running:step-1"),
                ordinal=0,
                kind=ActivityStepKind.INTERNAL,
                operation="review_context",
                deadline=NOW + timedelta(hours=1),
                scope=ExecutionScope(
                    external_domain=None,
                    capability_revision=0,
                    allowed_operations=("review_context",),
                    expires_at=NOW + timedelta(hours=1),
                ),
            ),
        ),
        cause_event_ids=(EventId("activity-running:cause"),),
        idempotency_key="activity-running:create",
        created_at=NOW,
        deadline=NOW + timedelta(hours=1),
    )
    preflight = store.preflight(draft, now=NOW)
    record = store.commit(draft, preflight=preflight)
    assert record.state is ActivityState.RUNNING


def test_restart_pauses_inflight_activity_and_journals_uncertainty(
    tmp_path: Path,
) -> None:
    activity_path = tmp_path / "activity" / "activity.sqlite"
    activity_path.parent.mkdir(parents=True)
    initial = SQLiteActivityStoreAdapter(activity_path)
    _running_activity(initial)
    initial.close()

    journal_path = tmp_path / "brain" / "journal.sqlite"
    elfie = ElfieFactory().restore(
        ElfieAssembly(
            profile=create_visual_profile(
                elfie_id="elfie-recovery",
                display_name="恢复精灵",
                species_id="fox",
                seed=7,
            ),
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            activity_store=SQLiteActivityStoreAdapter(activity_path),
            journal_store=SQLiteBrainJournalAdapter(journal_path),
            model_port=FailingModel(),
        )
    )
    try:
        elfie.start()
        record = elfie.activities()[0]
        assert record.state is ActivityState.PAUSED
        assert record.revision == 1
        activity_entries = [
            entry
            for entry in elfie.brain_journal()
            if entry.kind is BrainJournalKind.ACTIVITY_STATE
        ]
        assert activity_entries[-1].status == ActivityState.PAUSED.value
        assert activity_entries[-1].detail == "restart_reconciliation_required"
    finally:
        elfie.stop()
        elfie.join()
        elfie.close_resources()

    reopened = SQLiteBrainJournalAdapter(journal_path)
    try:
        assert any(
            entry.kind is BrainJournalKind.ACTIVITY_STATE
            and entry.status == ActivityState.PAUSED.value
            for entry in reopened.entries()
        )
    finally:
        reopened.close()


def test_restart_restores_durable_continuity_and_cognitive_clock(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "brain" / "journal.sqlite"
    profile = create_visual_profile(
        elfie_id="elfie-continuity",
        display_name="连续精灵",
        species_id="fox",
        seed=11,
    )
    first = ElfieFactory().restore(
        ElfieAssembly(
            profile=profile,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            journal_store=SQLiteBrainJournalAdapter(journal_path),
            model_port=FailingModel(),
        )
    )
    first.start()
    first.advance_clock(12.0)
    first.stop()
    first.join()
    expected = first.continuity_checkpoint()
    checkpoint_adapter = TypeAdapter(BrainContinuityCheckpoint)
    legacy_payload = json.loads(checkpoint_adapter.dump_json(expected))
    legacy_payload.pop("conversation")
    assert (
        checkpoint_adapter.validate_json(
            json.dumps(legacy_payload)
        ).conversation.threads
        == ()
    )
    first.close_resources()

    restored = ElfieFactory().restore(
        ElfieAssembly(
            profile=profile,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            journal_store=SQLiteBrainJournalAdapter(journal_path),
            model_port=FailingModel(),
        )
    )
    try:
        restored.start()
        actual = restored.continuity_checkpoint()
        assert actual.energy == expected.energy
        assert actual.orientation == expected.orientation
        assert restored.elapsed_time == expected.captured_at.timestamp()

        restored.advance_clock(1.0)
        restored.stop()
        restored.join()
        assert restored.elapsed_time == expected.captured_at.timestamp() + 1.0
    finally:
        restored.stop()
        restored.join()
        restored.close_resources()


def test_restart_restores_alternating_owner_conversation_context(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "brain" / "journal.sqlite"
    memory_path = tmp_path / "memory" / "knowledge.sqlite"
    memory_path.parent.mkdir(parents=True)
    profile = create_visual_profile(
        elfie_id="elfie-conversation",
        display_name="连续对话精灵",
        species_id="fox",
        seed=17,
    )
    first_hub = CommunicationHub("elfie-conversation")
    first_hub.register_channel(RecordingChannel(), connect=True)
    first_model = RecordingReplyModel("我记住了，你喜欢蓝色。")
    first = ElfieFactory().restore(
        ElfieAssembly(
            profile=profile,
            memory_store=SQLiteMemoryStoreAdapter(memory_path),
            journal_store=SQLiteBrainJournalAdapter(journal_path),
            communication=first_hub,
            model_port=first_model,
        )
    )
    first.start()
    first.receive_communication_envelope(
        _owner_message(
            first.cognitive_datetime,
            event_id="owner-blue",
            text="我喜欢蓝色。",
            elfie_id="elfie-conversation",
        )
    )
    first.advance_clock(0.5)
    first.wait_for_outcome_count(1, timeout=1)
    first_turn = first.turn_outcomes()[0]
    first.wait_for_output(first_turn.turn_id, timeout=1)
    first.stop()
    first.join()
    first.close_resources()

    restored_hub = CommunicationHub("elfie-conversation")
    restored_hub.register_channel(RecordingChannel(), connect=True)
    restored_model = RecordingReplyModel("你喜欢蓝色。")
    restored = ElfieFactory().restore(
        ElfieAssembly(
            profile=profile,
            memory_store=SQLiteMemoryStoreAdapter(memory_path),
            journal_store=SQLiteBrainJournalAdapter(journal_path),
            communication=restored_hub,
            model_port=restored_model,
        )
    )
    try:
        restored.start()
        restored.receive_communication_envelope(
            _owner_message(
                restored.cognitive_datetime,
                event_id="owner-recall",
                text="我刚才说喜欢什么颜色？",
                elfie_id="elfie-conversation",
            )
        )
        restored.advance_clock(0.5)
        request = restored_model.wait_for_prompt(
            "我刚才说喜欢什么颜色？",
            timeout=2,
        )

        prompt = request.user_prompt
        assert "owner: 我喜欢蓝色。" in prompt
        assert "elfie: 我记住了，你喜欢蓝色。" in prompt
        assert prompt.count("我刚才说喜欢什么颜色？") == 1
    finally:
        restored.stop()
        restored.join()
        restored.close_resources()
