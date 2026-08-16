from __future__ import annotations

from app.features.communication.telegram_port_models import (
    StoredTelegramAccount,
    StoredTelegramBinding,
    TelegramRuntimeAccount,
)
from app.orchestration.message_delivery import TelegramUpdateOutcome
from infrastructure.communication.telegram.client import TelegramSentMessage
from infrastructure.communication.telegram.runner import TelegramPollingWorker


def _runtime(binding: bool = True) -> TelegramRuntimeAccount:
    account = StoredTelegramAccount(
        elfie_id="00000001",
        bot_id="991",
        bot_username="elfienest_star_bot",
        display_name="星星",
        credential_ref="TOKEN_REF",
        configured_owner_user_id=7,
        status="active",
        last_checked_at="t0",
        issue=None,
    )
    paired = StoredTelegramBinding(
        elfie_id="00000001",
        telegram_user_id="701",
        telegram_chat_id="1701",
        telegram_username="owner_seven",
        display_name="七号主人",
        local_owner_user_id=7,
        local_owner_account_id="owner-seven",
        conversation_id="telegram:1701",
        bound_at="t0",
    )
    return TelegramRuntimeAccount(
        account, "991:secret", 42, paired if binding else None
    )


class Source:
    def __init__(self) -> None:
        self.cursors: list[int] = []
        self.health: list[tuple[bool, str | None]] = []

    def save_next_update_id(self, elfie_id: str, next_update_id: int) -> None:
        self.cursors.append(next_update_id)

    def mark_runtime_health(self, elfie_id: str, *, healthy: bool, issue=None) -> None:
        self.health.append((healthy, issue))


class Client:
    def __init__(self) -> None:
        self.offsets: list[int | None] = []
        self.sent: list[tuple[str, str]] = []
        self.closed = False

    def get_updates(self, *, offset, timeout_seconds=5):
        self.offsets.append(offset)
        return (
            {
                "update_id": 42,
                "message": {
                    "message_id": 9,
                    "chat": {"id": 1701, "type": "private"},
                    "from": {
                        "id": 701,
                        "is_bot": False,
                        "first_name": "七号主人",
                    },
                    "text": "你好",
                },
            },
        )

    def send_message(self, chat_id: str, text: str) -> TelegramSentMessage:
        self.sent.append((chat_id, text))
        return TelegramSentMessage(17)

    def close(self) -> None:
        self.closed = True


class Handler:
    def __init__(self, terminal: bool = True, reply_text: str | None = None) -> None:
        self.terminal = terminal
        self.reply_text = reply_text
        self.updates = []

    def handle(self, account, update, *, pairing_code=None):
        self.updates.append((account, update, pairing_code))
        return TelegramUpdateOutcome(self.terminal, self.reply_text)


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


def test_terminal_update_is_persisted_before_next_offset_is_used() -> None:
    source = Source()
    client = Client()
    handler = Handler(reply_text="收到")
    registry = Registry()
    worker = TelegramPollingWorker(
        _runtime(),
        source=source,
        handler=handler,
        registry=registry,
        history=History(),
        client=client,
        poll_timeout_seconds=5,
    )

    assert worker.poll_once() is True

    assert client.offsets == [42]
    assert client.sent == [("1701", "收到")]
    assert source.cursors == [43]
    assert source.health[-1] == (True, None)
    worker.close()
    assert registry.detached[0][0] == "00000001"


def test_retryable_update_does_not_advance_durable_cursor() -> None:
    source = Source()
    worker = TelegramPollingWorker(
        _runtime(),
        source=source,
        handler=Handler(terminal=False),
        registry=Registry(),
        history=History(),
        client=Client(),
        poll_timeout_seconds=5,
    )

    assert worker.poll_once() is False
    assert source.cursors == []
    worker.close()


def test_unpaired_worker_polls_for_start_without_registering_outbound_channel() -> None:
    registry = Registry()
    worker = TelegramPollingWorker(
        _runtime(binding=False),
        source=Source(),
        handler=Handler(),
        registry=registry,
        history=History(),
        client=Client(),
        poll_timeout_seconds=5,
    )

    worker.poll_once()

    assert registry.attached == []
    worker.close()
