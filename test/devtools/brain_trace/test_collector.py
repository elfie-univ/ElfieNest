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
    turns = _read_jsonl(result.artifact_dir / "turns.jsonl")
    assert events and all(isinstance(item, dict) for item in events)
    assert len(turns) == 2
    assert all(turn["context_events"] for turn in turns)
    assert all(
        event["payload"]["duration_ms"] >= 0
        for turn in turns
        for event in turn["context_events"]
    )
    assert all("model_execution_events" in turn for turn in turns)
    assert all(turn["model_calls"] for turn in turns)
    assert all(turn["memory_events"]["events"] for turn in turns)
    assert all("analysis" not in turn for turn in turns)
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
                        "content_text": "主人喜欢草莓",
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
    assert any(
        event["kind"] == "memory_fixture"
        for event in _read_jsonl(result.artifact_dir / "events.jsonl")
    )


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
