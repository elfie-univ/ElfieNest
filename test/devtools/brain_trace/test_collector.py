import json

import pytest

from devtools.brain_trace import (
    BrainTraceValidationError,
    collect_brain_trace,
    list_brain_trace_sources,
)
from devtools.elfie_lab.model_execution_adapters import redact_value
from devtools.elfie_lab.schemas import StimulusBundle
from devtools.elfie_lab.session import ElfieLabSession
from devtools.elfie_lab.storage import ElfieLabStorage
from devtools.elfie_lab.turn_summary import model_call_summary
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _workspace_bytes(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


ENVELOPE_EVENT_KEYS = {
    "schema_version",
    "boundary",
    "kind",
    "sequence",
    "captured_at",
    "turn_id",
    "frame_id",
    "cause_event_ids",
    "duration_ms",
    "status",
    "error",
    "payload",
}


def test_collects_full_mock_chain_without_changing_lab_summary(tmp_path):
    storage = ElfieLabStorage(str(tmp_path / "lab"))
    spec = storage.create_elfie("采集测试")
    source_before = _workspace_bytes(storage.elfie_dir(spec.elfie_id))

    result = collect_brain_trace(
        elfie_id=spec.elfie_id,
        messages=(
            StimulusBundle(message="你好"),
            StimulusBundle(message="你还记得我的偏好吗？"),
        ),
        memory_mode="mock",
        model_mode="mock",
        data_dir=storage.root,
        output_root=tmp_path / "out",
    )

    assert result.status == "completed"
    manifest = json.loads((result.artifact_dir / "manifest.json").read_text())
    assert manifest["schema_version"] == "brain-trace.v1"
    assert manifest["memory"]["mode"] == "mock"
    assert manifest["model"]["mode"] == "mock"
    events = _read_jsonl(result.artifact_dir / "events.jsonl")
    records = _read_jsonl(result.artifact_dir / "collector_records.jsonl")
    turns = _read_jsonl(result.artifact_dir / "turns.jsonl")
    # Acceptance: every events.jsonl line is a named envelope event dump
    # (boundary/kind/payload present); bare stage dicts are gone.
    assert events
    assert all(set(event) == ENVELOPE_EVENT_KEYS for event in events)
    assert all(
        isinstance(event["boundary"], str)
        and event["boundary"]
        and isinstance(event["kind"], str)
        and event["kind"]
        and isinstance(event["payload"], dict)
        for event in events
    )
    # Collector-diagnostic records live in their own stream and carry no
    # envelope fields.
    assert records
    assert all(event["kind"] not in ENVELOPE_EVENT_KEYS for event in records)
    assert all("boundary" not in record for record in records)
    assert manifest["event_count"] == len(events)
    assert manifest["collector_record_count"] == len(records)
    assert len(turns) == 2
    assert all(turn["context_events"] for turn in turns)
    assert all(
        event["boundary"] == "reasoning.context_engine"
        for turn in turns
        for event in turn["context_events"]
    )
    assert all(
        event["kind"] in {"compiled_context", "context_trimmed"}
        for turn in turns
        for event in turn["context_events"]
    )
    assert all(
        event["duration_ms"] is not None and event["duration_ms"] >= 0
        for turn in turns
        for event in turn["context_events"]
        if event["kind"] == "compiled_context"
    )
    assert all("model_execution_events" in turn for turn in turns)
    assert all(turn["model_calls"] for turn in turns)
    assert all(turn["memory_events"]["events"] for turn in turns)
    assert all(turn["memory_events"]["collector_records"] for turn in turns)
    assert all("analysis" not in turn for turn in turns)
    # Acceptance: recall-selection events keep their envelope kinds instead
    # of collapsing into the boundary string.
    selection_kinds = {
        event["kind"]
        for event in events
        if event["boundary"] == "memory.recall.selection"
    }
    # Empty mock memory: a selection summary fires per recall, but nothing
    # is scored until the fixture test seeds recallable material.
    assert selection_kinds == {"selection_summary"}
    summaries = [
        event["payload"] for event in events if event["kind"] == "selection_summary"
    ]
    assert all(
        isinstance(item["candidates_seen"], int) and item["candidates_seen"] >= 0
        for item in summaries
    )
    # Acceptance: memory status/query/evidence stay derivable from the named
    # envelope payloads.
    recall_summaries = [turn["memory_recall_summary"] for turn in turns]
    assert all(summary["turn_opened"] is not None for summary in recall_summaries)
    assert any(
        recall["result"] is not None and recall["result"]["status"]
        for summary in recall_summaries
        for recall in summary["recalls"]
    )
    assert _workspace_bytes(storage.elfie_dir(spec.elfie_id)) == source_before

    # The public Lab projection remains intentionally redacted and compact.
    assert "response" not in model_call_summary(turns[0]["model_calls"][0])


def test_mock_memory_fixture_is_seeded_through_typed_store(tmp_path):
    storage = ElfieLabStorage(str(tmp_path / "lab"))
    spec = storage.create_elfie("记忆夹具")
    fixture = tmp_path / "memory.json"
    fixture.write_text(
        json.dumps(
            {
                "episodes": [
                    {
                        "episode_id": "fixture-episode",
                        "idempotency_key": "fixture-episode",
                        "occurred_from": "2026-01-01T00:00:00+00:00",
                        "content_text": "主人之前说过自己的偏好是喜欢草莓",
                        "importance": 0.8,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = collect_brain_trace(
        elfie_id=spec.elfie_id,
        messages=(StimulusBundle(message="你还记得我的偏好吗？"),),
        memory_mode="mock",
        model_mode="mock",
        data_dir=storage.root,
        output_root=tmp_path / "out",
        memory_fixture=fixture,
    )

    turn = _read_jsonl(result.artifact_dir / "turns.jsonl")[0]
    assert [item["episode_id"] for item in turn["memory_after"]["episodes"]] == [
        "fixture-episode"
    ]
    records = _read_jsonl(result.artifact_dir / "collector_records.jsonl")
    assert any(record["kind"] == "memory_fixture" for record in records)
    assert any(
        record["kind"] == "memory_store"
        and record["payload"]["method"] == "record_episode"
        for record in records
    )
    events = _read_jsonl(result.artifact_dir / "events.jsonl")
    # Acceptance: recall-selection events keep their envelope kinds instead
    # of collapsing into the boundary string.
    selection = [
        event for event in events if event["boundary"] == "memory.recall.selection"
    ]
    assert {"candidate_scored", "selection_summary"} == {
        event["kind"] for event in selection
    }
    scored = [event for event in selection if event["kind"] == "candidate_scored"]
    assert scored and all(
        event["payload"]["candidate_id"] == "fixture-episode"
        and event["payload"]["candidate_kind"] == "episode"
        and event["payload"]["matched_terms"]
        and isinstance(event["payload"]["score"], float)
        for event in scored
    )
    # The recall summary derives status/query/evidence from the named
    # envelope payloads: the scored episode reaches the turn's bundle.
    summary = turn["memory_recall_summary"]
    assert summary["turn_opened"]["query"] == "你还记得我的偏好吗？"
    recalled = [
        recall
        for recall in summary["recalls"]
        if recall["result"] is not None and recall["result"]["status"] == "recalled"
    ]
    assert recalled
    assert recalled[0]["result"]["bundle"]["episode_ids"] == ["fixture-episode"]


def test_real_model_mode_never_silently_falls_back(tmp_path):
    storage = ElfieLabStorage(str(tmp_path / "lab"))
    spec = storage.create_elfie("模式校验")

    with pytest.raises(BrainTraceValidationError, match="food_key"):
        collect_brain_trace(
            elfie_id=spec.elfie_id,
            messages=(StimulusBundle(message="测试"),),
            memory_mode="real",
            model_mode="real",
            data_dir=storage.root,
            output_root=tmp_path / "out",
        )


def test_source_listing_contains_elfie_without_model_secrets(tmp_path):
    storage = ElfieLabStorage(str(tmp_path / "lab"))
    spec = storage.create_elfie("列表测试")

    payload = list_brain_trace_sources(storage.root)

    assert payload["elfies"][0]["elfie_id"] == spec.elfie_id
    assert "api_key" not in json.dumps(payload, ensure_ascii=False)


def test_collect_run_session_seam_works_without_observation_sink(tmp_path):
    storage = ElfieLabStorage(str(tmp_path / "lab"))
    spec = storage.create_elfie("无观测采集")
    memory_store = SQLiteMemoryStoreAdapter.in_memory(elfie_id=spec.elfie_id)
    session = ElfieLabSession(
        storage.get_elfie(spec.elfie_id),
        storage,
        memory_store=memory_store,
        observation_sink=None,
    )
    try:
        turn = session.run_turn(StimulusBundle(message="你好"), "mock")
    finally:
        session.close()
        memory_store.close()

    assert turn["result"]["success"] is True


def test_trace_redaction_handles_nested_credentials():
    api_key = "sk-" + "live-secret-value-12345"
    authorization = "Bearer " + "token-value-123456"
    value = redact_value(
        {
            "apiKey": api_key,
            "nested": {"Authorization": authorization},
            "message": "safe text",
        }
    )

    assert value == {
        "apiKey": "<redacted>",
        "nested": {"Authorization": "<redacted>"},
        "message": "safe text",
    }
