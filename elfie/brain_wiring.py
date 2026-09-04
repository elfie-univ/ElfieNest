"""Private root wiring that connects Brain ports to one Elfie's siblings."""

from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Callable, Mapping

from elfie.body.port import BodyPort
from elfie.brain.activity.context import ActivityContextReader
from elfie.brain.activity.system import ActivityStorePort, InMemoryActivityStore
from elfie.brain.consolidation.system import CognitiveConsolidationSystem
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import EnergySystem
from elfie.brain.journal import BrainJournalPort
from elfie.brain.memory.memory_records import MaintenanceRequest
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.memory.model_food import ModelPortMemoryAdapter
from elfie.brain.motivation.system import MotivationSystem
from elfie.brain.orientation.system import OrientationSystem
from elfie.brain.reasoning.context_source import BrainContextProvider
from elfie.brain.reasoning.context_types import (
    BodyCapabilityDescriptor,
    CapabilityDescriptor,
    ConnectedChannelDescriptor,
    EffectiveCapabilities,
)
from elfie.brain.reasoning.conversation_context import ReasoningContextWorkspace
from elfie.brain.reasoning.embodied_control import EmbodiedInputMode
from elfie.brain.reasoning.internal_execution import NoOpExecutor
from elfie.brain.reasoning.memory_context import ReasoningMemoryBridge
from elfie.brain.reasoning.model_header import ReasoningConstitution
from elfie.brain.reasoning.model_port import ModelPort
from elfie.brain.reasoning.skills import SkillManager
from elfie.brain.reasoning.tool_port import ToolPort
from elfie.brain.runtime import BrainRuntime
from elfie.brain.selfhood.system import SelfhoodSystem
from elfie.brain.workspace.system import EventWorkspace
from elfie.communication import CommunicationHub
from elfie.communication.output_executor import CommunicationIntentExecutor
from elfie.communication.perception_adapter import CommunicationPerceptionAdapter
from elfie.message_types import ElfieId
from elfie.nervous_system import NervousSystem
from elfie.nervous_system.output_executor import NervousSystemIntentExecutor

# Stage-one default. Change this code switch to ``BRAIN`` when embodied
# Reasoning is ready to receive physical input.
DEFAULT_EMBODIED_INPUT_MODE = EmbodiedInputMode.MOCK


class EffectiveCapabilityProjection:
    """Version the capabilities currently exposed by sibling authorities."""

    def __init__(
        self,
        *,
        current_body: Callable[[], BodyPort | None],
        current_body_generation: Callable[[], int | None] | None = None,
        communication: CommunicationHub,
        world_capabilities: Callable[[], tuple[str, ...]] | None = None,
        world_capability_catalog: Callable[[], tuple[CapabilityDescriptor, ...]]
        | None = None,
    ) -> None:
        self._current_body = current_body
        self._current_body_generation = current_body_generation or (lambda: 1)
        self._communication = communication
        self._world_capabilities = world_capabilities or (lambda: ())
        self._world_capability_catalog = world_capability_catalog or (lambda: ())
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
            body_generation = self._current_body_generation() or 1
            all_body_actions = body.list_actions(model_visible=False)
            all_body_inputs = body.list_inputs(model_visible=False)
            # A legacy wildcard/raw adapter has no authoritative catalog.  Do
            # not turn its synthesized ``*`` entry into a fake dynamic catalog;
            # validation will use the raw wildcard fallback for that adapter.
            body_actions = (
                body.list_actions(model_visible=True)
                if capabilities.action_catalog
                else ()
            )
            body_inputs = (
                body.list_inputs(model_visible=True)
                if capabilities.input_catalog
                else ()
            )
            action_catalog = tuple(
                CapabilityDescriptor(
                    capability_id=descriptor.capability_id,
                    category="body",
                    description=descriptor.description,
                    argument_schema=descriptor.argument_schema,
                    return_schema=descriptor.return_schema,
                    registration_source=descriptor.registration_source,
                )
                for descriptor in body_actions
            )
            input_catalog = tuple(
                CapabilityDescriptor(
                    capability_id=descriptor.capability_id,
                    category="body",
                    description=descriptor.description,
                    argument_schema=descriptor.argument_schema,
                    return_schema=descriptor.return_schema,
                    registration_source=descriptor.registration_source,
                )
                for descriptor in body_inputs
            )
            current_body = BodyCapabilityDescriptor(
                body_id=body.body_id,
                body_generation=body_generation,
                capability_revision=capabilities.revision,
                sensors=tuple(
                    sorted(
                        {descriptor.capability_id for descriptor in all_body_inputs}
                        if capabilities.input_catalog
                        else capabilities.sensors
                    )
                ),
                actions=tuple(
                    sorted(
                        {descriptor.capability_id for descriptor in all_body_actions}
                        if capabilities.action_catalog
                        else capabilities.actions
                    )
                ),
                input_catalog=input_catalog,
                action_catalog=action_catalog,
            )
            signature.extend(
                (
                    f"body:{body.body_id}",
                    f"body-generation:{body_generation}",
                    f"body-revision:{capabilities.revision}",
                    f"body-connected:{body.snapshot_body(now=captured_at).connected}",
                )
            )
            signature.extend(
                "body-input-contract:" + descriptor.model_dump_json()
                for descriptor in input_catalog
            )
            signature.extend(
                "body-action-contract:" + descriptor.model_dump_json()
                for descriptor in action_catalog
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
        world_capabilities = tuple(sorted(set(self._world_capabilities())))
        world_catalog = tuple(
            descriptor
            for descriptor in self._world_capability_catalog()
            if descriptor.category == "world"
            and descriptor.capability_id in world_capabilities
        )
        all_catalog = (
            tuple(current_body.action_catalog) if current_body is not None else ()
        ) + world_catalog
        capability_catalog = tuple(
            sorted(
                {item.capability_id: item for item in all_catalog}.values(),
                key=lambda descriptor: descriptor.capability_id,
            )
        )
        signature.extend(f"world-capability:{item}" for item in world_capabilities)
        signature.extend(
            "capability-contract:" + descriptor.model_dump_json()
            for descriptor in capability_catalog
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
            world_capabilities=world_capabilities,
            capability_catalog=capability_catalog,
            connected_channels=channels,
        )


def assemble_brain_runtime(
    *,
    elfie_id: ElfieId,
    workspace: EventWorkspace,
    memory: MemorySystem,
    emotion: EmotionSystem,
    homeostasis: EnergySystem,
    selfhood: SelfhoodSystem,
    constitution: ReasoningConstitution,
    nervous_system: NervousSystem,
    communication: CommunicationHub,
    skills: SkillManager,
    current_body: Callable[[], BodyPort | None],
    current_body_generation: Callable[[], int | None] | None = None,
    clock: Callable[[], datetime],
    model_port: ModelPort,
    embodied_input_mode: EmbodiedInputMode = DEFAULT_EMBODIED_INPUT_MODE,
    world_capabilities: Callable[[], tuple[str, ...]] | None = None,
    world_capability_catalog: Callable[[], tuple[CapabilityDescriptor, ...]]
    | None = None,
    tool_port: ToolPort | None = None,
    activity_store: ActivityStorePort | None = None,
    journal_store: BrainJournalPort | None = None,
    restore_clock: Callable[[datetime], None] | None = None,
) -> BrainRuntime:
    """Assemble Brain once while keeping sibling adapters outside Brain ownership."""
    communication.bind_perception_adapter(CommunicationPerceptionAdapter(workspace))
    capabilities = EffectiveCapabilityProjection(
        current_body=current_body,
        current_body_generation=current_body_generation,
        communication=communication,
        world_capabilities=world_capabilities,
        world_capability_catalog=world_capability_catalog,
    )
    resolved_activity_store = activity_store or InMemoryActivityStore()
    initial_at = clock()
    memory_model = ModelPortMemoryAdapter(
        model_port,
        elfie_id=str(elfie_id),
        clock=clock,
    )

    def run_memory_maintenance(limit: int) -> Mapping[str, object]:
        """Route the scheduler through Memory's ordered maintenance boundary."""
        receipt = memory.run_maintenance(
            MaintenanceRequest(
                max_episodes=limit,
                worker_id="brain-cognitive-consolidation",
            ),
            model_port=memory_model,
        )
        return {
            "consolidated_count": len(receipt.consolidated_episode_ids),
            "knowledge_created": receipt.knowledge_created,
            "edges_created": receipt.edges_created,
            "patterns_created": receipt.patterns_created,
        }

    context = BrainContextProvider(
        memory=ReasoningMemoryBridge(memory),
        conversations=ReasoningContextWorkspace(),
        activities=ActivityContextReader(resolved_activity_store),
        capability_reader=capabilities.current,
        clock=clock,
        orientation=OrientationSystem(initial_at=initial_at),
        selfhood=selfhood,
        motivation=MotivationSystem(initial_at=initial_at),
        consolidation=CognitiveConsolidationSystem(
            pending_episode_ids=memory.pending_consolidation_ids,
            consolidate=run_memory_maintenance,
            initial_at=initial_at,
        ),
    )
    brain_runtime = BrainRuntime(
        elfie_id=elfie_id,
        workspace=workspace,
        emotion=emotion,
        homeostasis=homeostasis,
        context=context,
        constitution=constitution,
        memory=memory,
        clock=clock,
        model_port=model_port,
        embodied_input_mode=embodied_input_mode,
        tool_port=tool_port,
        skills=skills,
        body_executor=NervousSystemIntentExecutor(
            nervous_system=nervous_system,
            current_body=current_body,
            current_body_generation=current_body_generation,
            clock=clock,
        ),
        message_executor=CommunicationIntentExecutor(
            hub=communication,
            elfie_id=elfie_id,
            capabilities=context,
            clock=clock,
        ),
        internal_executor=NoOpExecutor(),
        activity_store=resolved_activity_store,
        journal_store=journal_store,
        restore_clock=restore_clock,
    )
    nervous_system.bind_perception_notifier(brain_runtime.notify_perception)
    return brain_runtime


__all__ = ("assemble_brain_runtime",)
