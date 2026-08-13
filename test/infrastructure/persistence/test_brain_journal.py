"""SQLite persistence contract for the append-only Brain journal."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from elfie.brain.journal import BrainJournalEntry, BrainJournalKind
from elfie.brain.workspace.contracts import (
    PerceptionEvent,
    PhysicalModality,
    PhysicalPayload,
    WorkspacePendingWrite,
    WorkspacePersistentState,
    WorkspaceSeenEvent,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MessageMeta,
    TraceId,
    TurnId,
)
from infrastructure.persistence.brain_journal import SQLiteBrainJournalAdapter

NOW = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)


def _entry(*, detail: str = "started") -> BrainJournalEntry:
    return BrainJournalEntry(
        entry_id=EventId(f"entry-{detail}"),
        elfie_id=ElfieId("elfie-journal"),
        kind=BrainJournalKind.RUN_STARTED,
        occurred_at=NOW,
        idempotency_key="run:turn-1:started",
        turn_id=TurnId("turn-1"),
        detail=detail,
    )


def test_journal_reopens_in_append_order_and_deduplicates(tmp_path: Path) -> None:
    path = tmp_path / "brain" / "journal.sqlite"
    first = SQLiteBrainJournalAdapter(path)
    try:
        entry = _entry()
        assert first.append(entry) is True
        assert first.append(entry) is False
    finally:
        first.close()

    reopened = SQLiteBrainJournalAdapter(path)
    try:
        assert reopened.entries() == (_entry(),)
    finally:
        reopened.close()


def test_journal_rejects_conflicting_idempotency_payload(tmp_path: Path) -> None:
    store = SQLiteBrainJournalAdapter(tmp_path / "brain" / "journal.sqlite")
    try:
        store.append(_entry())
        with pytest.raises(ValueError, match="idempotency conflict"):
            store.append(_entry(detail="different"))
    finally:
        store.close()


def test_workspace_pending_cut_reopens_atomically(tmp_path: Path) -> None:
    path = tmp_path / "brain" / "journal.sqlite"
    write = PerceptionEvent(
        meta=MessageMeta(
            event_id=EventId("pending-event"),
            elfie_id=ElfieId("elfie-journal"),
            source=ActorRef(actor_id=ActorId("sensor"), source_kind="test"),
            occurred_at=NOW,
            received_at=NOW,
            trace_id=TraceId("pending-trace"),
        ),
        payload=PhysicalPayload(
            type="physical",
            body_id="body-1",
            modality=PhysicalModality.UTTERANCE,
            content="hello",
        ),
        salience=0.7,
    )
    first = SQLiteBrainJournalAdapter(path)
    try:
        first.save_workspace_state(
            WorkspacePersistentState(
                next_ingest_seq=7,
                pending_writes=(WorkspacePendingWrite(ingest_seq=7, write=write),),
                seen_events=(
                    WorkspaceSeenEvent(
                        event_id=write.meta.event_id,
                        ingest_seq=7,
                    ),
                ),
            )
        )
    finally:
        first.close()

    reopened = SQLiteBrainJournalAdapter(path)
    try:
        state = reopened.load_workspace_state()
        assert state.pending_writes[0].write == write
        assert state.next_ingest_seq == 7
        assert state.seen_events[0].event_id == write.meta.event_id
        reopened.save_workspace_state(WorkspacePersistentState())
        assert reopened.load_workspace_state() == WorkspacePersistentState()
    finally:
        reopened.close()
