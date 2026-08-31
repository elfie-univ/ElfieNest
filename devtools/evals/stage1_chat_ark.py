"""Run the frozen E1 chat evaluation through the real Elfie Brain path.

The candidate and judge models are called through the user's local ArkCLI
profile.  No API key is accepted as a command-line argument and no key is
written to evaluation artifacts.  The evaluator deliberately keeps machine
facts separate from Ark's soft-quality judgment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.features.adoption import AcceptedAdoptionReservation
from elfie import ElfieFactory
from elfie.body import HeadlessBody
from elfie.brain.reasoning.model_header import ReasoningConstitution
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationRequest,
    ModelGenerationResult,
    ModelResponseMode,
    StructuredOutputMode,
)
from elfie.communication import (
    CommunicationEnvelope,
    CommunicationHub,
    DeliveryReceipt,
    DeliveryStatus,
    MessageDirection,
    TextPart,
)
from elfie.factory import ElfieAssembly
from elfie.genesis import (
    GenesisBundle,
    GenesisMemoryCommitter,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MessageMeta,
    TraceId,
)
from elfie.profile import (
    configure_species_catalog,
    create_visual_profile,
    get_species_canon_for_technical_id,
)
from infrastructure.persistence.configuration.bundled_defaults import (
    load_reasoning_constitution,
)
from infrastructure.persistence.configuration.species import load_species_catalog
from infrastructure.persistence.configuration.world import load_world_canon
from infrastructure.persistence.elfie_workspace.adoption_profiles import (
    _genesis_bundle,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPEC = ROOT / "devtools" / "evals" / "stage1_e1_scenarios.json"
JUDGE_SCHEMA = ROOT / "devtools" / "evals" / "stage1_judge_schema.json"
DEFAULT_OUTPUT = ROOT / "build" / "evaluations" / "stage1-chat" / "e1-ark-current"
DETERMINISTIC_TESTS = (
    "test/devtools/evals/test_stage1_chat_ark.py",
    "test/devtools/evals/test_opt001_e2e3.py",
    "test/devtools/evals/test_opt002_continuous_learning.py",
    "test/e2e/test_stage1_memory_chat.py",
    "test/e2e/test_continuous_learning_memory.py",
    "test/elfie/brain/memory/test_memory_system.py",
    "test/elfie/brain/memory/test_retrieval.py",
    "test/elfie/brain/reasoning/test_memory_context.py",
    "test/elfie/brain/reasoning/test_reasoning.py",
    "test/elfie/genesis/test_initializer.py",
    "test/infrastructure/persistence/elfie_workspace/test_adoption_profiles.py",
    "test/app/orchestration/message_delivery/test_message_delivery_facade.py",
    "test/app/orchestration/test_godot_owner_channel.py",
)

_SECRET_PATTERNS = (
    re.compile(r"ark-[A-Za-z0-9_-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key|token|secret)\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
)

# Match stable identifiers, not prompt field names such as ``memory_id`` or
# ``event_ids``.  Canonical generated IDs use ``genesis:...`` or a typed
# prefix followed by ``:``/a hyphen and an alphanumeric value.
_MEMORY_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"genesis:[A-Za-z0-9][A-Za-z0-9_.:-]*|"
    r"memory-episode:[A-Za-z0-9][A-Za-z0-9_.:-]*|"
    r"(?:episode|memory|event|knowledge|assertion):[A-Za-z0-9][A-Za-z0-9_.:-]*|"
    r"(?:episode|event|knowledge|assertion)-[A-Za-z0-9][A-Za-z0-9_.:-]*"
    r")"
)


def redact(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("<redacted>", result)
    return result


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def memory_evidence_from_prompt(prompt: str) -> List[str]:
    """Extract only stable memory IDs for an auditable, privacy-safe report."""
    return list(dict.fromkeys(_MEMORY_ID_PATTERN.findall(prompt)))[:32]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"评测文件必须是对象: {path}")
    return value


class ArkCallError(RuntimeError):
    pass


class ArkCliJsonClient:
    """Small, secret-free bridge to the already authenticated local ArkCLI."""

    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: float = 180.0,
        binary: str = "arkcli",
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.binary = binary
        self.calls: List[Dict[str, Any]] = []

    def dry_run(self) -> Dict[str, Any]:
        payload = self._invoke(
            prompt="E1 evaluator preflight. Do not answer the task.",
            instructions="Return nothing useful; this is a local dry-run only.",
            schema_path=None,
            dry_run=True,
        )
        return payload

    def json_call(
        self,
        *,
        prompt: str,
        instructions: str,
        schema_path: Optional[Path],
        json_mode: bool = False,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        started = time.perf_counter()
        payload = self._invoke(
            prompt=prompt,
            instructions=instructions,
            schema_path=schema_path,
            json_mode=json_mode,
            dry_run=False,
        )
        duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
        usage_value = payload.get("usage")
        usage: Mapping[str, Any] = usage_value if isinstance(usage_value, dict) else {}
        call = {
            "model_requested": self.model,
            "model_returned": str(payload.get("model") or self.model),
            "duration_ms": duration_ms,
            "prompt_tokens": _int_or_none(usage.get("prompt_tokens")),
            "completion_tokens": _int_or_none(usage.get("completion_tokens")),
            "total_tokens": _int_or_none(usage.get("total_tokens")),
        }
        self.calls.append(call)
        content = payload.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ArkCallError("Ark 返回了空 content")
        # Keep only a bounded, redacted preview for diagnosing provider/schema
        # mismatches.  Full provider output is never copied into artifacts.
        call["content_preview"] = redact(content[:2400])
        return _parse_json_text(content), call

    def text_call(
        self,
        *,
        prompt: str,
        instructions: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """Run an ordinary owner-chat request without forcing JSON."""
        started = time.perf_counter()
        payload = self._invoke(
            prompt=prompt,
            instructions=instructions,
            schema_path=None,
            json_mode=False,
            dry_run=False,
        )
        duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
        usage_value = payload.get("usage")
        usage: Mapping[str, Any] = usage_value if isinstance(usage_value, dict) else {}
        content = payload.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ArkCallError("Ark 返回了空 content")
        call = {
            "model_requested": self.model,
            "model_returned": str(payload.get("model") or self.model),
            "duration_ms": duration_ms,
            "prompt_tokens": _int_or_none(usage.get("prompt_tokens")),
            "completion_tokens": _int_or_none(usage.get("completion_tokens")),
            "total_tokens": _int_or_none(usage.get("total_tokens")),
            "content_preview": redact(content[:2400]),
        }
        self.calls.append(call)
        return content, call

    def _invoke(
        self,
        *,
        prompt: str,
        instructions: str,
        schema_path: Optional[Path],
        json_mode: bool = False,
        dry_run: bool,
    ) -> Dict[str, Any]:
        command = [
            self.binary,
            "+chat",
            "--model",
            self.model,
            "--format",
            "json",
            "--no-progress",
            "--temperature",
            "0.2",
            "--max-output-tokens",
            "768",
        ]
        if instructions.strip():
            command.extend(("--instructions", instructions))
        if schema_path is not None:
            # The judge is required to return a small strict JSON object.  Some
            # Ark reasoning models otherwise spend the entire 768-token budget
            # on hidden reasoning and truncate the JSON response at `length`.
            # Disable provider thinking for this advisory call; machine facts
            # remain authoritative and candidate calls keep their normal mode.
            command.extend(("--thinking", "disabled"))
            command.extend(
                (
                    "--text-format",
                    "json_schema",
                    "--text-schema",
                    str(schema_path),
                    "--text-strict",
                )
            )
        elif json_mode:
            command.extend(("--text-format", "json_object"))
        if dry_run:
            command.append("--dry-run")
        command.append(prompt)
        environment = os.environ.copy()
        environment.update(
            {
                "ARKCLI_NO_UPDATE_NOTIFIER": "1",
                "ARKCLI_CALLER_TYPE": "ai_agent",
                "ARKCLI_CALLER_NAME": "codex",
                "ARKCLI_SKILL_NAME": "arkcli-chat",
            }
        )
        try:
            completed = subprocess.run(
                command,
                cwd=str(ROOT),
                env=environment,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ArkCallError(f"Ark 调用超时: {self.timeout_seconds:.0f}s") from error
        if completed.returncode != 0:
            detail = redact((completed.stderr or completed.stdout or "").strip())
            if len(detail) > 2400:
                detail = f"{detail[:800]} … {detail[-1600:]}"
            raise ArkCallError(
                f"ArkCLI 返回非零退出码 {completed.returncode}: {detail}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ArkCallError("ArkCLI 输出不是合法 JSON") from error
        if not isinstance(payload, dict):
            raise ArkCallError("ArkCLI JSON 输出不是对象")
        return payload


class ArkCliModelPort:
    """Adapt ArkCLI's structured JSON response to Brain's ModelPort."""

    def __init__(self, model: str, *, timeout_seconds: float = 180.0) -> None:
        self.client = ArkCliJsonClient(model=model, timeout_seconds=timeout_seconds)
        self.requests: List[ModelGenerationRequest] = []
        self.errors: List[str] = []

    def capabilities(self) -> ModelGenerationCapabilities:
        return ModelGenerationCapabilities(
            provider="volcengine-coding-plan",
            model_key=self.client.model,
            # Candidate calls deliberately use provider JSON mode.  Brain still
            # validates the returned text against its own DecisionPlan schema;
            # the provider is not asked to carry that internal schema.
            supports_json_schema=False,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=768,
        )

    def abandon(self, request: ModelGenerationRequest) -> None:
        del request

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        self.requests.append(request)
        try:
            if request.response_mode is ModelResponseMode.DIRECT_REPLY:
                text, call = self.client.text_call(
                    prompt=request.user_prompt,
                    instructions=request.system_prompt,
                )
                return ModelGenerationResult(
                    text=text,
                    selected_mode=StructuredOutputMode.PLAIN_TEXT,
                    provider="volcengine-coding-plan",
                    model_key=str(call["model_returned"]),
                    prompt_tokens=call.get("prompt_tokens"),
                    completion_tokens=call.get("completion_tokens"),
                    latency_ms=float(call["duration_ms"]),
                )
            payload, call = self.client.json_call(
                prompt=request.user_prompt,
                instructions=(
                    f"{request.system_prompt}\n"
                    "只输出一个 DecisionPlan JSON 对象，不要 Markdown、代码围栏或解释。"
                ),
                schema_path=None,
                json_mode=True,
            )
        except ArkCallError as error:
            self.errors.append(str(error))
            raise
        return ModelGenerationResult(
            text=json.dumps(payload, ensure_ascii=False),
            selected_mode=StructuredOutputMode.JSON_TEXT,
            provider="volcengine-coding-plan",
            model_key=str(call["model_returned"]),
            prompt_tokens=call.get("prompt_tokens"),
            completion_tokens=call.get("completion_tokens"),
            latency_ms=float(call["duration_ms"]),
        )


class CaptureChannel:
    channel_id = "chat"

    def __init__(self) -> None:
        self.connected = False
        self.sent: List[CommunicationEnvelope] = []

    @property
    def is_connected(self) -> bool:
        return self.connected

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def send_envelope(self, envelope: CommunicationEnvelope) -> DeliveryReceipt:
        self.sent.append(envelope)
        return DeliveryReceipt.for_envelope(envelope, status=DeliveryStatus.SENT)


@dataclass
class RuntimeBundle:
    elfie: Any
    memory_store: SQLiteMemoryStoreAdapter
    body: HeadlessBody
    channel: CaptureChannel
    model_port: ArkCliModelPort

    def close(self) -> None:
        try:
            self.elfie.stop()
            self.elfie.join()
        finally:
            self.memory_store.close()


def _build_bundle(
    spec: Mapping[str, Any], elfie_id: str, display_name: str
) -> GenesisBundle:
    """Build the E1 fixture through the same typed Canon compiler as adoption."""
    elfie_spec = spec["elfie"]
    species_id = str(elfie_spec["species_id"])
    appearance_seed = int(elfie_spec["profile_seed"])
    profile = create_visual_profile(
        elfie_id=elfie_id,
        display_name=display_name,
        species_id=species_id,
        seed=appearance_seed,
    )
    reservation = AcceptedAdoptionReservation(
        elfie_id=elfie_id,
        owner_user_id=1,
        name=display_name,
        species_id=species_id,
        personality_style="好奇探索",
        height="standard",
        build="standard",
        appearance_seed=appearance_seed,
        face="soft",
        signature="warm",
        gender="female",
        birth_date="2001-01-01",
    )
    species = get_species_canon_for_technical_id(species_id)
    world = load_world_canon()
    origin = profile.identity.origin
    selfhood_seed = {
        "state_schema_version": 1,
        "revision": 1,
        "identity_core": {
            "elfie_id": profile.identity.elfie_id,
            "display_name": profile.identity.display_name,
            "species_id": profile.identity.species_id,
            "species_name": species.display_name,
            "home_world_id": origin.home_world_id,
            "home_world_name": world.display_name,
            "home_region_id": origin.home_region_id,
            "home_region_name": world.known_region_name,
            "earth_arrival_statement": world.earth_arrival_statement,
            "resident_role": "ElfieNest 居民",
        },
        "adaptive_self": {
            "big_five": {
                "openness": 0.5,
                "conscientiousness": 0.5,
                "extraversion": 0.5,
                "agreeableness": 0.5,
                "neuroticism": 0.5,
            },
            "interaction_tendency_ids": tuple(species.earth_first_contact_cues),
            "coping_tendency_ids": tuple(species.common_sensory_biases),
            "expression_tendency_ids": ("好奇探索",),
            "value_ids": (
                "尊重自愿选择，不把猜测说成亲历。",
                "不知道时说明不知道，并在真实接触中学习地球。",
            ),
            "speech_marker_ids": ("呢",),
            "source_event_ids": (),
        },
    }
    return _genesis_bundle(reservation, profile, selfhood_seed)


def _build_runtime(
    spec: Mapping[str, Any],
    *,
    elfie_id: str,
    display_name: str,
    model_port: ArkCliModelPort,
    memory_path: Optional[Path] = None,
) -> RuntimeBundle:
    if memory_path is None:
        memory_store = SQLiteMemoryStoreAdapter.in_memory()
    else:
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_store = SQLiteMemoryStoreAdapter(memory_path)
    bundle = _build_bundle(spec, elfie_id, display_name)
    GenesisMemoryCommitter().commit(bundle, memory_store)
    body = HeadlessBody(body_id=f"{elfie_id}:e1-body")
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
            selfhood_seed=bundle.selfhood_state.model_dump(mode="python")
            if bundle.selfhood_state is not None
            else None,
            reasoning_constitution=ReasoningConstitution.from_mapping(
                load_reasoning_constitution()
            ),
            model_port=model_port,
        )
    )
    elfie.start()
    return RuntimeBundle(elfie, memory_store, body, channel, model_port)


def _owner_message(
    at: datetime,
    *,
    event_id: str,
    text: str,
    elfie_id: str,
) -> CommunicationEnvelope:
    owner = ActorRef(actor_id=ActorId("owner-1"), source_kind="owner")
    return CommunicationEnvelope(
        meta=MessageMeta(
            event_id=EventId(event_id),
            elfie_id=ElfieId(elfie_id),
            source=owner,
            occurred_at=at,
            received_at=at,
            trace_id=TraceId(f"trace-{event_id}"),
        ),
        account_id="owner-account",
        channel_id="chat",
        conversation_id="owner-chat",
        sender=owner,
        recipients=(ActorRef(actor_id=ActorId(elfie_id), source_kind="elfie"),),
        direction=MessageDirection.INBOUND,
        external_message_id=f"external-{event_id}",
        dedupe_key=f"external-{event_id}",
        parts=(TextPart(text=text),),
    )


def _run_step(
    runtime: RuntimeBundle,
    *,
    step_index: int,
    text: str,
    duplicate: bool = False,
) -> Dict[str, Any]:
    event_id = f"e1-ark-step-{step_index}"
    envelope = _owner_message(
        # Make the synthetic inbound message old enough to satisfy the normal
        # 400 ms quiet-window trigger without advancing the Brain clock.  This
        # keeps autonomous clock-driven work out of a foreground chat case.
        runtime.elfie.cognitive_datetime - timedelta(seconds=0.5),
        event_id=event_id,
        text=text,
        elfie_id=str(runtime.elfie.profile.identity.elfie_id),
    )
    disposition = runtime.elfie.receive_communication_envelope(envelope)
    # Communication ingestion itself wakes Brain.  Do not inject a clock pulse
    # between chat turns: that pulse can admit autonomous motivation or
    # consolidation work and would race the user-facing scenario under test.
    reply_before = len(runtime.channel.sent)
    outcome_before = len(runtime.elfie.turn_outcomes())
    if disposition.status.value == "accepted":
        # A foreground message can share a frame with a queued internal
        # receipt/reconciliation turn.  Wait for the first actual outbound
        # reply, rather than assuming the first newly recorded outcome belongs
        # to this message.
        outcome = None
        reply_deadline = time.monotonic() + 180.0
        no_reply_deadline: Optional[float] = None
        while time.monotonic() < reply_deadline:
            outcomes = runtime.elfie.turn_outcomes()
            new_outcomes = outcomes[outcome_before:]
            for candidate in new_outcomes:
                try:
                    runtime.elfie.wait_for_output(candidate.turn_id, timeout=0.1)
                except TimeoutError:
                    pass
            replies_now = runtime.channel.sent[reply_before:]
            if replies_now:
                outcome = new_outcomes[-1] if new_outcomes else outcomes[-1]
                break
            if new_outcomes:
                outcome = new_outcomes[-1]
                if no_reply_deadline is None:
                    no_reply_deadline = time.monotonic() + 30.0
                if time.monotonic() >= no_reply_deadline:
                    break
            time.sleep(0.05)
        if outcome is None:
            raise TimeoutError("chat turn did not produce an outcome")
    else:
        outcome = None
    replies = runtime.channel.sent[reply_before:]
    reply_text = "\n".join(
        part.text
        for envelope_item in replies
        for part in envelope_item.parts
        if isinstance(part, TextPart)
    )
    direct_requests = [
        request
        for request in runtime.model_port.requests
        if request.response_mode is ModelResponseMode.DIRECT_REPLY
    ]
    request_prompt = (
        (
            direct_requests[-1] if direct_requests else runtime.model_port.requests[-1]
        ).user_prompt
        if runtime.model_port.requests
        else ""
    )
    if duplicate:
        duplicate_disposition = runtime.elfie.receive_communication_envelope(envelope)
    else:
        duplicate_disposition = None
    return {
        "text": text,
        "event_id": event_id,
        "disposition": disposition.status.value,
        "duplicate_disposition": (
            duplicate_disposition.status.value
            if duplicate_disposition is not None
            else None
        ),
        "outcome_status": outcome.status.value if outcome is not None else None,
        "outcome_fallback_reason": (
            outcome.fallback_reason if outcome is not None else None
        ),
        "outcome_error_code": (outcome.error_code if outcome is not None else None),
        "outcome_model_mode": (
            outcome.model_mode.value if outcome is not None else None
        ),
        "reply": redact(reply_text),
        "reply_count": len(replies),
        "prompt_memory_evidence": memory_evidence_from_prompt(request_prompt),
        "prompt_fingerprint": sha256_text(request_prompt) if request_prompt else None,
        "prompt_contains": request_prompt,
    }


def _run_case(
    spec: Mapping[str, Any],
    scenario: Mapping[str, Any],
    *,
    repetition: int,
    candidate_model: str,
) -> Dict[str, Any]:
    scenario_id = str(scenario["scenario_id"])
    elfie_id = f"e1-ark-{scenario_id}-{repetition}"
    display_name = str(spec["elfie"]["display_name"])
    runtime = ArkCliModelPort(candidate_model)
    temp_parent = ROOT / "build" / ".e1-ark-tmp"
    temp_parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(
        tempfile.mkdtemp(prefix=f"elfie-e1-{scenario_id}-", dir=str(temp_parent))
    )
    # The production memory adapter intentionally accepts only its canonical
    # filename.  Keep restart evidence on an isolated temporary path while
    # preserving that persistence contract.
    memory_path = (
        temp_root / "knowledge.sqlite"
        if scenario.get("restart_after_step") is not None
        else None
    )
    first = _build_runtime(
        spec,
        elfie_id=elfie_id,
        display_name=display_name,
        model_port=runtime,
        memory_path=memory_path,
    )
    step_results: List[Dict[str, Any]] = []
    bundles = [first]
    try:
        restart_after = scenario.get("restart_after_step")
        for index, raw_step in enumerate(scenario.get("steps", ())):
            step = dict(raw_step)
            step_results.append(
                _run_step(
                    bundles[-1],
                    step_index=index,
                    text=str(step["text"]),
                    duplicate=index == int(scenario.get("duplicate_step", -1)),
                )
            )
            if restart_after is not None and index == int(restart_after):
                bundles[-1].close()
                restarted_port = ArkCliModelPort(candidate_model)
                bundles.append(
                    _build_runtime(
                        spec,
                        elfie_id=elfie_id,
                        display_name=display_name,
                        model_port=restarted_port,
                        memory_path=memory_path,
                    )
                )
        all_prompts = "\n".join(
            str(item.get("prompt_contains", "")) for item in step_results
        )
        replies = [str(item.get("reply", "")) for item in step_results]
        required_prompt_tokens = tuple(
            str(item) for item in scenario.get("required_prompt_tokens", ())
        )
        required_prompt_ok = all(
            token in all_prompts for token in required_prompt_tokens
        )
        forbidden = tuple(
            str(item) for item in scenario.get("forbidden_response_patterns", ())
        )
        forbidden_hits = [
            pattern
            for pattern in forbidden
            if any(re.search(pattern, reply, flags=re.IGNORECASE) for reply in replies)
        ]
        expected_replies = int(
            scenario.get("expected_reply_count", len(scenario.get("steps", ())))
            if scenario.get("duplicate_step") is None
            else scenario.get("expected_reply_count", 1)
        )
        observed_replies = sum(int(item.get("reply_count", 0)) for item in step_results)
        required_reply_failures: List[str] = []
        for index, raw_step in enumerate(scenario.get("steps", ())):
            for token in raw_step.get("required_reply_tokens", ()):
                if str(token) not in step_results[index].get("reply", ""):
                    required_reply_failures.append(f"step-{index}:{token}")
        duplicate_ok = True
        if scenario.get("duplicate_step") is not None:
            duplicate_ok = (
                step_results[int(scenario["duplicate_step"])].get(
                    "duplicate_disposition"
                )
                == "duplicate"
            )
        outcome_ok = all(
            item.get("disposition") == "accepted"
            and item.get("outcome_status") == "completed"
            for item in step_results
        )
        machine = {
            "passed": bool(
                required_prompt_ok
                and not forbidden_hits
                and not required_reply_failures
                and duplicate_ok
                and outcome_ok
                and observed_replies == expected_replies
            ),
            "required_prompt_tokens": list(required_prompt_tokens),
            "missing_prompt_tokens": [
                token for token in required_prompt_tokens if token not in all_prompts
            ],
            "forbidden_hits": forbidden_hits,
            "required_reply_failures": required_reply_failures,
            "duplicate_ok": duplicate_ok,
            "outcome_ok": outcome_ok,
            "expected_reply_count": expected_replies,
            "observed_reply_count": observed_replies,
        }
        return {
            "scenario_id": scenario_id,
            "repetition": repetition,
            "candidate_model": candidate_model,
            "steps": [
                {key: value for key, value in item.items() if key != "prompt_contains"}
                for item in step_results
            ],
            "transcript": [
                {
                    "user": str(raw_step["text"]),
                    "elfie": step_results[index].get("reply", ""),
                }
                for index, raw_step in enumerate(scenario.get("steps", ()))
            ],
            "machine": machine,
            "applicable_dimensions": list(scenario.get("applicable_dimensions", ())),
            "model_calls": [
                call for bundle in bundles for call in bundle.model_port.client.calls
            ],
            "model_errors": [
                error for bundle in bundles for error in bundle.model_port.errors
            ],
        }
    finally:
        for bundle in reversed(bundles):
            try:
                bundle.close()
            except Exception:
                pass
        try:
            for path in sorted(temp_root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            temp_root.rmdir()
        except OSError:
            pass


def _judge_case(
    scenario: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    judge_model: str,
) -> Dict[str, Any]:
    scenario_id = str(scenario["scenario_id"])
    instructions = (
        "你是 Elfie 第一阶段 E1 的严格体验评审员。只输出符合 JSON Schema 的 JSON。"
        "你不能推翻机器事实；只评估可见回复是否保持身份连续、异星世界边界、记忆依据、"
        "领养前经历连续性和自然表达。不要奖励没有证据的创造性细节。"
        "评分锚点：1=明显失败，2=频繁出戏，3=时好时坏，4=稳定可信，5=自然且让人想继续探索。"
    )
    prompt = json.dumps(
        {
            "scenario_id": scenario_id,
            "purpose": scenario.get("purpose"),
            "applicable_dimensions": scenario.get("applicable_dimensions", ()),
            "forbidden_response_patterns": scenario.get(
                "forbidden_response_patterns", ()
            ),
            "machine_result": result.get("machine", {}),
            "transcript": result.get("transcript", []),
        },
        ensure_ascii=False,
    )
    last_error = "unknown judge contract error"
    attempts: List[Dict[str, Any]] = []
    for attempt in range(1, 3):
        client = ArkCliJsonClient(model=judge_model)
        try:
            parsed, call = client.json_call(
                prompt=prompt,
                instructions=instructions
                + f"\n本次必须评审 scenario_id={scenario_id}，不得输出其他场景。",
                schema_path=JUDGE_SCHEMA,
            )
        except ArkCallError as error:
            last_error = str(error)
            continue
        attempts.append(call)
        if parsed.get("scenario_id") != scenario_id:
            last_error = (
                "裁判返回的 scenario_id 不匹配："
                f"期望 {scenario_id}，实际 {parsed.get('scenario_id')}"
            )
            continue
        evidence = parsed.get("evidence")
        if not isinstance(evidence, list) or any(
            not isinstance(item, str) or not item.strip() for item in evidence
        ):
            last_error = "裁判 evidence 必须是非空说明"
            continue
        parsed["_call"] = call
        parsed["_judge_attempts"] = attempts
        parsed["_judge_retry_count"] = attempt - 1
        return parsed
    raise ArkCallError(last_error)


def _run_deterministic_gate() -> Dict[str, Any]:
    python = Path(sys.executable)
    command = [str(python), "-m", "pytest", "-q", *DETERMINISTIC_TESTS]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=600.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"passed": False, "status": "timeout", "command": command}
    output = redact((completed.stdout or "") + (completed.stderr or ""))
    return {
        "passed": completed.returncode == 0,
        "status": "passed" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "duration_ms": round((time.perf_counter() - started) * 1000.0, 2),
        "command": command,
        "output_tail": output[-6000:],
    }


def _git_revision() -> Dict[str, Any]:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = (
            subprocess.run(
                ["git", "diff", "--quiet"],
                cwd=str(ROOT),
                capture_output=True,
                check=False,
            ).returncode
            != 0
        )
        return {"head": head, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"head": "unknown", "dirty": True}


def _aggregate_judges(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    by_dimension: Dict[str, List[int]] = {}
    failures: List[str] = []
    for item in results:
        judge = item.get("judge")
        if not isinstance(judge, dict):
            failures.append(str(item.get("scenario_id")))
            continue
        scores = judge.get("scores")
        if not isinstance(scores, dict):
            failures.append(str(item.get("scenario_id")))
            continue
        applicable = {str(value) for value in item.get("applicable_dimensions", ())}
        for dimension in applicable:
            value = scores.get(dimension)
            if not isinstance(value, int):
                failures.append(f"{item.get('scenario_id')}:{dimension}")
                continue
            by_dimension.setdefault(dimension, []).append(value)
        violations = judge.get("violations", ())
        if isinstance(violations, list) and violations:
            failures.append(f"{item.get('scenario_id')}:violations")
    summary: Dict[str, Any] = {}
    passed = not failures
    for dimension, values in sorted(by_dimension.items()):
        summary[dimension] = {
            "sample_count": len(values),
            "median": statistics.median(values),
            "worst": min(values),
            "all_at_least_4": min(values) >= 4,
        }
        passed = passed and min(values) >= 4
    return {"passed": passed, "dimensions": summary, "failures": failures}


def _write_report(report: Mapping[str, Any], output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    lines = [
        "# E1 Ark 评测报告",
        "",
        f"- 运行时间：{report.get('created_at')}",
        f"- 评测规约：{report.get('scenario_set', {}).get('version')}",
        f"- 候选模型：{report.get('candidate_model')}",
        f"- 裁判模型：{report.get('judge_model')}",
        f"- 重复次数：{report.get('repetitions')}",
        f"- 实际模型调用：{report.get('actual_calls', {})}",
        f"- PromotionDecision：`{report.get('promotion_decision')}`",
        "",
        "## 门禁摘要",
        "",
        f"- 确定性门禁：`{report.get('deterministic_gate', {}).get('status')}`",
        f"- 真实模型预检：`{report.get('preflight', {}).get('status', 'not-run')}`",
        f"- 机器硬门：`{'PASS' if report.get('machine_gate_passed') else 'FAIL'}`",
        f"- Ark 软质量：`{'PASS' if report.get('judge_gate', {}).get('passed') else 'FAIL/未完成'}`",
        "",
        "## 场景结果",
        "",
        "| 场景 | 重复 | 机器门 | 关键回复 |",
        "| --- | ---: | --- | --- |",
    ]
    for result in report.get("results", ()):
        reply = " / ".join(
            str(item.get("reply", "")) for item in result.get("steps", ())
        )
        reply = reply.replace("\n", " ")[:180]
        lines.append(
            f"| {result.get('scenario_id')} | {result.get('repetition')} | "
            f"{'PASS' if result.get('machine', {}).get('passed') else 'FAIL'} | {reply} |"
        )
    lines.extend(("", "## 残余与阻塞", ""))
    for item in report.get("residuals", ()):
        lines.append(f"- {item}")
    with markdown_path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return json_path, markdown_path


def _int_or_none(value: Any) -> Optional[int]:
    return int(value) if isinstance(value, (int, float)) else None


def _parse_json_text(value: str) -> Dict[str, Any]:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ArkCallError("模型 JSON 顶层不是对象")
    return parsed


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the frozen E1 Ark evaluation.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Run local gates and print the call plan only.",
    )
    mode.add_argument(
        "--real-run",
        action="store_true",
        help="Call the authenticated local ArkCLI profile.",
    )
    mode.add_argument(
        "--rejudge-report",
        type=Path,
        help="Reuse candidate results from an earlier report and rerun only Ark judge calls.",
    )
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--candidate-model", default="doubao-seed-2.0-lite")
    parser.add_argument("--judge-model", default="deepseek-v4-pro")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--case", action="append", dest="cases", default=[])
    parser.add_argument("--skip-deterministic", action="store_true")
    parser.add_argument("--max-calls", type=int, default=96)
    return parser.parse_args(argv)


def _rejudge_existing_report(
    *,
    args: argparse.Namespace,
    spec: Mapping[str, Any],
) -> int:
    """Rejudge frozen candidate transcripts without paying for new candidates."""
    source = load_json(args.rejudge_report)
    source_results = source.get("results")
    if not isinstance(source_results, list) or not source_results:
        raise SystemExit("--rejudge-report 中没有可重评的 results")
    scenarios = {
        str(item.get("scenario_id")): item
        for item in spec.get("scenarios", ())
        if isinstance(item, dict)
    }
    deterministic = {"status": "skipped"}
    if not args.skip_deterministic:
        deterministic = _run_deterministic_gate()
    report: Dict[str, Any] = dict(source)
    report["created_at"] = utc_now()
    report["source_revision"] = _git_revision()
    report["replay_of"] = {
        "path": str(args.rejudge_report),
        "sha256": sha256_text(args.rejudge_report.read_text(encoding="utf-8")),
    }
    report["candidate_model"] = source.get("candidate_model", args.candidate_model)
    report["judge_model"] = args.judge_model
    report["repetitions"] = source.get("repetitions")
    report["estimated_calls"] = {
        "candidate": 0,
        "judge": len(source_results),
        "total": len(source_results),
    }
    report["deterministic_gate"] = deterministic
    report["results"] = []
    report["residuals"] = []
    preflight_client = ArkCliJsonClient(model=args.judge_model, timeout_seconds=60.0)
    try:
        preflight = preflight_client.dry_run()
        report["preflight"] = {
            "status": "passed",
            "summary": preflight.get("summary", {}),
        }
    except ArkCallError as error:
        report["preflight"] = {"status": "failed", "error": str(error)}
        report["promotion_decision"] = "BLOCKED"
        report["residuals"].append("Ark 裁判 dry-run 失败，重评未执行。")
        json_path, markdown_path = _write_report(report, args.output)
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "json": str(json_path),
                    "markdown": str(markdown_path),
                },
                ensure_ascii=False,
            )
        )
        return 2

    machine_passed = True
    provider_blocked = False
    for old_result in source_results:
        result = dict(old_result)
        scenario_id = str(result.get("scenario_id"))
        scenario = scenarios.get(scenario_id)
        if scenario is None:
            provider_blocked = True
            result["judge"] = {"error": f"scenario 不在冻结规约中: {scenario_id}"}
        else:
            try:
                result["judge"] = _judge_case(
                    scenario,
                    result,
                    judge_model=args.judge_model,
                )
            except ArkCallError as error:
                provider_blocked = True
                result["judge"] = {"error": redact(str(error))}
        machine_passed = machine_passed and bool(
            result.get("machine", {}).get("passed")
        )
        report["results"].append(result)

    report["machine_gate_passed"] = machine_passed
    report["judge_gate"] = _aggregate_judges(report["results"])
    if not deterministic.get("passed", False):
        report["residuals"].append("确定性硬门禁未通过。")
    if not machine_passed:
        report["residuals"].append("候选结果中至少一个机器硬门禁失败。")
    if provider_blocked:
        report["residuals"].append("至少一个裁判调用或裁判契约校验失败。")
    report["residuals"].append("负责人对匿名对话样本的体验确认尚未完成。")
    report["actual_calls"] = {
        "candidate": sum(
            len(item.get("model_calls", ())) for item in report["results"]
        ),
        "judge": sum(
            len(item.get("judge", {}).get("_judge_attempts", ()))
            + int(item.get("judge", {}).get("_judge_retry_count", 0))
            for item in report["results"]
            if isinstance(item.get("judge"), dict)
        ),
    }
    report["actual_calls"]["total"] = (
        report["actual_calls"]["candidate"] + report["actual_calls"]["judge"]
    )
    report["promotion_decision"] = (
        "BLOCKED"
        if provider_blocked or not deterministic.get("passed", False)
        else "NO-GO"
        if not machine_passed or not report["judge_gate"]["passed"]
        else "BLOCKED"
    )
    json_path, markdown_path = _write_report(report, args.output)
    print(
        json.dumps(
            {
                "status": report["promotion_decision"].lower(),
                "json": str(json_path),
                "markdown": str(markdown_path),
            },
            ensure_ascii=False,
        )
    )
    return 1 if report["promotion_decision"] == "NO-GO" else 2


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    # The evaluator is a developer-tool entrypoint, so it must perform the
    # same explicit catalog injection that the production Bootstrap and tests
    # perform.  No global fallback is allowed.
    configure_species_catalog(load_species_catalog())
    if args.repetitions < 1:
        raise SystemExit("--repetitions 必须大于 0")
    spec = load_json(args.spec)
    if args.rejudge_report is not None:
        return _rejudge_existing_report(args=args, spec=spec)
    scenarios = list(spec.get("scenarios", ()))
    if args.cases:
        requested = set(args.cases)
        scenarios = [item for item in scenarios if item.get("scenario_id") in requested]
    if not scenarios:
        raise SystemExit("没有匹配的 E1 场景")
    candidate_calls = (
        sum(len(item.get("steps", ())) for item in scenarios) * args.repetitions
    )
    judge_calls = len(scenarios) * args.repetitions
    estimated_calls = candidate_calls + judge_calls
    if estimated_calls > args.max_calls:
        raise SystemExit(
            f"预计 {estimated_calls} 次模型调用超过 --max-calls={args.max_calls}；请减少场景/重复次数并显式重试。"
        )

    deterministic = {"status": "skipped"}
    if not args.skip_deterministic:
        deterministic = _run_deterministic_gate()
    revision = _git_revision()
    report: Dict[str, Any] = {
        "created_at": utc_now(),
        "scenario_set": {
            "path": str(args.spec),
            "version": spec.get("schema_version"),
            "sha256": sha256_text(args.spec.read_text(encoding="utf-8")),
            "scenario_count": len(scenarios),
        },
        "source_revision": revision,
        "candidate_model": args.candidate_model,
        "judge_model": args.judge_model,
        "repetitions": args.repetitions,
        "estimated_calls": {
            "candidate": candidate_calls,
            "judge": judge_calls,
            "total": estimated_calls,
        },
        "deterministic_gate": deterministic,
        "results": [],
        "residuals": [],
    }
    if not args.real_run:
        report["promotion_decision"] = "DRY-RUN"
        report["residuals"] = [
            "尚未调用真实模型；必须使用 --real-run 才能完成 Ark 体验评测。",
            "负责人体验确认尚未进行。",
        ]
        json_path, markdown_path = _write_report(report, args.output)
        print(
            json.dumps(
                {
                    "status": "dry-run",
                    "json": str(json_path),
                    "markdown": str(markdown_path),
                    "estimated_calls": report["estimated_calls"],
                },
                ensure_ascii=False,
            )
        )
        return 0

    preflight_client = ArkCliJsonClient(
        model=args.candidate_model, timeout_seconds=60.0
    )
    try:
        preflight = preflight_client.dry_run()
        report["preflight"] = {
            "status": "passed",
            "summary": preflight.get("summary", {}),
        }
    except ArkCallError as error:
        report["preflight"] = {"status": "failed", "error": str(error)}
        report["promotion_decision"] = "BLOCKED"
        report["residuals"].append("ArkCLI dry-run 失败，真实模型评测未执行。")
        json_path, markdown_path = _write_report(report, args.output)
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "json": str(json_path),
                    "markdown": str(markdown_path),
                },
                ensure_ascii=False,
            )
        )
        return 2

    machine_passed = True
    provider_blocked = False
    for scenario in scenarios:
        for repetition in range(1, args.repetitions + 1):
            try:
                result = _run_case(
                    spec,
                    scenario,
                    repetition=repetition,
                    candidate_model=args.candidate_model,
                )
                if not result["machine"]["passed"]:
                    machine_passed = False
                try:
                    result["judge"] = _judge_case(
                        scenario,
                        result,
                        judge_model=args.judge_model,
                    )
                except ArkCallError as error:
                    result["judge"] = {"error": str(error)}
                    provider_blocked = True
                report["results"].append(result)
            except Exception as error:  # noqa: BLE001 - report evaluator failures
                provider_blocked = True
                report["results"].append(
                    {
                        "scenario_id": scenario.get("scenario_id"),
                        "repetition": repetition,
                        "machine": {"passed": False, "error": redact(str(error))},
                        "transcript": [],
                        "steps": [],
                        "applicable_dimensions": list(
                            scenario.get("applicable_dimensions", ())
                        ),
                    }
                )
    report["machine_gate_passed"] = machine_passed
    report["judge_gate"] = _aggregate_judges(report["results"])
    report["actual_calls"] = {
        "candidate": sum(
            len(item.get("model_calls", ())) for item in report["results"]
        ),
        "judge": sum(
            len(item.get("judge", {}).get("_judge_attempts", ()))
            + int(item.get("judge", {}).get("_judge_retry_count", 0))
            for item in report["results"]
            if isinstance(item.get("judge"), dict)
        ),
    }
    report["actual_calls"]["total"] = (
        report["actual_calls"]["candidate"] + report["actual_calls"]["judge"]
    )
    if not deterministic.get("passed", False):
        report["residuals"].append("确定性硬门禁未通过。")
    if not machine_passed:
        report["residuals"].append("至少一个 E1 场景的机器硬门禁失败。")
    if provider_blocked:
        report["residuals"].append(
            "至少一个真实模型或裁判调用失败，结果不能视为完整通过。"
        )
    report["residuals"].append("负责人对匿名对话样本的体验确认尚未完成。")
    report["promotion_decision"] = (
        "BLOCKED"
        if provider_blocked or not deterministic.get("passed", False)
        else "NO-GO"
        if not machine_passed or not report["judge_gate"]["passed"]
        else "BLOCKED"
    )
    json_path, markdown_path = _write_report(report, args.output)
    print(
        json.dumps(
            {
                "status": report["promotion_decision"].lower(),
                "json": str(json_path),
                "markdown": str(markdown_path),
                "estimated_calls": report["estimated_calls"],
            },
            ensure_ascii=False,
        )
    )
    if report["promotion_decision"] == "NO-GO":
        return 1
    if report["promotion_decision"] == "BLOCKED":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
