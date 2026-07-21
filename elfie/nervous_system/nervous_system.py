from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from elfie.body.contracts import BodyId, BodySensorEvent, EmergencyStopCommand
from elfie.body.native.anatomy.base import SomaticAnatomy, VoiceProfile
from elfie.body.port import BodyPort
from elfie.body.types import BodyCommand, BodyEvent, CommandResult
from elfie.brain.perception_types import IngestReceipt
from elfie.brain.workspace_ports import PerceptionSink
from elfie.message_types import ElfieId
from elfie.nervous_system.actuators import (
    MotionActuator,
    MutterActuator,
    SpeechActuator,
)
from elfie.nervous_system.legacy_perception import adapt_legacy_body_events
from elfie.nervous_system.perception_bridge import BodyPerceptionBridge
from elfie.nervous_system.perception_normalizer import BodyPerceptionNormalizer
from elfie.nervous_system.physical_limits import PhysicalLimitsReflex
from elfie.nervous_system.reflex import SomaticReflexArc
from elfie.nervous_system.sensors import AudioSensor, EnvironmentSensor, VisionSensor
from elfie.nervous_system.signal_filter import SensoryDamSignalFilter


class PerceptionBridgeNotConfiguredError(RuntimeError):
    """Raised when typed Body input arrives before sink injection."""


class NervousSystem:
    """统一大脑与身体之间的感知、反射、校验和动作传递入口。"""

    def __init__(
        self,
        capabilities_config: Optional[Dict[str, Any]] = None,
        *,
        perception_sink: Optional[PerceptionSink] = None,
        elfie_id: Optional[ElfieId] = None,
        body_port: Optional[BodyPort] = None,
    ) -> None:
        self.vision_sensor = VisionSensor()
        self.audio_sensor = AudioSensor()
        self.environment_sensor = EnvironmentSensor()

        self.speech_actuator = SpeechActuator()
        self.motion_actuator = MotionActuator()
        self.mutter_actuator = MutterActuator()

        self.signal_filter = SensoryDamSignalFilter()
        self.physical_limits = PhysicalLimitsReflex(capabilities_config)
        self.reflex = SomaticReflexArc()
        self._perception_bridge: Optional[BodyPerceptionBridge] = None
        if perception_sink is not None and elfie_id is not None:
            self._perception_bridge = BodyPerceptionBridge(
                sink=perception_sink,
                elfie_id=elfie_id,
                normalizer=BodyPerceptionNormalizer(elfie_id, self.signal_filter),
                body_port=body_port,
            )
        elif perception_sink is not None or elfie_id is not None:
            raise PerceptionBridgeNotConfiguredError(
                "perception_sink and elfie_id must be injected together"
            )

    @property
    def pending_count(self) -> int:
        return self._require_perception_bridge().pending_count

    @property
    def filtered_count(self) -> int:
        return self._require_perception_bridge().filtered_count

    @property
    def urgent_revision(self) -> int:
        return self._require_perception_bridge().urgent_revision

    @property
    def last_reflex_command(self) -> Optional[EmergencyStopCommand]:
        return self._require_perception_bridge().last_reflex_command

    def receive_body_events(
        self,
        events: Iterable[BodySensorEvent],
    ) -> Tuple[IngestReceipt, ...]:
        """Publish a typed Body batch without flattening event identity."""
        return self._require_perception_bridge().receive(events)

    def receive(self, events: Iterable[BodyEvent]) -> Dict[str, Any]:
        """Deprecated raw Body adapter retained until the Task 14 migration."""
        return self.receive_legacy(events, body_id=BodyId("legacy-body"))

    def receive_body_event(
        self,
        event: BodySensorEvent,
    ) -> Tuple[IngestReceipt, ...]:
        """Process one Body event through reflex, filter, and Brain publish."""
        return self._require_perception_bridge().receive_body_event(event)

    def receive_legacy(
        self,
        events: Iterable[BodyEvent],
        *,
        body_id: BodyId,
    ) -> Dict[str, Any]:
        """Publish legacy Body events and return their deprecated raw view."""
        event_batch = tuple(events)
        self._mirror_legacy_sensors(event_batch)
        typed_events, raw = adapt_legacy_body_events(event_batch, body_id=body_id)
        if self._perception_bridge is not None:
            self.receive_body_events(typed_events)
        return raw

    def bind_body_port(self, body_port: Optional[BodyPort]) -> None:
        """Keep the immediate reflex target aligned with the active Body."""
        self._require_perception_bridge().bind_body_port(body_port)

    def _mirror_legacy_sensors(self, events: Tuple[BodyEvent, ...]) -> None:
        handlers: Dict[str, Callable[[BodyEvent, Dict[str, Any]], None]] = {
            "hearing": self._mirror_legacy_hearing,
            "touch": self._mirror_legacy_touch,
            "environment": self._mirror_legacy_environment,
        }
        for event in events:
            payload = dict(event.payload)
            handler = handlers.get(event.sensor)
            if handler is not None:
                handler(event, payload)

    def _mirror_legacy_hearing(
        self,
        event: BodyEvent,
        payload: Dict[str, Any],
    ) -> None:
        heard = str(
            payload.get("user_message")
            or payload.get("transcript")
            or payload.get("text")
            or ""
        ).strip()
        if heard:
            self.audio_sensor.receive_virtual_audio(heard, event.source)

    def _mirror_legacy_touch(
        self,
        _event: BodyEvent,
        payload: Dict[str, Any],
    ) -> None:
        self.environment_sensor.receive_tactile_pulse(
            impact_force=float(payload.get("impact_force", 0.0)),
            direction=str(payload.get("impact_direction", "none")),
            stroke_freq=float(payload.get("gentle_stroke", 0.0)),
        )

    def _mirror_legacy_environment(
        self,
        _event: BodyEvent,
        payload: Dict[str, Any],
    ) -> None:
        self.environment_sensor.update_from_godot_world(payload)

    def retry_pending(self) -> Tuple[IngestReceipt, ...]:
        """Retry reliable writes retained after Workspace backpressure."""
        return self._require_perception_bridge().retry_pending()

    def _require_perception_bridge(self) -> BodyPerceptionBridge:
        bridge = self._perception_bridge
        if bridge is None:
            raise PerceptionBridgeNotConfiguredError(
                "typed perception bridge is not configured"
            )
        return bridge

    def control(self, body: BodyPort, command: BodyCommand) -> CommandResult:
        """把已校验的语义动作交给当前身体执行。

        神经系统不判断 Godot 动画、电机或无界面记录的实现细节；对应身体根据
        自身 capabilities 决定执行或拒绝，并返回统一结果。
        """
        return body.execute(command)

    def filter_signals(self, raw_sensor_data: Dict[str, Any]) -> bool:
        """过滤重复或无价值的感知信号。"""
        return self.signal_filter.filter_noise(raw_sensor_data)

    def process_reflex(
        self,
        anatomy: SomaticAnatomy,
        tactile_sensor: Dict[str, Any],
        emotion_system: Any,
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        """处理可绕过认知层的即时身体反射。"""
        return self.reflex.process_sensory_impact(
            anatomy=anatomy,
            tactile_sensor=tactile_sensor,
            amygdala=emotion_system,
        )

    def validate_action(
        self, action_name: str, anatomy: SomaticAnatomy
    ) -> Dict[str, Any]:
        """根据当前身体形态校验动作是否能够执行。"""
        return self.physical_limits.intercept_and_validate(action_name, anatomy)

    def speak(self, text: str, voice_profile: Optional[VoiceProfile] = None) -> str:
        """把说话意图交给发声执行器。"""
        return self.speech_actuator.synthesize_speech(text, voice_profile)

    def drive(
        self,
        anatomy: SomaticAnatomy,
        action: str,
        speed: float = 1.0,
        elapsed_time: float = 0.0,
    ) -> Dict[str, float]:
        """把高阶动作意图转换为当前身体的关节驱动。"""
        return self.motion_actuator.translate_and_drive(
            anatomy=anatomy,
            action_intent=action,
            speed=speed,
            elapsed_time=elapsed_time,
        )

    def mutter(self, status: str) -> str:
        """把内部状态转换为精灵的碎碎念。"""
        return self.mutter_actuator.mutter(status)
