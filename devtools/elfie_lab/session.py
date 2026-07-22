"""单精灵调试会话：执行、快照、轨迹和历史持久化。"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from devtools.elfie_lab.deprecated_sync_adapter import DeprecatedSyncCognitionAdapter
from devtools.elfie_lab.runtime_adapters import create_runtime
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
from elfie import ElfieFactory
from elfie.body import HeadlessBody


class ElfieLabSession:
    def __init__(
        self,
        spec: ElfieSpec,
        storage: ElfieLabStorage,
        runtime_config_dir: str | None = None,
    ):
        self.spec = spec
        self.storage = storage
        self.runtime_config_dir = runtime_config_dir or str(
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
        self.elfie = ElfieFactory().restore(
            storage.elfie_dir(spec.elfie_id),
            memory_db_path=str(storage.memory_path(spec.elfie_id)),
            body=self.body,
        )
        self._sync_adapter = DeprecatedSyncCognitionAdapter(self.elfie)
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
            turn_id = new_id("turn")
            trace: Dict[str, Any] = {}
            pre_injection = self.snapshot()
            injection_changes = apply_state_injection(
                self.elfie,
                stimulus.state_injection,
            )
            state_before = self.snapshot()
            runtime = None
            started = time.perf_counter()
            result: Dict[str, Any] = {}
            error: Optional[str] = None
            try:
                runtime = create_runtime(food_key, self.runtime_config_dir)
                outcome, receipts = self._sync_adapter.run(
                    stimulus,
                    turn_id,
                    runtime,
                )
                response = runtime.calls[-1].get("response", "") if runtime.calls else ""
                result = {
                    "success": outcome.status.value == "completed",
                    "speech": str(response),
                    "action": "",
                    "turn_id": str(outcome.turn_id),
                    "plan_id": str(outcome.plan_id),
                }
                trace = {
                    "stages": {
                        "typed_input": {"source": "developer_tool"},
                        "cognitive_turn": outcome.model_dump(mode="json"),
                        "output_receipts": [
                            receipt.model_dump(mode="json") for receipt in receipts
                        ],
                    },
                    "warnings": [],
                }
            except Exception as exc:  # noqa: BROAD_EXCEPT_OK - Lab trace boundary
                error = f"{type(exc).__name__}: {exc}"
                result = {
                    "success": False,
                    "reason": "调试回合执行失败",
                    "error": error,
                }
                trace.setdefault("warnings", []).append(error)

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
            model_call = (
                runtime.calls[-1]
                if runtime is not None and runtime.calls
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
            self.session_id = new_id("session")
            self.created_at = utc_now()
            self.turns = []
            self._sync_adapter.close()
            self.body.disconnect()
            self.body = HeadlessBody(body_id=f"{self.spec.elfie_id}:headless")
            self.body.connect()
            self.elfie = ElfieFactory().restore(
                self.storage.elfie_dir(self.spec.elfie_id),
                memory_db_path=str(self.storage.memory_path(self.spec.elfie_id)),
                body=self.body,
            )
            self._sync_adapter = DeprecatedSyncCognitionAdapter(self.elfie)
            self._closed = False
            self.storage.save_session(self.get_payload())
            return self.get_payload()

    def close(self) -> None:
        """Stop cognition and release the body owned by this session."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._sync_adapter.close()
            self.body.disconnect()
