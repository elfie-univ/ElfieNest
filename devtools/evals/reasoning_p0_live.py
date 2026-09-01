"""Run one replayable Reasoning P0 chat slice against the production Provider.

The evaluator reads the configured product Food/Provider through the existing
Bootstrap composition, but backs up mutable SQLite inputs into an isolated
temporary data root.  It never copies a credential value into the report.  The
chat itself travels through the real Elfie Brain and OutputRouter so the report
can bind a real Provider response to a terminal ``ExecutionReceipt``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional, Sequence

from app.bootstrap.app_wiring.food import build_report_repository
from app.bootstrap.model_execution import build_model_execution_services
from devtools.evals.stage1_chat_ark import (
    DEFAULT_SPEC,
    CaptureChannel,
    _build_bundle,
    _owner_message,
    load_json,
    redact,
)
from elfie import ElfieFactory
from elfie.body import HeadlessBody
from elfie.brain.reasoning.model_header import ReasoningConstitution
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    ModelPort,
)
from elfie.communication import CommunicationHub, TextPart
from elfie.factory import ElfieAssembly
from elfie.genesis import GenesisMemoryCommitter
from elfie.profile import configure_species_catalog, create_visual_profile
from elfie.public import MainFoodSelection
from infrastructure.models.model_execution_adapter import (
    SerializedModelExecutionAdapter,
)
from infrastructure.models.provider_administration import ProviderModelsAdapter
from infrastructure.persistence.configuration.bundled_defaults import (
    load_reasoning_constitution,
    load_system_defaults,
)
from infrastructure.persistence.configuration.species import load_species_catalog
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.food_evidence import SQLiteFoodEvidenceAdapter
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.model_catalog import load_model_identities
from infrastructure.persistence.provider_catalog import load_provider_catalog
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.provider_storage import ProviderStorageAdapter
from infrastructure.persistence.report_storage import ReportStorageAdapter

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "build" / "evaluations" / "reasoning-p0-live"
DEFAULT_SOURCE_HOME = Path.home() / ".elfienest"
_DIRECT_MESSAGE = "我喜欢雨天，尤其喜欢听雨声。"
_DELIBERATE_MESSAGE = (
    "请结合我刚才说的雨天偏好和你的来历，建议一个我们现在可以聊的话题，"
    "并简短解释为什么。"
)
_SYNTHETIC_ELFIE_ID = "reasoning-p0-live-synthetic"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _backup_sqlite(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    # ``ai-runtime.sqlite`` uses WAL mode.  The source tree is deliberately
    # read-only to this evaluator, so immutable mode prevents SQLite from
    # trying to create source-side ``-shm``/``-wal`` files during the backup.
    source_uri = f"file:{source.resolve()}?mode=ro&immutable=1"
    with sqlite3.connect(source_uri, uri=True) as source_connection:
        with sqlite3.connect(target) as target_connection:
            source_connection.backup(target_connection)


def _link_read_only(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(source.resolve())


def _copy_public_config(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _prepare_isolated_data_home(source_home: Path, isolated_home: Path) -> Path:
    source_db = source_home / "nest.db"
    source_reports = source_home / "reports" / "ai-runtime.sqlite"
    if not source_db.is_file():
        raise FileNotFoundError(source_db)
    if not source_reports.is_file():
        raise FileNotFoundError(source_reports)
    isolated_db = isolated_home / "nest.db"
    _backup_sqlite(source_db, isolated_db)
    _backup_sqlite(
        source_reports,
        isolated_home / "reports" / "ai-runtime.sqlite",
    )
    _copy_public_config(
        source_home / "configs" / "providers.yaml",
        isolated_home / "configs" / "providers.yaml",
    )
    _link_read_only(
        source_home / "configs" / "auth.env",
        isolated_home / "configs" / "auth.env",
    )
    return isolated_db


def _probe_primary_model(isolated_db: Path, reference: str) -> dict[str, Any]:
    """Refresh exactly the serving primary endpoint through its existing probe."""
    layout = final_root_layout(isolated_db.parent)
    provider_catalog = load_provider_catalog(layout.provider_catalog_config)
    report_repository = build_report_repository(str(isolated_db))
    reports = ReportStorageAdapter(report_repository)
    provider_store = ProviderConnectionStore(layout.providers_config)
    provider_storage = ProviderStorageAdapter(
        provider_store,
        secret_path=layout.auth_env,
    )
    evidence = SQLiteFoodEvidenceAdapter(
        provider_store,
        report_repository,
        provider_catalog,
        secret_resolver=provider_storage.resolve_secret,
    )
    adapter = ProviderModelsAdapter(
        provider_storage,
        reports,
        evidence,
        catalog=provider_catalog,
        identity_catalog=load_model_identities(),
        system_defaults=load_system_defaults(),
    )
    asyncio.run(adapter.probe_model(reference))
    observation = reports.latest("model", reference)
    if observation is None:
        raise RuntimeError("primary model probe produced no observation")
    return {
        "reference": reference,
        "status": observation.status,
        "observed_at": observation.observed_at,
        "latency_ms": observation.latency_ms,
        "error_category": observation.error_category,
        "error_message": observation.error_message,
    }


class RecordingModelPort:
    """Observe Brain-owned requests while delegating to the production Adapter."""

    def __init__(self, delegate: ModelPort) -> None:
        self._delegate = delegate
        self.requests: list[ModelGenerationRequest] = []
        self.results: list[ModelGenerationResult] = []
        self.completed: list[tuple[ModelGenerationRequest, ModelGenerationResult]] = []

    def capabilities(self) -> ModelGenerationCapabilities:
        return self._delegate.capabilities()

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        self.requests.append(request)
        result = self._delegate.generate(request)
        self.results.append(result)
        self.completed.append((request, result))
        return result

    def abandon(self, request: ModelGenerationRequest) -> None:
        self._delegate.abandon(request)


@dataclass
class LiveRuntime:
    elfie: Any
    memory_store: SQLiteMemoryStoreAdapter
    channel: CaptureChannel
    model_port: RecordingModelPort

    def close(self) -> None:
        try:
            self.elfie.stop()
            self.elfie.join()
        finally:
            self.memory_store.close()


def _build_live_runtime(
    spec: dict[str, Any],
    *,
    elfie_id: str,
    model_port: RecordingModelPort,
) -> LiveRuntime:
    display_name = str(spec["elfie"]["display_name"])
    bundle = _build_bundle(spec, elfie_id, display_name)
    memory_store = SQLiteMemoryStoreAdapter.in_memory()
    GenesisMemoryCommitter().commit(bundle, memory_store)
    body = HeadlessBody(body_id=f"{elfie_id}:reasoning-p0-live-body")
    body.connect()
    hub = CommunicationHub(elfie_id)
    channel = CaptureChannel()
    hub.register_channel(channel, connect=True)
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=create_visual_profile(
                elfie_id=elfie_id,
                display_name=display_name,
                species_id=str(spec["elfie"]["species_id"]),
                seed=int(spec["elfie"]["profile_seed"]),
            ),
            memory_store=memory_store,
            body=body,
            communication=hub,
            selfhood_seed=(
                bundle.selfhood_state.model_dump(mode="python")
                if bundle.selfhood_state is not None
                else None
            ),
            reasoning_constitution=ReasoningConstitution.from_mapping(
                load_reasoning_constitution()
            ),
            model_port=model_port,
        )
    )
    elfie.start()
    return LiveRuntime(elfie, memory_store, channel, model_port)


def _wait_for_causal_outcome(
    runtime: LiveRuntime,
    *,
    event_id: str,
    outcome_before: int,
    timeout_seconds: float,
) -> Any:
    deadline = time.monotonic() + timeout_seconds
    last_outcome = None
    while time.monotonic() < deadline:
        for outcome in runtime.elfie.turn_outcomes()[outcome_before:]:
            last_outcome = outcome
            decision = runtime.elfie.turn_decision(outcome.turn_id)
            if decision is None or event_id not in {
                str(item) for item in decision.plan.cause_event_ids
            }:
                continue
            runtime.elfie.wait_for_output(outcome.turn_id, timeout=timeout_seconds)
            return outcome
        time.sleep(0.05)
    if last_outcome is not None:
        raise TimeoutError(
            f"causal chat turn did not finish; last={last_outcome.status.value}"
        )
    raise TimeoutError("causal chat turn did not produce an outcome")


def _request_evidence(request: ModelGenerationRequest) -> dict[str, Any]:
    system_markers = {
        marker: marker in request.system_prompt
        for marker in (
            "[APPLICATION_FRAME]",
            "[IDENTITY_CORE]",
            "[ADAPTIVE_SELF]",
            "[OPERATING_CONTRACT]",
            "[CURRENT_BRAIN_STATE]",
        )
    }
    user_markers = {
        marker: marker in request.user_prompt
        for marker in (
            "MEMORY_RECALL_STATUS:",
            "RELEVANT_MEMORY:",
            "CONTEXT_ONLY:",
            "CURRENT_MESSAGE:",
        )
    }
    return {
        "turn_id": str(request.turn_id),
        "response_mode": request.response_mode.value,
        "response_schema": request.response_schema.name,
        "reasoning_mode": request.reasoning_mode,
        "allowed_tools": list(request.allowed_tools),
        "system_prompt_sha256": _sha256(request.system_prompt),
        "user_prompt_sha256": _sha256(request.user_prompt),
        "system_prompt_bytes": len(request.system_prompt.encode("utf-8")),
        "user_prompt_bytes": len(request.user_prompt.encode("utf-8")),
        "system_markers": system_markers,
        "user_markers": user_markers,
        "disabled_tool_protocol_hidden": (
            "Brain semantic tools are bounded" not in request.system_prompt
        ),
        "persistent_activity_protocol_hidden": (
            "PERSISTENT_ACTIVITY_ROUTING:" not in request.system_prompt
        ),
        "contains_prior_direct_message": _DIRECT_MESSAGE in request.user_prompt,
        "contains_current_message": (
            f"CURRENT_MESSAGE:\n{_DIRECT_MESSAGE}" in request.user_prompt
            or f"CURRENT_MESSAGE:\n{_DELIBERATE_MESSAGE}" in request.user_prompt
        ),
    }


def _run_turn(
    runtime: LiveRuntime,
    *,
    index: int,
    text: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    event_id = f"reasoning-p0-live-{index}"
    outcome_before = len(runtime.elfie.turn_outcomes())
    reply_before = len(runtime.channel.sent)
    request_before = len(runtime.model_port.requests)
    completed_before = len(runtime.model_port.completed)
    envelope = _owner_message(
        runtime.elfie.cognitive_datetime - timedelta(seconds=0.5),
        event_id=event_id,
        text=text,
        elfie_id=str(runtime.elfie.profile.identity.elfie_id),
    )
    disposition = runtime.elfie.receive_communication_envelope(envelope)
    outcome = _wait_for_causal_outcome(
        runtime,
        event_id=event_id,
        outcome_before=outcome_before,
        timeout_seconds=timeout_seconds,
    )
    replies = runtime.channel.sent[reply_before:]
    reply_text = "\n".join(
        part.text
        for reply in replies
        for part in reply.parts
        if isinstance(part, TextPart)
    )
    observed_requests = runtime.model_port.requests[request_before:]
    requests = [
        request for request in observed_requests if request.turn_id == outcome.turn_id
    ]
    observed_completed = runtime.model_port.completed[completed_before:]
    results = [
        result
        for request, result in observed_completed
        if request.turn_id == outcome.turn_id
    ]
    receipts = runtime.elfie.execution_receipts(outcome.turn_id)
    reasoning = runtime.elfie.turn_reasoning(outcome.turn_id)
    return {
        "input": text,
        "input_event_id": event_id,
        "disposition": disposition.status.value,
        "outcome_status": outcome.status.value,
        "reply": redact(reply_text),
        "reply_count": len(replies),
        "reasoning": {
            "status": reasoning.status.value if reasoning is not None else None,
            "model_calls": reasoning.model_calls if reasoning is not None else None,
            "tool_calls": reasoning.tool_calls if reasoning is not None else None,
            "failure_reason": (
                reasoning.failure_reason if reasoning is not None else None
            ),
            "steps": [
                {
                    "ordinal": step.ordinal,
                    "kind": step.kind.value,
                    "status": step.status,
                }
                for step in reasoning.steps
            ]
            if reasoning is not None
            else [],
        },
        "requests": [_request_evidence(request) for request in requests],
        "background_request_count": len(observed_requests) - len(requests),
        "provider_results": [
            {
                "provider": result.provider,
                "model_key": result.model_key,
                "selected_mode": result.selected_mode.value,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "latency_ms": result.latency_ms,
            }
            for result in results
        ],
        "execution_receipts": [
            {
                "receipt_id": str(receipt.receipt_id),
                "intent_id": str(receipt.intent_id),
                "executor": receipt.executor.value,
                "status": receipt.status.value,
                "error_code": (
                    receipt.error.code if receipt.error is not None else None
                ),
            }
            for receipt in receipts
        ],
    }


def _completed_communication_receipt(turn: dict[str, Any]) -> bool:
    return any(
        receipt.get("executor") == "communication"
        and receipt.get("status") == "completed"
        for receipt in turn.get("execution_receipts", ())
    )


def _evaluate(
    turns: list[dict[str, Any]],
    *,
    primary_model: str,
    fallback_model: Optional[str],
) -> dict[str, Any]:
    direct, deliberate = turns
    requests = [request for turn in turns for request in turn["requests"]]
    results = [result for turn in turns for result in turn["provider_results"]]
    final_request = deliberate["requests"][-1] if deliberate["requests"] else {}
    system_markers = final_request.get("system_markers", {})
    user_markers = final_request.get("user_markers", {})
    accepted_models = {primary_model}
    if fallback_model:
        accepted_models.add(fallback_model)
    checks = {
        "direct_one_model_call": direct["reasoning"]["model_calls"] == 1,
        "direct_zero_tools": direct["reasoning"]["tool_calls"] == 0,
        "deliberate_bounded_model_calls": (
            isinstance(deliberate["reasoning"]["model_calls"], int)
            and 1 <= deliberate["reasoning"]["model_calls"] <= 2
        ),
        "deliberate_zero_tools": deliberate["reasoning"]["tool_calls"] == 0,
        "all_turns_completed": all(
            turn["disposition"] == "accepted"
            and turn["outcome_status"] == "completed"
            and turn["reply_count"] == 1
            and bool(turn["reply"].strip())
            for turn in turns
        ),
        "real_completed_communication_receipts": all(
            _completed_communication_receipt(turn) for turn in turns
        ),
        "all_requests_hide_disabled_capabilities": all(
            request["allowed_tools"] == []
            and request["disabled_tool_protocol_hidden"]
            and request["persistent_activity_protocol_hidden"]
            for request in requests
        ),
        "final_prompt_has_selfhood_and_state": bool(system_markers)
        and all(system_markers.values()),
        "final_prompt_has_message_history_and_memory": bool(user_markers)
        and all(user_markers.values())
        and final_request.get("contains_prior_direct_message") is True
        and final_request.get("contains_current_message") is True,
        "production_volcengine_provider_used": bool(results)
        and all(
            str(result["provider"]).startswith("volcengine_coding_plan")
            and result["model_key"] in accepted_models
            for result in results
        ),
        "primary_food_attempt_observed": any(
            result["model_key"] == primary_model for result in results
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def _write_report(report: dict[str, Any], output: Path) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "report.json"
    markdown_path = output / "summary.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    evaluation = report.get("evaluation", {})
    passed = bool(evaluation.get("passed"))
    lines = [
        "# Reasoning P0 真实 Provider / Receipt 验收",
        "",
        f"- 结果：`{'PASS' if passed else 'BLOCKED'}`",
    ]
    if "blocked_error" in report:
        lines.append(f"- 阻塞：`{report['blocked_error']}`")
    food = report.get("food")
    if isinstance(food, dict):
        lines.extend(
            (
                f"- Food primary：`{food.get('primary_model')}`",
                f"- Food fallback：`{food.get('fallback_model') or 'none'}`",
            )
        )
    lines.extend(("", "## 机器检查", ""))
    lines.extend(
        f"- {'PASS' if passed else 'FAIL'} `{name}`"
        for name, passed in evaluation.get("checks", {}).items()
    )
    lines.extend(("", "## 对话", ""))
    for turn in report.get("turns", ()):
        lines.append(f"- Owner：{turn['input']}")
        lines.append(f"- Elfie：{turn['reply']}")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the production Reasoning P0 Provider/Receipt slice."
    )
    parser.add_argument("--source-data-home", type=Path, default=DEFAULT_SOURCE_HOME)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    configure_species_catalog(load_species_catalog())
    spec = load_json(DEFAULT_SPEC)
    temp_parent = ROOT / "build" / ".reasoning-p0-live"
    temp_parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any]
    stage = "prepare"
    try:
        with tempfile.TemporaryDirectory(
            prefix="run-", dir=str(temp_parent)
        ) as temp_directory:
            isolated_home = Path(temp_directory)
            stage = "backup_product_inputs"
            isolated_db = _prepare_isolated_data_home(
                args.source_data_home.expanduser().resolve(), isolated_home
            )
            stage = "load_common_food"
            catalog = SQLiteFoodAdapter(isolated_db).load()
            food_id = catalog.global_default_food_id
            food = catalog.packages[food_id]
            if food.primary is None:
                raise RuntimeError(f"Food {food_id!r} has no primary model")
            stage = "validate_primary_food_model"
            provider_probe = _probe_primary_model(isolated_db, food.primary.model)
            stage = "build_model_execution_services"
            services = build_model_execution_services(
                str(isolated_db),
                live_reload=False,
                resolve_main_food=False,
            )
            selection = MainFoodSelection(food_id)
            delegate = SerializedModelExecutionAdapter(
                services.execution,
                scope_id=_SYNTHETIC_ELFIE_ID,
                food_key_resolver=lambda: selection,
            )
            model_port = RecordingModelPort(delegate)
            stage = "build_elfie_runtime"
            runtime = _build_live_runtime(
                spec,
                elfie_id=_SYNTHETIC_ELFIE_ID,
                model_port=model_port,
            )
            try:
                stage = "direct_turn"
                turns = [
                    _run_turn(
                        runtime,
                        index=1,
                        text=_DIRECT_MESSAGE,
                        timeout_seconds=args.timeout_seconds,
                    )
                ]
                stage = "deliberate_turn"
                turns.append(
                    _run_turn(
                        runtime,
                        index=2,
                        text=_DELIBERATE_MESSAGE,
                        timeout_seconds=args.timeout_seconds,
                    )
                )
            finally:
                runtime.close()
            primary_model = food.primary.model
            fallback_model = food.fallback.model if food.fallback is not None else None
            report = {
                "schema_version": "reasoning-p0-live.v1",
                "source_data_home": str(args.source_data_home.expanduser().resolve()),
                "isolation": {
                    "sqlite_inputs_backed_up": True,
                    "credential_values_copied": False,
                    "production_data_written": False,
                    "provider_prompt_uses_synthetic_fixture_only": True,
                    "production_elfie_identity_used": False,
                    "production_conversation_or_memory_used": False,
                },
                "food": {
                    "food_id": food_id,
                    "primary_model": primary_model,
                    "fallback_model": fallback_model,
                },
                "provider_probe": provider_probe,
                "turns": turns,
                "evaluation": _evaluate(
                    turns,
                    primary_model=primary_model,
                    fallback_model=fallback_model,
                ),
            }
    except Exception as error:  # noqa: BLE001 - emit bounded live-gate evidence
        report = {
            "schema_version": "reasoning-p0-live.v1",
            "source_data_home": str(args.source_data_home.expanduser().resolve()),
            "evaluation": {"passed": False, "checks": {}},
            "blocked_stage": stage,
            "blocked_error": redact(f"{type(error).__name__}: {error}"),
        }
    json_path, markdown_path = _write_report(report, args.output)
    print(
        json.dumps(
            {
                "status": "passed" if report["evaluation"]["passed"] else "blocked",
                "json": str(json_path),
                "markdown": str(markdown_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["evaluation"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
