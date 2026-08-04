from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.evidence import query_model_evidence, record_model_evidence
from ai_runtime.food.executor import NoAvailableFoodError
from ai_runtime.food.models import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    FoodPackage,
    ModelAssignment,
)
from ai_runtime.food.planner import FoodPlanner, ModelEvidence
from ai_runtime.food.store import FoodCatalog
from ai_runtime.gateway.agent import RuntimeAgent
from ai_runtime.storage.data_home import (
    get_provider_config_path,
)
from ai_runtime.storage.provider_connections import (
    ProviderConnectionStore,
    ProviderModelRecord,
)
from ai_runtime.storage.report_repository import ReportRepository
from ai_runtime.storage.runtime_settings import write_runtime_settings
from ai_runtime.storage.secrets import set_connection_secret
from app.infrastructure.persistence.food_packages import SQLiteFoodPackageRepository
from app.infrastructure.persistence.store import get_db, init_db


def _evidence(model: str, capabilities: set[str], *, local: bool = False):
    return ModelEvidence(
        model=model,
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
    food_repository = SQLiteFoodPackageRepository(db_path)
    initial = food_repository.load()
    assert [item.key for item in initial.ordered_packages()] == [
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
        initial.packages[FOOD_EMERGENCY_ID],
        evidence,
        connection_ids=(local.connection_id,),
        local_first=True,
        allow_remote=False,
    )
    common_preview = FoodPlanner().propose_package(
        initial.packages[FOOD_COMMON_ID],
        evidence,
        connection_ids=(remote_a.connection_id,),
    )
    assert emergency_preview.package.primary.model == refs["local"]
    assert common_preview.package.primary.model.startswith(f"{remote_a.connection_id}/")
    assert emergency_preview.has_changes and common_preview.has_changes

    custom_id = "food_custom"
    catalog = FoodCatalog(
        packages={
            FOOD_EMERGENCY_ID: replace(
                emergency_preview.package,
                enabled=True,
            ),
            FOOD_COMMON_ID: FoodPackage(
                FOOD_COMMON_ID,
                "Common food",
                system_role="common",
                enabled=True,
                primary=ModelAssignment(refs["main"]),
                reasoning=ModelAssignment(refs["reason"]),
                tool=ModelAssignment(refs["tool"]),
                fallback=ModelAssignment(refs["backup"]),
            ),
            custom_id: FoodPackage(
                custom_id,
                "Private food",
                enabled=True,
                primary=ModelAssignment(refs["main"]),
            ),
        }
    )
    for package in catalog.packages.values():
        if food_repository.get(package.key) is None:
            food_repository.create(package)
        else:
            food_repository.update(package)
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
    write_runtime_settings(
        {
            "runtime_policy": {
                "tools": {
                    "web_search": {"enabled": False},
                    "local_file": {"enabled": True},
                }
            }
        }
    )
    agent = RuntimeAgent(
        LLMRuntimeConfig(),
        live_reload=True,
        food_catalog_repository=food_repository,
    )
    calls: list[str] = []

    def fake_model_call(provider, model, messages, *_args, **_kwargs):
        calls.append(model)
        if model == "reason":
            raise RuntimeError("reasoning unavailable")
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
        semantic_role="tool",
        allowed_skills=["local_file"],
        elfie_config_dir=str(workspace),
    )
    assert primary.actual_model == refs["main"]
    assert reasoning.actual_model == refs["backup"]
    assert reasoning.execution_stage == "fallback"
    assert fallback.actual_model == refs["backup"]
    assert tool.text == "ok:tool"
    assert calls.count("tool") >= 2

    provider_bytes = get_provider_config_path().read_bytes()
    food_snapshot = food_repository.load().to_dict()
    write_runtime_settings(
        {
            "runtime_policy": {
                "tools": {
                    "web_search": {"enabled": False},
                    "local_file": {"enabled": True},
                }
            }
        }
    )
    assert get_provider_config_path().read_bytes() == provider_bytes
    assert food_repository.load().to_dict() == food_snapshot

    provider_store.replace(replace(remote_a, enabled=False))
    emergency_result = agent.run_with_food(
        prompt="use emergency",
        food_key=FOOD_COMMON_ID,
    )
    assert emergency_result.food_used == FOOD_EMERGENCY_ID
    assert emergency_result.actual_model == refs["local"]

    provider_store.replace(remote_a)
    disabled_emergency = replace(
        food_repository.get(FOOD_EMERGENCY_ID),
        enabled=False,
    )
    food_repository.update(disabled_emergency)
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
