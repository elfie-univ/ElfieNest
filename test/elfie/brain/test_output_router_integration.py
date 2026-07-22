"""Real in-memory Body and Communication integration for OutputRouter."""

from elfie.body import HeadlessBody
from elfie.brain.decision_types import (
    DecisionIntent,
    ExpressionIntent,
    MotionIntent,
    SpeechIntent,
)
from elfie.brain.output_router import OutputRouter
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.communication import CommunicationHub
from elfie.communication.output_executor import CommunicationIntentExecutor
from elfie.nervous_system import NervousSystem
from elfie.nervous_system.output_executor import NervousSystemIntentExecutor
from test.elfie.brain.test_output_router import (
    ELFIE_ID,
    NOW,
    RecordingExecutor,
    StaticCapabilities,
    _base,
    _capabilities,
    _message,
    _plan,
)
from test.elfie.communication.test_output_executor import RecordingChannel


def test_real_body_and_communication_execute_one_multi_intent_plan() -> None:
    # Given: one real in-memory Body and one connected Communication channel.
    capabilities = StaticCapabilities(_capabilities())
    body = HeadlessBody(body_id="body-1")
    body.connect()
    nervous_system = NervousSystem()
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
    workspace = PerceptualWorkspace(ELFIE_ID)
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
    plan = _plan(physical + tuple(_message(index) for index in range(5)))

    # When: the asynchronous router accepts and finishes the complete plan.
    router.start()
    assert router.accept(plan) is True
    router.wait_for_turn(plan.turn_id, timeout=1)

    # Then: all real boundaries executed and every lifecycle transition returned.
    assert len(channel.sent) == 5
    assert [envelope.ordinal for envelope in channel.sent] == list(range(5))
    assert body.snapshot_body(now=NOW).last_status is not None
    assert len(router.receipts(plan.turn_id)) == 24
    assert workspace.metrics().reliable_event_count == 24
    router.stop()
    router.join()
