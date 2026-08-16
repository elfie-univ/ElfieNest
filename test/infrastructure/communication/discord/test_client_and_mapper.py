from __future__ import annotations

import json
from threading import Event

import httpx

from infrastructure.communication.discord.client import (
    DiscordBotApiClient,
    DiscordBotInspector,
    DiscordGatewayClient,
)
from infrastructure.communication.discord.mapper import map_message_create


def test_inspector_and_rest_client_use_bot_identity_without_returning_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/users/@me"):
            return httpx.Response(
                200,
                json={
                    "id": "991",
                    "username": "elfienest_star",
                    "global_name": "星星",
                    "bot": True,
                },
            )
        if request.url.path.endswith("/gateway/bot"):
            return httpx.Response(200, json={"url": "wss://gateway.discord.gg"})
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"id": "17"})
        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(handler)
    inspector = DiscordBotInspector(
        lambda token: DiscordBotApiClient(token, transport=transport)
    )
    identity = inspector.inspect_bot("discord-super-secret")
    assert identity.bot_id == "991"
    assert identity.display_name == "星星"
    assert "discord-super-secret" not in repr(identity)

    client = DiscordBotApiClient("discord-super-secret", transport=transport)
    assert client.get_gateway_url() == "wss://gateway.discord.gg?v=10&encoding=json"
    assert client.send_message("1701", "你好").message_id == "17"


def test_mapper_separates_private_dms_from_guild_messages_and_bots() -> None:
    private = map_message_create(
        {
            "id": "42",
            "channel_id": "1701",
            "author": {
                "id": "701",
                "username": "owner_seven",
                "global_name": "七号主人",
                "bot": False,
            },
            "content": "你好",
        }
    )
    guild = map_message_create(
        {
            "id": "43",
            "channel_id": "1801",
            "guild_id": "999",
            "author": {"id": "701", "username": "owner_seven", "bot": False},
            "content": "公开消息",
        }
    )
    bot = map_message_create(
        {
            "id": "44",
            "channel_id": "1701",
            "author": {"id": "991", "username": "elfienest_star", "bot": True},
            "content": "回复",
        }
    )

    assert (
        private is not None
        and private.is_dm is True
        and private.discord_user_id == "701"
    )
    assert guild is not None and guild.is_dm is False and guild.guild_id == "999"
    assert bot is not None and bot.sender_is_bot is True
    assert map_message_create({"id": True}) is None


class _GatewayApi:
    def get_gateway_url(self) -> str:
        return "wss://gateway.discord.gg?v=10&encoding=json"

    def close(self) -> None:
        pass


class _Socket:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.messages = iter(
            [
                json.dumps({"op": 10, "d": {"heartbeat_interval": 100000}}),
                json.dumps(
                    {
                        "op": 0,
                        "t": "READY",
                        "s": 1,
                        "d": {
                            "session_id": "session-1",
                            "resume_gateway_url": "wss://resume.discord.gg",
                        },
                    }
                ),
                json.dumps(
                    {
                        "op": 0,
                        "t": "MESSAGE_CREATE",
                        "s": 2,
                        "d": {
                            "id": "42",
                            "channel_id": "1701",
                            "author": {"id": "701", "username": "owner_seven"},
                            "content": "你好",
                        },
                    }
                ),
            ]
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def recv(self):
        return next(self.messages)

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))


def test_gateway_identifies_with_dm_intent_and_delivers_message_event() -> None:
    socket = _Socket()
    stop = Event()
    ready: list[bool] = []
    received: list[dict[str, object]] = []
    gateway = DiscordGatewayClient(
        "discord-super-secret",
        api_client=_GatewayApi(),  # type: ignore[arg-type]
        connect_factory=lambda *_args, **_kwargs: socket,
    )

    gateway.run(
        stop,
        lambda event: (received.append(event), stop.set()),
        on_ready=lambda: ready.append(True),
    )

    assert ready == [True]
    assert received[0]["id"] == "42"
    identify = next(item for item in socket.sent if item.get("op") == 2)
    data = identify["d"]
    assert isinstance(data, dict)
    assert data["intents"] == 1 << 12
    assert data["token"] == "discord-super-secret"
