from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Tuple

from elfie.body.contracts import (
    BodyCommand,
    BodySensorEvent,
    CommandReceipt,
    EmergencyStopCommand,
)
from elfie.body.native.anatomy.base import SomaticAnatomy, VoiceProfile
from elfie.body.port import BodyPort
from elfie.brain.workspace.contracts import IngestReceipt
from elfie.brain.workspace.ports import PerceptionSink
from elfie.message_types import ElfieId
from elfie.nervous_system.actuators import (
    MotionActuator,
    MutterActuator,
    SpeechActuator,
)
from elfie.nervous_system.perception_bridge import BodyPerceptionBridge
from elfie.nervous_system.perception_normalizer import BodyPerceptionNormalizer
from elfie.nervous_system.physical_limits import PhysicalLimitsReflex
from elfie.nervous_system.reflex import SomaticReflexArc
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
        body_generation: int | None = None,
    ) -> None:
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
                body_generation=body_generation,
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
    def dropped_pending_count(self) -> int:
        return self._require_perception_bridge().dropped_pending_count

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

    def receive_body_event(
        self,
        event: BodySensorEvent,
    ) -> Tuple[IngestReceipt, ...]:
        """Process one Body event through reflex, filter, and Brain publish."""
        return self._require_perception_bridge().receive_body_event(event)

    def bind_body_port(
        self,
        body_port: Optional[BodyPort],
        *,
        body_generation: int | None = None,
    ) -> None:
        """Keep the immediate reflex target aligned with the active Body."""
        self._require_perception_bridge().bind_body_port(
            body_port,
            body_generation=body_generation,
        )

    def retry_pending(self) -> Tuple[IngestReceipt, ...]:
        """Retry reliable writes retained after Workspace backpressure."""
        return self._require_perception_bridge().retry_pending()

    def close_perception(self) -> None:
        """Close the Body-to-Brain input boundary."""
        self._require_perception_bridge().close()

    def _require_perception_bridge(self) -> BodyPerceptionBridge:
        bridge = self._perception_bridge
        if bridge is None:
            raise PerceptionBridgeNotConfiguredError(
                "typed perception bridge is not configured"
            )
        return bridge

    def execute_body_command(
        self,
        body: BodyPort,
        command: BodyCommand,
        *,
        now: datetime,
    ) -> Tuple[CommandReceipt, ...]:
        """Pass an already typed physical intent to the current Body boundary."""
        return body.execute(command, now=now)

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
        """把说话意图交给文本发言执行器。"""
        return self.speech_actuator.speak(text)

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
