from __future__ import annotations

from threading import Event

from app.features.communication.discord_port_models import (
    DiscordRuntimeAccount,
    StoredDiscordAccount,
    StoredDiscordBinding,
)
from app.orchestration.message_delivery import DiscordUpdateOutcome
from infrastructure.communication.discord.client import DiscordSentMessage
from infrastructure.communication.discord.runner import DiscordGatewayWorker


def _runtime(binding: StoredDiscordBinding | None = None) -> DiscordRuntimeAccount:
    return DiscordRuntimeAccount(
        StoredDiscordAccount(
            "00000001",
            "991",
            "elfienest_star",
            "星星",
            "TOKEN_REF",
            7,
            "active",
            "t0",
            None,
        ),
        "discord-secret-token",
        binding,
    )


class Source:
    def __init__(self, runtime: DiscordRuntimeAccount) -> None:
        self.runtime = runtime
        self.health: list[tuple[bool, str | None]] = []

    def runtime_accounts(self):
        return (self.runtime,)

    def mark_runtime_health(self, elfie_id: str, *, healthy: bool, issue=None):
        self.health.append((healthy, issue))


class Client:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.closed = False

    def send_message(self, channel_id: str, text: str) -> DiscordSentMessage:
        self.sent.append((channel_id, text))
        return DiscordSentMessage("reply-17")

    def close(self) -> None:
        self.closed = True


class Gateway:
    def __init__(self, event: dict[str, object]) -> None:
        self.event = event
        self.closed = False

    def run(self, stop: Event, on_event, *, on_ready=None):
        if on_ready is not None:
            on_ready()
        on_event(self.event)
        stop.set()

    def close(self) -> None:
        self.closed = True


class Handler:
    def __init__(self, outcome: DiscordUpdateOutcome, source: Source) -> None:
        self.outcome = outcome
        self.source = source

    def handle(self, account, update, *, pairing_code=None):
        if pairing_code is not None and self.outcome.reply_text:
            self.source.runtime = DiscordRuntimeAccount(
                self.source.runtime.account,
                self.source.runtime.bot_token,
                StoredDiscordBinding(
                    "00000001",
                    "701",
                    "1701",
                    "owner_seven",
                    "七号主人",
                    7,
                    "owner-seven",
                    "discord:1701",
                    "t0",
                ),
            )
        return self.outcome


class Registry:
    def __init__(self) -> None:
        self.attached = []
        self.detached = []

    def attach_communication_channel(self, elfie_id, channel):
        self.attached.append((elfie_id, channel))
        return True

    def detach_communication_channel(self, elfie_id, channel):
        self.detached.append((elfie_id, channel))


class History:
    def record_reply(self, **kwargs):
        pass


def _raw() -> dict[str, object]:
    return {
        "id": "42",
        "channel_id": "1701",
        "author": {
            "id": "701",
            "username": "owner_seven",
            "global_name": "七号主人",
            "bot": False,
        },
        "content": "pairing-code",
    }


def test_unpaired_gateway_event_can_complete_pairing_then_attach_channel() -> None:
    source = Source(_runtime())
    client = Client()
    registry = Registry()
    worker = DiscordGatewayWorker(
        source.runtime,
        source=source,
        handler=Handler(DiscordUpdateOutcome(True, "配对成功"), source),
        registry=registry,
        history=History(),
        client=client,  # type: ignore[arg-type]
        gateway=Gateway(_raw()),  # type: ignore[arg-type]
    )

    worker.run(Event())
    worker.close()

    assert client.sent == [("1701", "配对成功")]
    assert len(registry.attached) == 1
    assert len(registry.detached) == 1
    assert client.closed is True


def test_bound_public_event_is_not_authorized_by_worker_handler() -> None:
    binding = StoredDiscordBinding(
        "00000001",
        "701",
        "1701",
        "owner_seven",
        "七号主人",
        7,
        "owner-seven",
        "discord:1701",
        "t0",
    )
    source = Source(_runtime(binding))
    registry = Registry()
    worker = DiscordGatewayWorker(
        source.runtime,
        source=source,
        handler=Handler(DiscordUpdateOutcome(True), source),
        registry=registry,
        history=History(),
        client=Client(),  # type: ignore[arg-type]
        gateway=Gateway({**_raw(), "guild_id": "999"}),  # type: ignore[arg-type]
    )
    worker.run(Event())
    worker.close()

    assert len(registry.attached) == 1
