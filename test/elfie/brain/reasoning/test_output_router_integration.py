"""Real in-memory Body and Communication integration for OutputRouter."""

from elfie.body import HeadlessBody
from elfie.brain.reasoning.decision_types import (
    DecisionIntent,
    ExpressionIntent,
    MotionIntent,
    SpeechIntent,
)
from elfie.brain.reasoning.execution_router import OutputRouter
from elfie.brain.workspace.system import EventWorkspace
from elfie.communication import CommunicationHub
from elfie.communication.output_executor import CommunicationIntentExecutor
from elfie.nervous_system import NervousSystem
from elfie.nervous_system.output_executor import NervousSystemIntentExecutor
from test.elfie.brain.reasoning.test_output_router import (
    ELFIE_ID,
    NOW,
    RecordingExecutor,
    StaticCapabilities,
    _base,
    _capabilities,
    _embodied_decision,
    _plan,
)
from test.elfie.communication.test_output_executor import RecordingChannel


def test_real_body_executes_one_embodied_turn() -> None:
    # Given: one real in-memory Body behind the nervous-system executor.
    capabilities = StaticCapabilities(_capabilities())
    body = HeadlessBody(body_id="body-1")
    body.connect()
    workspace = EventWorkspace(ELFIE_ID)
    nervous_system = NervousSystem(
        perception_sink=workspace,
        elfie_id=ELFIE_ID,
        body_port=body,
        body_generation=1,
    )
    body_executor = NervousSystemIntentExecutor(
        nervous_system=nervous_system,
        current_body=lambda: body,
        clock=lambda: NOW,
    )
    hub = CommunicationHub(str(ELFIE_ID))
    channel = RecordingChannel()
    hub.register_channel(channel, connect=True)
    message_executor = CommunicationIntentExecutor(
        hub=hub,
        elfie_id=ELFIE_ID,
        capabilities=capabilities,
        clock=lambda: NOW,
    )
    router = OutputRouter(
        elfie_id=ELFIE_ID,
        capabilities=capabilities,
        perception_sink=workspace,
        body_executor=body_executor,
        message_executor=message_executor,
        internal_executor=RecordingExecutor(),
        clock=lambda: NOW,
    )
    physical: tuple[DecisionIntent, ...] = (
        SpeechIntent(type="speech", text="hello room", **_base("speech")),
        MotionIntent(type="motion", motion="walk", **_base("motion")),
        ExpressionIntent(
            type="expression",
            expression="happy",
            intensity=0.8,
            **_base("expression"),
        ),
    )
    plan = _plan(physical)

    # When: the asynchronous router accepts and finishes the complete plan.
    router.start()
    assert router.accept(_embodied_decision(plan)) is True
    router.wait_for_turn(plan.turn_id, timeout=1)

    # Then: only the embodied boundary executes.
    assert channel.sent == []
    assert body.snapshot_body(now=NOW).last_status is not None
    assert len(router.receipts(plan.turn_id)) == 9
    assert workspace.metrics().reliable_event_count == 3
    router.stop()
    router.join()
