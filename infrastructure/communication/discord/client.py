"""Sanitized Discord REST and Gateway clients for lifecycle-managed workers."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
from dataclasses import dataclass
from threading import Event
from typing import AsyncContextManager, Callable, Mapping, Optional, Protocol, Union

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from app.features.communication.discord_port_models import DiscordBotInspection
from app.features.communication.discord_ports import (
    DiscordBotTokenRejected,
    DiscordBotTransportError,
)

logger = logging.getLogger("infrastructure.communication.discord.client")

_API_BASE_URL = "https://discord.com/api/v10"
_GATEWAY_VERSION = 10
_DIRECT_MESSAGES_INTENT = 1 << 12
_MAX_MESSAGE_LENGTH = 2000


class _GatewaySocket(Protocol):
    async def recv(self) -> Union[str, bytes]: ...

    async def send(self, raw: str) -> None: ...


@dataclass(frozen=True)
class DiscordSentMessage:
    message_id: str


class DiscordBotApiClient:
    """Call only P0 endpoints and never include the Bot Token in errors."""

    def __init__(
        self,
        bot_token: str,
        *,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        if not bot_token:
            raise ValueError("Discord bot token is required")
        self._client = httpx.Client(
            base_url=_API_BASE_URL,
            transport=transport,
            headers={
                "Authorization": f"Bot {bot_token}",
                "User-Agent": "DiscordBot (ElfieNest, 0.1)",
                "Content-Type": "application/json",
            },
        )
        self._bot_token = bot_token

    def close(self) -> None:
        self._client.close()

    def get_me(self) -> Mapping[str, object]:
        result = self._call("GET", "/users/@me")
        if not isinstance(result, dict) or result.get("bot") is not True:
            raise DiscordBotTokenRejected("Discord rejected the bot credential")
        return result

    def get_gateway_url(self) -> str:
        result = self._call("GET", "/gateway/bot")
        if not isinstance(result, dict):
            raise DiscordBotTransportError("Discord returned an invalid gateway")
        value = result.get("url")
        if not isinstance(value, str) or not value:
            raise DiscordBotTransportError("Discord returned an invalid gateway")
        return f"{value}?v={_GATEWAY_VERSION}&encoding=json"

    def send_message(self, channel_id: str, text: str) -> DiscordSentMessage:
        if not channel_id or not text.strip():
            raise ValueError("Discord message requires a channel and text")
        if len(text) > _MAX_MESSAGE_LENGTH:
            raise ValueError("Discord message is too long")
        result = self._call(
            "POST",
            f"/channels/{channel_id}/messages",
            payload={"content": text},
        )
        if not isinstance(result, dict):
            raise DiscordBotTransportError("Discord returned an invalid message")
        message_id = result.get("id")
        if not isinstance(message_id, str) or not message_id:
            raise DiscordBotTransportError("Discord returned an invalid message")
        return DiscordSentMessage(message_id=message_id)

    def set_profile_avatar(self, content: bytes, media_type: str) -> None:
        """Set the bot's global profile avatar from the current Elfie headshot."""
        if not content:
            raise ValueError("Discord profile avatar cannot be empty")
        if not media_type.startswith("image/"):
            raise ValueError("Discord profile avatar must be an image")
        encoded = base64.b64encode(content).decode("ascii")
        result = self._call(
            "PATCH",
            "/users/@me",
            payload={"avatar": f"data:{media_type};base64,{encoded}"},
        )
        if not isinstance(result, dict):
            raise DiscordBotTransportError("Discord returned an invalid profile")

    def _call(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[Mapping[str, object]] = None,
        read_timeout: float = 15.0,
    ) -> object:
        try:
            response = self._client.request(
                method,
                path,
                json=None if payload is None else dict(payload),
                timeout=httpx.Timeout(
                    connect=5.0,
                    read=read_timeout,
                    write=5.0,
                    pool=5.0,
                ),
            )
            document = response.json()
        except (httpx.HTTPError, ValueError):
            raise DiscordBotTransportError("Discord request failed") from None
        if response.status_code in {401, 403}:
            raise DiscordBotTokenRejected("Discord rejected the bot credential")
        if response.status_code == 429 or response.status_code >= 500:
            raise DiscordBotTransportError("Discord is temporarily unavailable")
        if response.status_code < 200 or response.status_code >= 300:
            raise DiscordBotTransportError("Discord request failed")
        return document


class DiscordBotInspector:
    """Validate a Bot Token before it crosses into the local secret store."""

    def __init__(
        self,
        client_factory: Optional[Callable[[str], DiscordBotApiClient]] = None,
    ) -> None:
        self._client_factory = client_factory or DiscordBotApiClient

    def inspect_bot(self, bot_token: str) -> DiscordBotInspection:
        client = self._client_factory(bot_token)
        try:
            bot = client.get_me()
        finally:
            client.close()
        bot_id = bot.get("id")
        username = bot.get("username")
        global_name = bot.get("global_name")
        if (
            not isinstance(bot_id, str)
            or not bot_id.isdigit()
            or not isinstance(username, str)
            or not username
        ):
            raise DiscordBotTransportError("Discord returned an invalid bot identity")
        display_name = (
            global_name if isinstance(global_name, str) and global_name else username
        )
        return DiscordBotInspection(
            bot_id=bot_id,
            username=username,
            display_name=display_name,
        )


class DiscordBotAvatarUpdater:
    """One-shot profile update adapter used during account configuration."""

    def __init__(
        self,
        client_factory: Optional[Callable[[str], DiscordBotApiClient]] = None,
    ) -> None:
        self._client_factory = client_factory or DiscordBotApiClient

    def sync_avatar(self, bot_token: str, content: bytes, media_type: str) -> None:
        client = self._client_factory(bot_token)
        try:
            client.set_profile_avatar(content, media_type)
        finally:
            client.close()


class DiscordGatewayClient:
    """Maintain one Discord Gateway session and recover through Resume/Reconnect."""

    def __init__(
        self,
        bot_token: str,
        *,
        api_client: Optional[DiscordBotApiClient] = None,
        connect_factory: Optional[
            Callable[..., AsyncContextManager[_GatewaySocket]]
        ] = None,
    ) -> None:
        self._api_client = api_client or DiscordBotApiClient(bot_token)
        self._connect_factory = connect_factory or websockets.connect
        self._bot_token = bot_token

    def close(self) -> None:
        self._api_client.close()

    def run(
        self,
        stop: Event,
        on_event: Callable[[Mapping[str, object]], None],
        *,
        on_ready: Optional[Callable[[], None]] = None,
    ) -> None:
        asyncio.run(self._run(stop, on_event, on_ready=on_ready))

    async def _run(
        self,
        stop: Event,
        on_event: Callable[[Mapping[str, object]], None],
        *,
        on_ready: Optional[Callable[[], None]],
    ) -> None:
        session_id: Optional[str] = None
        resume_url: Optional[str] = None
        sequence: Optional[int] = None
        delay = 1.0
        while not stop.is_set():
            try:
                gateway_url = resume_url or self._api_client.get_gateway_url()
                should_resume = session_id is not None and sequence is not None
                outcome = await self._run_connection(
                    gateway_url,
                    stop,
                    on_event,
                    on_ready=on_ready,
                    session_id=session_id if should_resume else None,
                    resume_url=resume_url if should_resume else None,
                    sequence=sequence if should_resume else None,
                )
                sequence = outcome.sequence
                session_id = outcome.session_id
                resume_url = outcome.resume_url or resume_url
                delay = 1.0
                if outcome.reset_session:
                    session_id = None
                    resume_url = None
                    sequence = None
            except DiscordBotTokenRejected:
                raise
            except DiscordBotTransportError:
                if stop.is_set():
                    return
                logger.warning("Discord Gateway transport failed; retrying")
            except (ConnectionClosed, OSError, asyncio.TimeoutError):
                if stop.is_set():
                    return
                logger.warning("Discord Gateway disconnected; retrying")
            except Exception:
                if stop.is_set():
                    return
                logger.exception("Unexpected Discord Gateway failure; retrying")
            await asyncio.to_thread(stop.wait, delay)
            delay = min(30.0, delay * 2.0)

    async def _run_connection(
        self,
        gateway_url: str,
        stop: Event,
        on_event: Callable[[Mapping[str, object]], None],
        *,
        on_ready: Optional[Callable[[], None]],
        session_id: Optional[str],
        resume_url: Optional[str],
        sequence: Optional[int],
    ) -> _GatewayOutcome:
        del resume_url  # The resolved URL is already supplied by the caller.
        heartbeat_task: Optional[asyncio.Task[None]] = None
        current_sequence = sequence
        current_session = session_id
        current_resume_url: Optional[str] = None
        reset_session = False
        try:
            async with self._connect_factory(
                gateway_url,
                open_timeout=10,
                close_timeout=5,
                ping_interval=None,
            ) as socket:
                hello = await asyncio.wait_for(socket.recv(), timeout=15)
                hello_document = _json_object(hello)
                if hello_document.get("op") != 10:
                    raise DiscordBotTransportError("Discord Gateway hello was invalid")
                hello_data = hello_document.get("d")
                interval = _heartbeat_interval(hello_data)
                heartbeat_task = asyncio.create_task(_heartbeat(socket, interval, stop))
                if current_session is not None and current_sequence is not None:
                    await socket.send(
                        json.dumps(
                            {
                                "op": 6,
                                "d": {
                                    "token": self._bot_token,
                                    "session_id": current_session,
                                    "seq": current_sequence,
                                },
                            }
                        )
                    )
                else:
                    await socket.send(
                        json.dumps(
                            {
                                "op": 2,
                                "d": {
                                    "token": self._bot_token,
                                    "intents": _DIRECT_MESSAGES_INTENT,
                                    "properties": {
                                        "os": "elfienest",
                                        "browser": "elfienest",
                                        "device": "elfienest",
                                    },
                                },
                            }
                        )
                    )
                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(socket.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    document = _json_object(raw)
                    op = document.get("op")
                    raw_sequence = document.get("s")
                    if isinstance(raw_sequence, int) and not isinstance(
                        raw_sequence, bool
                    ):
                        current_sequence = raw_sequence
                    if op == 0:
                        event_name = document.get("t")
                        data = document.get("d")
                        if event_name == "READY" and isinstance(data, dict):
                            value = data.get("session_id")
                            if isinstance(value, str) and value:
                                current_session = value
                            resume = data.get("resume_gateway_url")
                            if isinstance(resume, str) and resume:
                                current_resume_url = (
                                    f"{resume}?v={_GATEWAY_VERSION}&encoding=json"
                                )
                            if on_ready is not None:
                                await asyncio.to_thread(on_ready)
                        elif event_name == "MESSAGE_CREATE" and isinstance(data, dict):
                            await asyncio.to_thread(on_event, data)
                    elif op == 1:
                        await socket.send(json.dumps({"op": 1, "d": current_sequence}))
                    elif op == 7:
                        break
                    elif op == 9:
                        reset_session = True
                        break
                    elif op == 11:
                        continue
        except ConnectionClosed as error:
            if error.code in {4004, 4013, 4014}:
                raise DiscordBotTokenRejected(
                    "Discord rejected the Bot Token or Gateway intents"
                ) from None
            raise
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
        return _GatewayOutcome(
            session_id=current_session,
            resume_url=current_resume_url,
            sequence=current_sequence,
            reset_session=reset_session,
        )


@dataclass(frozen=True)
class _GatewayOutcome:
    session_id: Optional[str]
    resume_url: Optional[str]
    sequence: Optional[int]
    reset_session: bool


async def _heartbeat(socket: _GatewaySocket, interval_ms: float, stop: Event) -> None:
    initial = max(0.1, interval_ms / 1000.0 * random.uniform(0.7, 1.0))
    await asyncio.sleep(initial)
    while not stop.is_set():
        await socket.send(json.dumps({"op": 1, "d": None}))
        await asyncio.sleep(max(0.1, interval_ms / 1000.0))


def _json_object(raw: object) -> dict[str, object]:
    if isinstance(raw, str):
        payload = raw
    elif isinstance(raw, (bytes, bytearray)):
        payload = bytes(raw).decode("utf-8")
    else:
        raise DiscordBotTransportError(
            "Discord Gateway returned invalid JSON"
        ) from None
    try:
        value = json.loads(payload)
    except (TypeError, UnicodeDecodeError, ValueError):
        raise DiscordBotTransportError(
            "Discord Gateway returned invalid JSON"
        ) from None
    if not isinstance(value, dict):
        raise DiscordBotTransportError("Discord Gateway returned invalid JSON")
    return value


def _heartbeat_interval(raw: object) -> float:
    if not isinstance(raw, dict):
        raise DiscordBotTransportError("Discord Gateway heartbeat was invalid")
    interval = raw.get("heartbeat_interval")
    if not isinstance(interval, (int, float)) or isinstance(interval, bool):
        raise DiscordBotTransportError("Discord Gateway heartbeat was invalid")
    return max(100.0, float(interval))


__all__ = (
    "DiscordBotApiClient",
    "DiscordBotAvatarUpdater",
    "DiscordBotInspector",
    "DiscordGatewayClient",
    "DiscordSentMessage",
)
