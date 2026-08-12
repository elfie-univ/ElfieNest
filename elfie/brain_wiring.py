"""Private root wiring that connects Brain ports to one Elfie's siblings."""

from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Callable, Mapping

from elfie.body.port import BodyPort
from elfie.brain.context_source import BrainContextState
from elfie.brain.context_types import (
    BodyCapabilityDescriptor,
    ConnectedChannelDescriptor,
    EffectiveCapabilities,
)
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import HypothalamusEnergy
from elfie.brain.internal_output import ClosedInternalIntentSink, InternalIntentExecutor
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.brain.runtime import BrainRuntime
from elfie.brain.runtime_port import ModelPort
from elfie.brain.skills import SkillManager
from elfie.brain.tool_port import ToolPort
from elfie.communication import CommunicationHub
from elfie.communication.output_executor import CommunicationIntentExecutor
from elfie.communication.perception_adapter import CommunicationPerceptionAdapter
from elfie.message_types import ElfieId
from elfie.nervous_system import NervousSystem
from elfie.nervous_system.output_executor import NervousSystemIntentExecutor


class EffectiveCapabilityProjection:
    """Version the capabilities currently exposed by sibling authorities."""

    def __init__(
        self,
        *,
        current_body: Callable[[], BodyPort | None],
        communication: CommunicationHub,
    ) -> None:
        self._current_body = current_body
        self._communication = communication
        self._signature: tuple[str, ...] | None = None
        self._revision = 0
        self._lock = Lock()

    def current(
        self,
        captured_at: datetime,
        authorized_conversations: Mapping[str, tuple[str, ...]],
    ) -> EffectiveCapabilities:
        body = self._current_body()
        current_body = None
        signature: list[str] = []
        if body is not None:
            capabilities = body.capabilities
            current_body = BodyCapabilityDescriptor(
                body_id=body.body_id,
                capability_revision=capabilities.revision,
                sensors=tuple(sorted(capabilities.sensors)),
                actions=tuple(sorted(capabilities.actions)),
            )
            signature.extend(
                (
                    f"body:{body.body_id}",
                    f"body-revision:{capabilities.revision}",
                    f"body-connected:{body.snapshot_body(now=captured_at).connected}",
                )
            )
        channels = tuple(
            ConnectedChannelDescriptor(
                channel_id=channel.channel_id,
                account_id=channel.channel_id,
                capability_revision=1,
                content_kinds=("text",),
                authorized_conversation_ids=authorized_conversations.get(
                    channel.channel_id, ()
                ),
            )
            for channel in self._communication.router.list_channels()
            if channel.is_connected
        )
        for channel in channels:
            signature.append(f"channel:{channel.channel_id}")
            signature.extend(
                f"channel:{channel.channel_id}:conversation:{conversation_id}"
                for conversation_id in channel.authorized_conversation_ids
            )
        with self._lock:
            frozen = tuple(signature)
            if frozen != self._signature:
                self._revision += 1
                self._signature = frozen
            revision = self._revision
        return EffectiveCapabilities(
            revision=revision,
            captured_at=captured_at,
            current_body=current_body,
            connected_channels=channels,
        )


def assemble_brain_runtime(
    *,
    elfie_id: ElfieId,
    workspace: PerceptualWorkspace,
    memory: MemorySystem,
    emotion: EmotionSystem,
    homeostasis: HypothalamusEnergy,
    nervous_system: NervousSystem,
    communication: CommunicationHub,
    skills: SkillManager,
    current_body: Callable[[], BodyPort | None],
    clock: Callable[[], datetime],
    model_port: ModelPort,
    tool_port: ToolPort | None = None,
) -> BrainRuntime:
    """Assemble Brain once while keeping sibling adapters outside Brain ownership."""
    communication.bind_perception_adapter(CommunicationPerceptionAdapter(workspace))
    capabilities = EffectiveCapabilityProjection(
        current_body=current_body,
        communication=communication,
    )
    context = BrainContextState(
        memory=memory,
        capability_reader=capabilities.current,
        clock=clock,
    )
    return BrainRuntime(
        elfie_id=elfie_id,
        workspace=workspace,
        emotion=emotion,
        homeostasis=homeostasis,
        context=context,
        clock=clock,
        model_port=model_port,
        tool_port=tool_port,
        skills=skills,
        body_executor=NervousSystemIntentExecutor(
            nervous_system=nervous_system,
            current_body=current_body,
            clock=clock,
        ),
        message_executor=CommunicationIntentExecutor(
            hub=communication,
            elfie_id=elfie_id,
            capabilities=context,
            clock=clock,
        ),
        internal_executor=InternalIntentExecutor(ClosedInternalIntentSink()),
    )


__all__ = ("assemble_brain_runtime",)
