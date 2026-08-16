"""Lifecycle-managed Telegram long-poll workers and account reconciliation."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from threading import Event, RLock, Thread
from typing import Callable, Optional

from app.features.communication.telegram_port_models import TelegramRuntimeAccount
from app.features.communication.telegram_ports import (
    TelegramAccountPortError,
    TelegramBotTokenRejected,
    TelegramBotTransportError,
)
from app.orchestration.message_delivery.telegram_runtime_ports import (
    ElfieCommunicationChannelRegistry,
    TelegramRuntimeAccountSource,
    TelegramRuntimeUpdateHandler,
)

from .channel import TelegramChannel, TelegramConnector, TelegramReplyHistory
from .client import TelegramBotApiClient
from .mapper import map_private_update, pairing_code, update_identifier

logger = logging.getLogger("infrastructure.communication.telegram.runner")


class TelegramPollingWorker:
    """Process one bot's ordered update stream and persist acknowledgement cursor."""

    def __init__(
        self,
        runtime_account: TelegramRuntimeAccount,
        *,
        source: TelegramRuntimeAccountSource,
        handler: TelegramRuntimeUpdateHandler,
        registry: ElfieCommunicationChannelRegistry,
        history: TelegramReplyHistory,
        client: TelegramBotApiClient,
        poll_timeout_seconds: int = 5,
    ) -> None:
        self._runtime_account = runtime_account
        self._source = source
        self._handler = handler
        self._registry = registry
        self._history = history
        self._client = client
        self._poll_timeout_seconds = max(1, min(30, poll_timeout_seconds))
        self._next_update_id = runtime_account.next_update_id
        self._channel: Optional[TelegramChannel] = None
        self._channel_attached = False
        self._closed = False

    def poll_once(self) -> bool:
        """Return False only when the earliest update must be retried."""
        self._ensure_channel()
        account = self._runtime_account.account
        updates = self._client.get_updates(
            offset=self._next_update_id,
            timeout_seconds=self._poll_timeout_seconds,
        )
        self._source.mark_runtime_health(account.elfie_id, healthy=True)
        for raw in sorted(
            updates,
            key=lambda item: update_identifier(item) or -1,
        ):
            raw_update_id = update_identifier(raw)
            if raw_update_id is None:
                continue
            update = map_private_update(raw)
            if update is None:
                self._commit_cursor(raw_update_id + 1)
                continue
            code = pairing_code(update.text, account.bot_username)
            outcome = self._handler.handle(account, update, pairing_code=code)
            if not outcome.terminal:
                return False
            if outcome.reply_text:
                try:
                    self._client.send_message(update.chat_id, outcome.reply_text)
                except (TelegramBotTokenRejected, TelegramBotTransportError):
                    self._source.mark_runtime_health(
                        account.elfie_id,
                        healthy=False,
                        issue="telegram_reply_failed",
                    )
            self._commit_cursor(raw_update_id + 1)
        return True

    def run(self, stop: Event, *, retry_delay_seconds: float = 2.0) -> None:
        account = self._runtime_account.account
        while not stop.is_set():
            try:
                progressed = self.poll_once()
                if not progressed:
                    stop.wait(retry_delay_seconds)
            except TelegramBotTokenRejected:
                self._source.mark_runtime_health(
                    account.elfie_id,
                    healthy=False,
                    issue="credential_rejected",
                )
                stop.wait(max(5.0, retry_delay_seconds))
            except (TelegramAccountPortError, TelegramBotTransportError):
                self._source.mark_runtime_health(
                    account.elfie_id,
                    healthy=False,
                    issue="telegram_unavailable",
                )
                stop.wait(retry_delay_seconds)
            except Exception:
                logger.exception(
                    "Unexpected Telegram worker failure for Elfie %s",
                    account.elfie_id,
                )
                self._source.mark_runtime_health(
                    account.elfie_id,
                    healthy=False,
                    issue="runtime_failed",
                )
                stop.wait(retry_delay_seconds)

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
            self._client.close()

    def _ensure_channel(self) -> None:
        binding = self._runtime_account.binding
        if binding is None or self._channel_attached:
            return
        if self._channel is None:
            self._channel = TelegramChannel(
                TelegramConnector(self._client),
                elfie_id=self._runtime_account.account.elfie_id,
                bot_id=self._runtime_account.account.bot_id,
                conversation_id=binding.conversation_id,
                history=self._history,
            )
            self._channel.connect()
        self._channel_attached = self._registry.attach_communication_channel(
            self._runtime_account.account.elfie_id,
            self._channel,
        )

    def _commit_cursor(self, next_update_id: int) -> None:
        self._source.save_next_update_id(
            self._runtime_account.account.elfie_id, next_update_id
        )
        self._next_update_id = next_update_id


@dataclass
class _WorkerHandle:
    signature: str
    worker: TelegramPollingWorker
    stop: Event
    thread: Thread


class TelegramLongPollingRuntime:
    """Reconcile configured bot accounts under one lifecycle-owned supervisor."""

    def __init__(
        self,
        *,
        source: TelegramRuntimeAccountSource,
        handler: TelegramRuntimeUpdateHandler,
        registry: ElfieCommunicationChannelRegistry,
        history: TelegramReplyHistory,
        client_factory: Optional[Callable[[str], TelegramBotApiClient]] = None,
        reconcile_seconds: float = 1.0,
        poll_timeout_seconds: int = 5,
    ) -> None:
        self._source = source
        self._handler = handler
        self._registry = registry
        self._history = history
        self._client_factory = client_factory or TelegramBotApiClient
        self._reconcile_seconds = max(0.1, reconcile_seconds)
        self._poll_timeout_seconds = poll_timeout_seconds
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
                name="elfienest-telegram-supervisor",
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
            supervisor.join(timeout=self._poll_timeout_seconds + 7)
        for handle in handles:
            handle.thread.join(timeout=self._poll_timeout_seconds + 7)
            handle.worker.close()
        with self._lock:
            self._workers.clear()

    def _supervise(self) -> None:
        while not self._stop.is_set():
            try:
                self._reconcile()
            except Exception:
                logger.exception("Telegram account reconciliation failed")
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

    def _start_worker(self, runtime: TelegramRuntimeAccount, signature: str) -> None:
        client = self._client_factory(runtime.bot_token)
        worker = TelegramPollingWorker(
            runtime,
            source=self._source,
            handler=self._handler,
            registry=self._registry,
            history=self._history,
            client=client,
            poll_timeout_seconds=self._poll_timeout_seconds,
        )
        stop = Event()
        thread = Thread(
            target=worker.run,
            args=(stop,),
            name=f"elfienest-telegram-{runtime.account.elfie_id}",
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
        handle.thread.join(timeout=self._poll_timeout_seconds + 7)
        handle.worker.close()


def _runtime_signature(runtime: TelegramRuntimeAccount) -> str:
    binding = runtime.binding
    material = "\0".join(
        (
            runtime.account.bot_id,
            hashlib.sha256(runtime.bot_token.encode()).hexdigest(),
            "" if binding is None else binding.conversation_id,
        )
    )
    return hashlib.sha256(material.encode()).hexdigest()


__all__ = ("TelegramLongPollingRuntime", "TelegramPollingWorker")
