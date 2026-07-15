"""单精灵调试会话：执行、快照、轨迹和历史持久化。"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from devtools.elfie_lab.runtime_adapters import create_runtime
from devtools.elfie_lab.schemas import (
    ElfieSpec,
    StimulusBundle,
    TurnRecord,
    calculate_state_diff,
    new_id,
    utc_now,
)
from devtools.elfie_lab.storage import ElfieLabStorage
from elfie import ElfieIndividual


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
        self.elfie = ElfieIndividual(
            anatomy_type=spec.anatomy_type,
            memory_db_path=str(storage.memory_path(spec.elfie_id)),
        )
        self._lock = threading.Lock()
        if self.turns:
            self._restore_snapshot(self.turns[-1].get("state_after", {}))

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
        profile = self.elfie.brain.profile
        personality = profile.personality
        metadata = personality.get("metadata", {})
        return {
            **self.spec.to_dict(),
            "configured_name": metadata.get("name", self.spec.name),
            "personality_summary": self._personality_summary(
                personality.get("big_five", {})
            ),
            "big_five": personality.get("big_five", {}),
            "speech_style": personality.get("speech_style", {}),
            "capabilities": profile.capabilities,
            "system_limits": profile.system_limits,
            "core_cognition": self.elfie.memory.get_core_cognition(),
            "memory_count": len(self.elfie.memory.get_all_episodes()),
            "model": {
                "interaction_protocol": "food",
                "default_food": "mock",
                "mock_model": "elfie-mock",
                "catalog_scope": "runtime",
            },
        }

    def snapshot(self) -> Dict[str, Any]:
        expression = self.elfie.amygdala.get_expression() or {}
        return {
            "energy": round(self.elfie.hypothalamus.get_energy(), 2),
            "fatigue": round(self.elfie.hypothalamus.get_fatigue(), 2),
            "is_sleeping": bool(self.elfie.hypothalamus.is_sleeping),
            "emotions": {
                name: round(value, 2)
                for name, value in self.elfie.amygdala.emotions.items()
            },
            "dominant_emotion": self.elfie.amygdala.get_dominant_mood(),
            "expression": expression,
            "attention_network": self.elfie.brain.attention.current_network,
            "anatomy_type": self.spec.anatomy_type,
            "action_intent": self.elfie.motion_actuator.last_action_intent,
            "joint_angles": {
                name: round(value, 3)
                for name, value in self.elfie.anatomy.get_joint_angles().items()
            },
            "elapsed_time": round(self.elfie.elapsed_time, 3),
            "memory_count": len(self.elfie.memory.get_all_episodes()),
        }

    def run_turn(self, stimulus: StimulusBundle, food_key: str) -> Dict[str, Any]:
        with self._lock:
            turn_id = new_id("turn")
            trace: Dict[str, Any] = {}
            pre_injection = self.snapshot()
            injection_changes = self._apply_state_injection(stimulus.state_injection)
            state_before = self.snapshot()
            runtime = None
            started = time.perf_counter()
            result: Dict[str, Any] = {}
            error: Optional[str] = None
            try:
                runtime = create_runtime(food_key, self.runtime_config_dir)
                result = self.elfie.perceive_and_respond(
                    stimulus.to_sensor_data(turn_id), runtime, debug_trace=trace
                )
            except Exception as exc:
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
                    "reason": error or self._model_skip_reason(trace),
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
            self.elfie = ElfieIndividual(
                anatomy_type=self.spec.anatomy_type,
                memory_db_path=str(self.storage.memory_path(self.spec.elfie_id)),
            )
            self.storage.save_session(self.get_payload())
            return self.get_payload()

    def _apply_state_injection(self, injection: Dict[str, Any]) -> Dict[str, Any]:
        if not injection:
            return {}
        allowed = {"energy", "fatigue", "is_sleeping", "emotions"}
        unknown = set(injection) - allowed
        if unknown:
            raise ValueError(f"不支持的状态注入字段: {', '.join(sorted(unknown))}")

        changes: Dict[str, Any] = {}
        if "energy" in injection:
            value = self._bounded_number(injection["energy"], "energy")
            changes["energy"] = {
                "before": self.elfie.hypothalamus.energy,
                "after": value,
            }
            self.elfie.hypothalamus.energy = value
        if "fatigue" in injection:
            value = self._bounded_number(injection["fatigue"], "fatigue")
            changes["fatigue"] = {
                "before": self.elfie.hypothalamus.fatigue,
                "after": value,
            }
            self.elfie.hypothalamus.fatigue = value
        if "is_sleeping" in injection:
            value = bool(injection["is_sleeping"])
            changes["is_sleeping"] = {
                "before": self.elfie.hypothalamus.is_sleeping,
                "after": value,
            }
            self.elfie.hypothalamus.is_sleeping = value
        if "emotions" in injection:
            emotions = injection["emotions"]
            if not isinstance(emotions, dict):
                raise ValueError("emotions 必须是字典")
            changes["emotions"] = {}
            for name, raw_value in emotions.items():
                if name not in self.elfie.amygdala.emotions:
                    raise ValueError(f"未知情绪: {name}")
                value = self._bounded_number(raw_value, name)
                changes["emotions"][name] = {
                    "before": self.elfie.amygdala.emotions[name],
                    "after": value,
                }
                self.elfie.amygdala.emotions[name] = value
        return changes

    def _restore_snapshot(self, snapshot: Dict[str, Any]) -> None:
        if not snapshot:
            return
        self.elfie.hypothalamus.energy = float(snapshot.get("energy", 100.0))
        self.elfie.hypothalamus.fatigue = float(snapshot.get("fatigue", 0.0))
        self.elfie.hypothalamus.is_sleeping = bool(snapshot.get("is_sleeping", False))
        for name, value in snapshot.get("emotions", {}).items():
            if name in self.elfie.amygdala.emotions:
                self.elfie.amygdala.emotions[name] = float(value)
        joints = snapshot.get("joint_angles", {})
        if isinstance(joints, dict):
            self.elfie.anatomy.apply_joint_angles(joints)
        self.elfie.motion_actuator.last_action_intent = str(
            snapshot.get("action_intent", "idle")
        )
        self.elfie.brain.attention.current_network = str(
            snapshot.get("attention_network", "DMN")
        )
        self.elfie.elapsed_time = float(snapshot.get("elapsed_time", 0.0))

    @staticmethod
    def _bounded_number(value: Any, field_name: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} 必须是数字") from exc
        if not 0.0 <= number <= 100.0:
            raise ValueError(f"{field_name} 必须在 0 到 100 之间")
        return number

    @staticmethod
    def _model_skip_reason(trace: Dict[str, Any]) -> str:
        stages = trace.get("stages", {})
        if "brainstem_reflex" in stages and stages["brainstem_reflex"].get(
            "event", {}
        ).get("triggered"):
            return "brainstem_reflex"
        if "sleep_gate" in stages:
            return "sleep_gate"
        if not stages.get("sensory_filter", {}).get("passed", True):
            return "sensory_filter"
        return "attention_path_without_model"

    @staticmethod
    def _personality_summary(big_five: Dict[str, Any]) -> str:
        labels = {
            "openness": "开放",
            "conscientiousness": "尽责",
            "extraversion": "外向",
            "agreeableness": "宜人",
            "neuroticism": "敏感",
        }
        ranked = sorted(
            (
                (key, float(value))
                for key, value in big_five.items()
                if key in labels and isinstance(value, (int, float))
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        return "、".join(f"高{labels[key]}" for key, _ in ranked[:2]) or "平衡人格"


class SessionRegistry:
    """进程内会话注册表，持久数据仍由 storage 负责。"""

    def __init__(self, storage: ElfieLabStorage, runtime_config_dir: str | None = None):
        self.storage = storage
        self.runtime_config_dir = runtime_config_dir
        self._sessions: Dict[str, ElfieLabSession] = {}
        self._lock = threading.Lock()

    def get(self, elfie_id: str) -> ElfieLabSession:
        with self._lock:
            if elfie_id not in self._sessions:
                self._sessions[elfie_id] = ElfieLabSession(
                    self.storage.get_elfie(elfie_id),
                    self.storage,
                    self.runtime_config_dir,
                )
            return self._sessions[elfie_id]
