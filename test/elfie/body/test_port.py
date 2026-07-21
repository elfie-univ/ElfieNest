from elfie.body import (
    BodyCapabilities,
    BodyCommand,
    BodyDescriptor,
    BodyEvent,
    BodyMode,
    BodyPort,
    BodyState,
    CommandResult,
    CommandStatus,
    HeadlessBody,
    LegacyBodyPort,
)


def test_headless_body_implements_body_port() -> None:
    body = HeadlessBody()

    assert isinstance(body, BodyPort)
    assert body.describe().mode.value == "headless"
    assert body.describe().capabilities.supports_sensor("vision") is True
    assert body.describe().capabilities.supports_action("tail.wag") is True


class MinimalBody:
    """证明 BodyPort 不要求调用方接触身体内部 sensors/actuators。"""

    body_id = "minimal"
    capabilities = BodyCapabilities()

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def describe(self) -> BodyDescriptor:
        return BodyDescriptor(
            body_id=self.body_id,
            mode=BodyMode.HEADLESS,
            display_name="Minimal Body",
            capabilities=self.capabilities,
        )

    def read_events(self) -> list[BodyEvent]:
        return []

    def execute(self, command: BodyCommand) -> CommandResult:
        return CommandResult(
            command_id=command.command_id,
            action=command.action,
            status=CommandStatus.COMPLETED,
        )

    def snapshot(self) -> BodyState:
        return BodyState(body_id=self.body_id, connected=True)

    def emergency_stop(self) -> CommandResult:
        return self.execute(BodyCommand(action="system.emergency_stop"))


def test_body_port_exposes_one_receive_and_one_control_entry() -> None:
    body = MinimalBody()

    assert isinstance(body, LegacyBodyPort)
    assert not isinstance(body, BodyPort)
    assert body.read_events() == []
    assert (
        body.execute(BodyCommand(action="face.blink")).status is CommandStatus.COMPLETED
    )
    assert not hasattr(body, "sensors")
    assert not hasattr(body, "actuators")
