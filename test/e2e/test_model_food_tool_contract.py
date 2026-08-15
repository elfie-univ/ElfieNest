from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.features.configuration.food import (
    FoodPlanner,
    StoredFoodPackage,
    StoredModelEvidence,
)
from elfie.brain.reasoning.food_port import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    NoAvailableFoodError,
)
from infrastructure.models.model_execution_agent import ModelExecutionAgent
from infrastructure.models.model_execution_contracts import (
    StructuredGenerationMode,
    StructuredModelExecutionRequest,
)
from infrastructure.models.model_execution_observations import (
    get_model_execution_observer,
)
from infrastructure.persistence.configuration.runtime_settings import (
    write_runtime_settings,
    write_tool_settings,
)
from infrastructure.persistence.configuration.secrets import set_connection_secret
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.food_evidence import (
    query_model_evidence,
    record_model_evidence,
)
from infrastructure.persistence.layout.data_home import (
    get_provider_config_path,
)
from infrastructure.persistence.model_execution_config import (
    load_model_execution_config,
)
from infrastructure.persistence.nest_db.store import get_db, init_db
from infrastructure.persistence.provider_connections import (
    ProviderConnectionStore,
    ProviderModelRecord,
)
from infrastructure.persistence.reports.report_repository import ReportRepository
from infrastructure.tools import ToolPortAdapter
from test.support.model_execution_agent import model_execution_agent_ports


def _evidence(model: str, capabilities: set[str], *, local: bool = False):
    return StoredModelEvidence(
        reference=model,
        display_name=model,
        capabilities=frozenset(capabilities),
        verified=True,
        local=local,
        tool_test_passed="tools" in capabilities,
        observed_at=datetime.now(timezone.utc).isoformat(),
    )


def test_clean_home_provider_food_elfie_tool_and_emergency_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    provider_store = ProviderConnectionStore()
    local = provider_store.create(
        catalog_id="ollama",
        alias="Local",
        models=(
            ProviderModelRecord("local-main"),
            ProviderModelRecord("local-reason", supports_reasoning=True),
        ),
    )
    remote_a = provider_store.create(
        catalog_id="custom_openai",
        alias="Remote A",
        api_base="https://a.example/v1",
        api_mode="chat_completions",
        models=(
            ProviderModelRecord("main"),
            ProviderModelRecord("reason", supports_reasoning=True),
            ProviderModelRecord("tool", supports_tools=True),
            ProviderModelRecord("backup"),
        ),
    )
    remote_b = provider_store.create(
        catalog_id="custom_openai",
        alias="Remote B",
        api_base="https://b.example/v1",
        api_mode="chat_completions",
        models=(ProviderModelRecord("main"),),
    )
    assert remote_a.connection_id == "custom_openai_0001"
    assert remote_b.connection_id == "custom_openai_0002"
    set_connection_secret(remote_a.connection_id, "test-secret-a")
    set_connection_secret(remote_b.connection_id, "test-secret-b")

    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    food_repository = SQLiteFoodAdapter(db_path)
    initial = food_repository.list_packages()
    assert [item.food_id for item in initial] == [
        FOOD_EMERGENCY_ID,
        FOOD_COMMON_ID,
    ]

    refs = {
        "local": f"{local.connection_id}/local-main",
        "main": f"{remote_a.connection_id}/main",
        "reason": f"{remote_a.connection_id}/reason",
        "tool": f"{remote_a.connection_id}/tool",
        "backup": f"{remote_a.connection_id}/backup",
    }
    record_model_evidence(
        [
            _evidence(refs["local"], {"text"}, local=True),
            _evidence(refs["main"], {"text"}),
            _evidence(refs["reason"], {"text", "reasoning"}),
            _evidence(refs["tool"], {"text", "tools"}),
            _evidence(refs["backup"], {"text"}),
        ],
        scope="contract-acceptance",
        trigger="test",
    )
    evidence = tuple(query_model_evidence().values())

    emergency_preview = FoodPlanner().propose_package(
        next(item for item in initial if item.food_id == FOOD_EMERGENCY_ID),
        evidence,
        connection_ids=(local.connection_id,),
        local_first=True,
        allow_remote=False,
    )
    common_preview = FoodPlanner().propose_package(
        next(item for item in initial if item.food_id == FOOD_COMMON_ID),
        evidence,
        connection_ids=(remote_a.connection_id,),
    )
    assert emergency_preview.package.primary_model == refs["local"]
    assert common_preview.package.primary_model is not None
    assert common_preview.package.primary_model.startswith(f"{remote_a.connection_id}/")
    assert emergency_preview.changes and common_preview.changes

    custom_id = "food_custom"
    packages = (
        replace(emergency_preview.package, enabled=True),
        StoredFoodPackage(
            FOOD_COMMON_ID,
            "Common food",
            system_role="common",
            enabled=True,
            primary_model=refs["main"],
            reasoning_model=refs["reason"],
            tool_model=refs["tool"],
            fallback_model=refs["backup"],
        ),
        StoredFoodPackage(
            custom_id,
            "Private food",
            enabled=True,
            primary_model=refs["main"],
        ),
    )
    for package in packages:
        if food_repository.get_package(package.food_id) is None:
            food_repository.create_package(package)
        else:
            food_repository.update_package(package)
    with get_db(db_path) as connection:
        user_id = int(
            connection.execute(
                """
                INSERT INTO users (account_id, password_hash, role)
                VALUES ('alice', 'test', 'user')
                """
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO elfies (elfie_id, name, owner_user_id, species, adopted_at, status, main_food_id)
            VALUES ('00000001', 'Test Elfie', ?, 'default', CURRENT_TIMESTAMP, 'online', ?)
            """,
            (user_id, custom_id),
        )
        connection.commit()
    workspace = tmp_path / "elfies" / "00000001"
    workspace.mkdir(parents=True)
    (workspace / "note.txt").write_text("knowledge " * 3000, encoding="utf-8")
    write_runtime_settings({})
    write_tool_settings(
        {
            "web_search": {"enabled": False},
            "local_file": {"enabled": True},
        }
    )
    runtime_config = load_model_execution_config()
    tool_port = ToolPortAdapter.from_model_execution_config(
        runtime_config,
        observation_port=get_model_execution_observer(),
        workspace_resolver=lambda scope_id: (
            workspace if scope_id == "00000001" else None
        ),
    )
    agent = ModelExecutionAgent(
        runtime_config,
        ports=model_execution_agent_ports(),
        live_reload=True,
        food_catalog_repository=food_repository,
        tool_port=tool_port,
    )
    calls: list[str] = []
    structured_probe = {"pending": False}

    def fake_model_call(provider, model, messages, *_args, **_kwargs):
        calls.append(model)
        if model == "reason":
            raise RuntimeError("reasoning unavailable")
        if model == "main" and structured_probe["pending"]:
            if "【本地文件内容】" not in messages[-1]["content"]:
                return "[READ_FILE]note.txt[/READ_FILE]"
            structured_probe["pending"] = False
            return "ok:structured"
        if model == "tool" and "【本地文件" not in messages[-1]["content"]:
            return "[READ_FILE]note.txt[/READ_FILE]"
        return f"ok:{model}"

    monkeypatch.setattr(agent, "_call_food_llm_api", fake_model_call)
    primary = agent.run_with_food(prompt="hello", food_key=FOOD_COMMON_ID)
    reasoning = agent.run_with_food(
        prompt="reason",
        food_key=FOOD_COMMON_ID,
        semantic_role="reasoning",
    )
    fallback = agent.run_with_food(
        prompt="fallback",
        food_key=FOOD_COMMON_ID,
        semantic_role="fallback",
    )
    tool = agent.run_with_food(
        prompt="read the note",
        food_key=FOOD_COMMON_ID,
        elfie_id="00000001",
        semantic_role="tool",
        allowed_skills=["local_file"],
    )
    assert primary.actual_model == refs["main"]
    assert reasoning.actual_model == refs["backup"]
    assert reasoning.execution_stage == "fallback"
    assert fallback.actual_model == refs["backup"]
    assert tool.text == "ok:tool"
    assert calls.count("tool") >= 2

    structured_probe["pending"] = True
    structured = agent.generate_structured(
        StructuredModelExecutionRequest(
            prompt="structured read",
            messages=(),
            response_schema_name="answer",
            response_schema={"type": "object"},
            selected_mode=StructuredGenerationMode.JSON_TEXT,
            allowed_tools=("local_file",),
            food_key=FOOD_COMMON_ID,
            scope_id="00000001",
        )
    )
    assert structured.text == "ok:structured"

    provider_bytes = get_provider_config_path().read_bytes()
    food_snapshot = food_repository.list_packages()
    write_runtime_settings({})
    write_tool_settings(
        {
            "web_search": {"enabled": False},
            "local_file": {"enabled": True},
        }
    )
    assert get_provider_config_path().read_bytes() == provider_bytes
    assert food_repository.list_packages() == food_snapshot

    provider_store.replace(replace(remote_a, enabled=False))
    emergency_result = agent.run_with_food(
        prompt="use emergency",
        food_key=FOOD_COMMON_ID,
    )
    assert emergency_result.food_used == FOOD_EMERGENCY_ID
    assert emergency_result.actual_model == refs["local"]

    provider_store.replace(remote_a)
    disabled_emergency = replace(
        food_repository.get_package(FOOD_EMERGENCY_ID),
        enabled=False,
    )
    food_repository.update_package(disabled_emergency)
    provider_store.replace(replace(remote_a, enabled=False))
    with pytest.raises(NoAvailableFoodError, match="no_available_food"):
        agent.run_with_food(prompt="nothing left", food_key=FOOD_COMMON_ID)

    reports = ReportRepository()
    kinds = {item.subject_kind for item in reports.current()}
    assert {"model", "food", "fallback", "tool"} <= kinds
    tool_observation = reports.latest("tool", "local_file_read")
    assert tool_observation is not None
    assert tool_observation.details["truncated"] is True
    assert tool_observation.details["retained_bytes"] <= 16000
    assert reports.as_of(datetime.now(timezone.utc).isoformat())
    complete_runs = [
        item.run_id
        for item in reports.current()
        if reports.get_run(item.run_id).status == "complete"
    ]
    assert complete_runs
    assert reports.observations_for_run(complete_runs[-1])
