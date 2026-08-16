"""Lifecycle-managed Discord Gateway workers and account reconciliation."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from threading import Event, RLock, Thread
from typing import Callable, Mapping, Optional

from app.features.communication.discord_port_models import DiscordRuntimeAccount
from app.features.communication.discord_ports import (
    DiscordAccountPortError,
    DiscordBotTokenRejected,
    DiscordBotTransportError,
)
from app.orchestration.message_delivery.discord_runtime_ports import (
    DiscordChannelRegistry,
    DiscordRuntimeAccountSource,
    DiscordRuntimeUpdateHandler,
)

from .channel import DiscordChannel, DiscordConnector, DiscordReplyHistory
from .client import DiscordBotApiClient, DiscordGatewayClient
from .mapper import map_message_create

logger = logging.getLogger("infrastructure.communication.discord.runner")


class DiscordGatewayWorker:
    """Process one bot's ordered Gateway stream and route only authorized DMs."""

    def __init__(
        self,
        runtime_account: DiscordRuntimeAccount,
        *,
        source: DiscordRuntimeAccountSource,
        handler: DiscordRuntimeUpdateHandler,
        registry: DiscordChannelRegistry,
        history: DiscordReplyHistory,
        client: DiscordBotApiClient,
        gateway: Optional[DiscordGatewayClient] = None,
    ) -> None:
        self._runtime_account = runtime_account
        self._source = source
        self._handler = handler
        self._registry = registry
        self._history = history
        self._client = client
        self._gateway = gateway or DiscordGatewayClient(
            runtime_account.bot_token, api_client=client
        )
        self._binding = runtime_account.binding
        self._channel: Optional[DiscordChannel] = None
        self._channel_attached = False
        self._closed = False

    def run(self, stop: Event) -> None:
        account = self._runtime_account.account
        try:

            def on_ready() -> None:
                self._source.mark_runtime_health(account.elfie_id, healthy=True)
                self._refresh_binding()
                self._ensure_channel()

            self._gateway.run(
                stop,
                self._handle_event,
                on_ready=on_ready,
            )
        except DiscordBotTokenRejected:
            self._source.mark_runtime_health(
                account.elfie_id,
                healthy=False,
                issue="credential_rejected",
            )
        except (DiscordAccountPortError, DiscordBotTransportError, OSError):
            self._source.mark_runtime_health(
                account.elfie_id,
                healthy=False,
                issue="discord_unavailable",
            )
        except Exception:
            logger.exception(
                "Unexpected Discord worker failure for Elfie %s", account.elfie_id
            )
            self._source.mark_runtime_health(
                account.elfie_id,
                healthy=False,
                issue="runtime_failed",
            )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        account = self._runtime_account.account
        if self._channel is not None:
            if self._channel_attached:
                self._registry.detach_communication_channel(
                    account.elfie_id, self._channel
                )
            self._channel.disconnect()
        else:
            self._gateway.close()

    def _handle_event(self, raw: Mapping[str, object]) -> None:
        update = map_message_create(raw)
        if update is None:
            return
        self._refresh_binding()
        self._ensure_channel()
        account = self._runtime_account.account
        pairing_code = None if self._binding is not None else _pairing_code(update.text)
        outcome = self._handler.handle(
            account,
            update,
            pairing_code=pairing_code,
        )
        if self._binding is None and pairing_code is not None:
            self._refresh_binding()
            self._ensure_channel()
        if outcome.reply_text:
            try:
                self._client.send_message(update.channel_id, outcome.reply_text)
            except (
                DiscordBotTokenRejected,
                DiscordBotTransportError,
                OSError,
                ValueError,
            ):
                self._source.mark_runtime_health(
                    account.elfie_id,
                    healthy=False,
                    issue="discord_reply_failed",
                )

    def _refresh_binding(self) -> None:
        for runtime in self._source.runtime_accounts():
            if runtime.account.elfie_id != self._runtime_account.account.elfie_id:
                continue
            self._binding = runtime.binding
            return

    def _ensure_channel(self) -> None:
        binding = self._binding
        if binding is None or self._channel_attached:
            return
        if self._channel is None:
            self._channel = DiscordChannel(
                DiscordConnector(self._client),
                elfie_id=self._runtime_account.account.elfie_id,
                bot_id=self._runtime_account.account.bot_id,
                conversation_id=binding.conversation_id,
                history=self._history,
            )
            self._channel.connect()
        self._channel_attached = self._registry.attach_communication_channel(
            self._runtime_account.account.elfie_id, self._channel
        )


@dataclass
class _WorkerHandle:
    signature: str
    worker: DiscordGatewayWorker
    stop: Event
    thread: Thread


class DiscordGatewayRuntime:
    """Reconcile configured Discord accounts under one lifecycle-owned supervisor."""

    def __init__(
        self,
        *,
        source: DiscordRuntimeAccountSource,
        handler: DiscordRuntimeUpdateHandler,
        registry: DiscordChannelRegistry,
        history: DiscordReplyHistory,
        client_factory: Optional[Callable[[str], DiscordBotApiClient]] = None,
        gateway_factory: Optional[
            Callable[[str, DiscordBotApiClient], DiscordGatewayClient]
        ] = None,
        reconcile_seconds: float = 1.0,
    ) -> None:
        self._source = source
        self._handler = handler
        self._registry = registry
        self._history = history
        self._client_factory = client_factory or DiscordBotApiClient
        self._gateway_factory = gateway_factory or (
            lambda token, client: DiscordGatewayClient(token, api_client=client)
        )
        self._reconcile_seconds = max(0.1, reconcile_seconds)
        self._stop = Event()
        self._supervisor: Optional[Thread] = None
        self._workers: dict[str, _WorkerHandle] = {}
        self._lock = RLock()

    def start(self) -> None:
        with self._lock:
            if self._supervisor is not None and self._supervisor.is_alive():
                return
            self._stop = Event()
            self._supervisor = Thread(
                target=self._supervise,
                name="elfienest-discord-supervisor",
                daemon=True,
            )
            self._supervisor.start()

    def stop(self) -> None:
        with self._lock:
            supervisor = self._supervisor
            self._supervisor = None
            self._stop.set()
            handles = tuple(self._workers.values())
            for handle in handles:
                handle.stop.set()
        if supervisor is not None:
            supervisor.join(timeout=12)
        for handle in handles:
            handle.thread.join(timeout=12)
            handle.worker.close()
        with self._lock:
            self._workers.clear()

    def _supervise(self) -> None:
        while not self._stop.is_set():
            try:
                self._reconcile()
            except Exception:
                logger.exception("Discord account reconciliation failed")
            self._stop.wait(self._reconcile_seconds)

    def _reconcile(self) -> None:
        desired = {
            runtime.account.elfie_id: runtime
            for runtime in self._source.runtime_accounts()
        }
        with self._lock:
            existing_ids = set(self._workers)
        for elfie_id in sorted(existing_ids - set(desired)):
            self._stop_worker(elfie_id)
        for elfie_id, runtime in sorted(desired.items()):
            signature = _runtime_signature(runtime)
            with self._lock:
                current = self._workers.get(elfie_id)
            if current is not None and current.signature == signature:
                continue
            if current is not None:
                self._stop_worker(elfie_id)
            self._start_worker(runtime, signature)

    def _start_worker(self, runtime: DiscordRuntimeAccount, signature: str) -> None:
        client = self._client_factory(runtime.bot_token)
        gateway = self._gateway_factory(runtime.bot_token, client)
        worker = DiscordGatewayWorker(
            runtime,
            source=self._source,
            handler=self._handler,
            registry=self._registry,
            history=self._history,
            client=client,
            gateway=gateway,
        )
        stop = Event()
        thread = Thread(
            target=worker.run,
            args=(stop,),
            name=f"elfienest-discord-{runtime.account.elfie_id}",
            daemon=True,
        )
        handle = _WorkerHandle(signature, worker, stop, thread)
        with self._lock:
            if self._stop.is_set():
                worker.close()
                return
            self._workers[runtime.account.elfie_id] = handle
        thread.start()

    def _stop_worker(self, elfie_id: str) -> None:
        with self._lock:
            handle = self._workers.pop(elfie_id, None)
        if handle is None:
            return
        handle.stop.set()
        handle.thread.join(timeout=12)
        handle.worker.close()


def _runtime_signature(runtime: DiscordRuntimeAccount) -> str:
    binding = runtime.binding
    material = "\0".join(
        (
            runtime.account.bot_id,
            hashlib.sha256(runtime.bot_token.encode()).hexdigest(),
            "" if binding is None else binding.conversation_id,
        )
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _pairing_code(text: Optional[str]) -> Optional[str]:
    value = text.strip() if isinstance(text, str) else ""
    return value or None


__all__ = ("DiscordGatewayRuntime", "DiscordGatewayWorker")
