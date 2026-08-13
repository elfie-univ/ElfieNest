"""单精灵调试会话：执行、快照、轨迹和历史持久化。"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict
from typing import Any, Callable, Dict, List, Optional

from devtools.elfie_lab.brain_turn_adapter import BrainTurnAdapter
from devtools.elfie_lab.model_execution_adapters import create_model_execution
from devtools.elfie_lab.schemas import (
    ElfieSpec,
    StimulusBundle,
    TurnRecord,
    calculate_state_diff,
    new_id,
    utc_now,
)
from devtools.elfie_lab.session_projection import build_profile, build_snapshot
from devtools.elfie_lab.session_state import apply_state_injection, model_skip_reason
from devtools.elfie_lab.storage import ElfieLabStorage
from devtools.elfie_lab.turn_projection import project_decision
from devtools.elfie_lab.turn_summary import model_call_summary, stimulus_modalities
from elfie import ElfieFactory
from elfie.body import HeadlessBody
from elfie.factory import ElfieAssembly
from infrastructure.persistence.activity import SQLiteActivityStoreAdapter
from infrastructure.persistence.brain_journal import SQLiteBrainJournalAdapter
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


class SessionClosedError(RuntimeError):
    __slots__ = ("elfie_id",)

    def __init__(self, elfie_id: str) -> None:
        super().__init__(elfie_id)
        self.elfie_id = elfie_id

    def __str__(self) -> str:
        return f"调试会话已关闭: {self.elfie_id}"


class ElfieLabSession:
    def __init__(
        self,
        spec: ElfieSpec,
        storage: ElfieLabStorage,
        model_execution_config_dir: str | None = None,
    ):
        self.spec = spec
        self.storage = storage
        self.model_execution_config_dir = model_execution_config_dir or str(
            storage.root / "runtime_config"
        )
        latest = storage.load_latest_session(spec.elfie_id)
        self.session_id = str(latest.get("session_id")) if latest else new_id("session")
        self.created_at = str(latest.get("created_at")) if latest else utc_now()
        self.turns: List[Dict[str, Any]] = (
            list(latest.get("turns", [])) if latest else []
        )
        self.body = HeadlessBody(body_id=f"{spec.elfie_id}:headless")
        self.body.connect()
        workspace = storage.elfie_dir(spec.elfie_id)
        profile_store = YamlProfileStoreAdapter(workspace / "profile")
        self.elfie = ElfieFactory().restore(
            ElfieAssembly(
                profile=profile_store.load(),
                memory_store=SQLiteMemoryStoreAdapter(
                    storage.memory_path(spec.elfie_id)
                ),
                activity_store=SQLiteActivityStoreAdapter(
                    storage.activity_path(spec.elfie_id)
                ),
                journal_store=SQLiteBrainJournalAdapter(
                    storage.journal_path(spec.elfie_id)
                ),
                body=self.body,
            ),
        )
        self._turn_adapter = BrainTurnAdapter(self.elfie)
        self._lock = threading.Lock()
        self._closed = False

    def get_payload(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "elfie_id": self.spec.elfie_id,
            "created_at": self.created_at,
            "updated_at": utc_now(),
            "profile": self.profile(),
            "current_state": self.snapshot(),
            "turns": self.turns,
        }

    def profile(self) -> Dict[str, Any]:
        return build_profile(self.elfie, self.spec, self.storage)

    def snapshot(self) -> Dict[str, Any]:
        return build_snapshot(self.elfie, self.spec)

    def run_turn(self, stimulus: StimulusBundle, food_key: str) -> Dict[str, Any]:
        with self._lock:
            self._ensure_open()
            turn_id = new_id("turn")
            trace: Dict[str, Any] = {}
            pre_injection = self.snapshot()
            injection_changes = apply_state_injection(
                self.elfie,
                stimulus.state_injection,
            )
            state_before = self.snapshot()
            model_execution = None
            started = time.perf_counter()
            result: Dict[str, Any] = {}
            error: Optional[str] = None
            try:
                model_execution = create_model_execution(
                    food_key,
                    self.model_execution_config_dir,
                    workspace_resolver=lambda scope_id: (
                        self.storage.elfie_dir(scope_id)
                        if scope_id is not None
                        else None
                    ),
                )
                outcome, turn_decision, receipts, reasoning = self._turn_adapter.run(
                    stimulus,
                    turn_id,
                    model_execution,
                )
                plan = turn_decision.plan if turn_decision is not None else None
                decision = project_decision(plan, receipts)
                speech = "\n".join(decision["spoken_texts"] + decision["message_texts"])
                result = {
                    "success": outcome.status.value == "completed",
                    "speech": speech,
                    "turn_id": str(outcome.turn_id),
                    "plan_id": str(outcome.plan_id),
                }
                trace = {
                    "stages": {
                        "typed_input": {
                            "source": "developer_tool",
                            "source_domain": stimulus.source_domain,
                            "modalities": stimulus_modalities(stimulus),
                        },
                        "turn_boundary": (
                            turn_decision.model_dump(mode="json", exclude={"plan"})
                            if turn_decision is not None
                            else None
                        ),
                        "cognitive_turn": outcome.model_dump(mode="json"),
                        "output_receipts": [
                            receipt.model_dump(mode="json") for receipt in receipts
                        ],
                        "reasoning": (
                            reasoning.model_dump(mode="json")
                            if reasoning is not None
                            else None
                        ),
                    },
                    "warnings": [],
                }
            except Exception as exc:  # Lab trace must persist unexpected failures.
                error = type(exc).__name__
                result = {
                    "success": False,
                    "reason": "调试回合执行失败",
                    "error": error,
                }
                trace.setdefault("warnings", []).append(error)
                decision = project_decision(None, ())

            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            if injection_changes:
                trace["stages"] = {
                    "state_injection": {
                        "state_before_injection": pre_injection,
                        "changes": injection_changes,
                    },
                    **trace.get("stages", {}),
                }
            state_after = self.snapshot()
            model_call = model_call_summary(
                model_execution.calls[-1]
                if model_execution is not None and model_execution.calls
                else {
                    "food_key": food_key,
                    "skipped": True,
                    "reason": error or model_skip_reason(trace),
                }
            )
            record = TurnRecord(
                turn_id=turn_id,
                session_id=self.session_id,
                elfie_id=self.spec.elfie_id,
                timestamp=utc_now(),
                food_key=food_key,
                stimulus_bundle=asdict(stimulus),
                state_before=state_before,
                trace=trace,
                model_call=model_call,
                result=result,
                decision=decision,
                state_after=state_after,
                state_diff=calculate_state_diff(state_before, state_after),
                duration_ms=duration_ms,
                used_state_injection=bool(injection_changes),
                warnings=list(trace.get("warnings", [])),
                error=error,
            ).to_dict()
            self.turns.append(record)
            self.storage.save_session(self.get_payload())
            return record

    def reset(self) -> Dict[str, Any]:
        with self._lock:
            self._ensure_open()
            self.session_id = new_id("session")
            self.created_at = utc_now()
            self.turns = []
            self._turn_adapter.close()
            self.elfie.close_resources()
            self.body.disconnect()
            self.body = HeadlessBody(body_id=f"{self.spec.elfie_id}:headless")
            self.body.connect()
            workspace = self.storage.elfie_dir(self.spec.elfie_id)
            profile_store = YamlProfileStoreAdapter(workspace / "profile")
            self.elfie = ElfieFactory().restore(
                ElfieAssembly(
                    profile=profile_store.load(),
                    memory_store=SQLiteMemoryStoreAdapter(
                        self.storage.memory_path(self.spec.elfie_id)
                    ),
                    activity_store=SQLiteActivityStoreAdapter(
                        self.storage.activity_path(self.spec.elfie_id)
                    ),
                    journal_store=SQLiteBrainJournalAdapter(
                        self.storage.journal_path(self.spec.elfie_id)
                    ),
                    body=self.body,
                ),
            )
            self._turn_adapter = BrainTurnAdapter(self.elfie)
            self._closed = False
            self.storage.save_session(self.get_payload())
            return self.get_payload()

    def close(self) -> None:
        """Stop cognition and release the body owned by this session."""
        with self._lock:
            self._close_locked()

    def close_if_idle(self) -> bool:
        """Close this session only when no turn or reset currently owns it."""
        if not self._lock.acquire(blocking=False):
            return False
        try:
            self._close_locked()
            return True
        finally:
            self._lock.release()

    def replace_if_idle(
        self,
        update_data: Callable[[], Callable[[], None]],
        create_replacement: Callable[[], ElfieLabSession],
    ) -> ElfieLabSession | None:
        """Build a replacement transactionally while preventing concurrent turns."""
        if not self._lock.acquire(blocking=False):
            return None
        try:
            self._ensure_open()
            rollback = update_data()
            replacement_created = False
            try:
                replacement = create_replacement()
                replacement_created = True
            finally:
                if not replacement_created:
                    rollback()
            self._close_locked()
            return replacement
        finally:
            self._lock.release()

    def _close_locked(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._turn_adapter.close()
        self.elfie.close_resources()
        self.body.disconnect()

    def _ensure_open(self) -> None:
        if self._closed:
            raise SessionClosedError(self.spec.elfie_id)
