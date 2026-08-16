"""Resumable five-phase first-install workflow."""

from __future__ import annotations

import logging
from typing import Callable

from .errors import (
    SetupInstallationConflict,
    SetupInstallationForbidden,
    SetupInstallationInvalid,
    SetupInstallationUnavailable,
)
from .models import ConfirmSetupInstallationCommand, ConfirmSetupInstallationResult
from .ports import (
    SetupAccountPort,
    SetupFoodPort,
    SetupInstallationPortError,
    SetupInstallationRunnerPort,
    SetupInstallationStatePort,
    SetupNestPort,
    SetupOllamaInstallPort,
    SetupOllamaTaskLease,
    SetupOllamaTaskLeaseFactory,
    SetupProviderPort,
)

logger = logging.getLogger("app.orchestration.setup_installation")


class SetupInstallationService:
    def __init__(
        self,
        *,
        key: str,
        state: SetupInstallationStatePort,
        accounts: SetupAccountPort,
        ollama: SetupOllamaInstallPort,
        providers: SetupProviderPort,
        food: SetupFoodPort,
        nest: SetupNestPort,
        runner: SetupInstallationRunnerPort,
        ollama_task_lease_factory: SetupOllamaTaskLeaseFactory | None = None,
    ) -> None:
        self._key = key
        self._state = state
        self._accounts = accounts
        self._ollama = ollama
        self._providers = providers
        self._food = food
        self._nest = nest
        self._runner = runner
        self._ollama_task_lease_factory = ollama_task_lease_factory

    def confirm(
        self, command: ConfirmSetupInstallationCommand
    ) -> ConfirmSetupInstallationResult:
        if not command.confirmed:
            raise SetupInstallationInvalid("必须明确确认 Setup 安装")
        if not command.principal.local or command.principal.kind not in {
            "setup",
            "owner",
        }:
            raise SetupInstallationForbidden(
                "Setup 安装仅允许本机 Setup 或 Owner principal"
            )
        try:
            draft = self._state.read_draft()
            if not draft.complete or draft.password_hash is None:
                raise SetupInstallationInvalid("Setup 配置尚未完成")
            if draft.locked_at is None:
                draft = self._state.lock_draft()
            owner = self._accounts.create_first_owner(draft)
            self._state.mark_owner_completed(owner.user_id)
            session_token, ttl = self._accounts.issue_session(owner.user_id)
            installation = self._state.begin_or_resume()
            if installation.task_status != "completed":
                self._runner.start(self._key, self._run_safely)
                installation = self._state.read_installation()
            return ConfirmSetupInstallationResult(
                installation=installation,
                session_token=session_token,
                session_ttl_seconds=ttl,
            )
        except (SetupInstallationInvalid, SetupInstallationForbidden):
            raise
        except SetupInstallationConflict:
            raise
        except SetupInstallationPortError as error:
            raise SetupInstallationUnavailable(
                "Setup installation unavailable"
            ) from error

    def recover(self) -> None:
        try:
            self._state.recover_running("应用重启前的 Setup 安装任务未完成")
        except SetupInstallationPortError as error:
            raise SetupInstallationUnavailable("Setup recovery unavailable") from error

    def _run_safely(self) -> None:
        try:
            self._run()
        except Exception as error:  # noqa: BLE001 - workflow boundary persists failure
            logger.exception("Setup installation worker failed")
            try:
                current = self._state.read_installation()
                self._state.fail(
                    current.install_action or "unknown", _safe_error(str(error))
                )
            except SetupInstallationPortError:
                logger.exception("Setup installation failure could not be persisted")

    def _run(self) -> None:
        draft = self._state.read_draft()
        if not draft.complete or draft.locked_at is None:
            raise SetupInstallationInvalid("Setup 安装草稿未锁定或不完整")
        current = self._state.read_installation()
        if current.task_status == "completed":
            return
        phase = current.install_step or 2
        model_reference = None
        task_lease: SetupOllamaTaskLease | None = None
        try:
            if phase <= 2:
                if draft.use_local_ollama:
                    task_lease = self._ollama.ensure_installation(self._reporter(2))
                else:
                    self._reporter(2)("ollama.skipped")
                self._state.complete_phase(2)
                phase = 3
            if draft.use_local_ollama and task_lease is None:
                if self._ollama_task_lease_factory is not None:
                    task_lease = self._ollama_task_lease_factory()
                    if task_lease is None:
                        raise SetupInstallationUnavailable(
                            "无法取得 Ollama Setup 任务租约"
                        )
            if phase <= 3:
                if draft.use_local_ollama:
                    if draft.model_id is None:
                        raise SetupInstallationInvalid("Setup 模型草稿缺失")
                    model_reference = self._ollama.ensure_model(
                        draft.model_id, self._reporter(3)
                    )
                else:
                    self._reporter(3)("model.skipped")
                self._state.complete_phase(3)
                phase = 4
            if phase <= 4:
                if draft.use_local_ollama:
                    if draft.model_id is None:
                        raise SetupInstallationInvalid("Setup 模型草稿缺失")
                    model_reference = (
                        model_reference
                        or self._providers.configured_model_reference(draft.model_id)
                    )
                    if model_reference is None:
                        raise SetupInstallationInvalid("Setup 模型连接记录缺失")
                    self._reporter(4)("food.emergency")
                    self._food.ensure_emergency_food(model_reference)
                else:
                    self._reporter(4)("food.skipped")
                self._state.complete_phase(4)
                phase = 5
            if phase <= 5:
                if draft.bed_count is None:
                    raise SetupInstallationInvalid("Setup 床位草稿缺失")
                self._reporter(5)("nest.apply")
                self._nest.set_bed_count(draft.bed_count)
                self._state.complete_phase(5)
        finally:
            if task_lease is not None:
                try:
                    task_lease.release()
                except Exception:  # noqa: BLE001 - cleanup is best effort at worker boundary
                    logger.exception("Setup Ollama task lease release failed")

    def _reporter(self, phase: int) -> Callable[[str], None]:
        progress = {2: 30, 3: 50, 4: 70, 5: 90}[phase]

        def report(action_key: str) -> None:
            self._state.report(phase=phase, action_key=action_key, progress=progress)

        return report


def _safe_error(message: str) -> str:
    lowered = message.lower()
    if any(marker in lowered for marker in ("password", "token", "secret", "api key")):
        return "安装失败；敏感错误详情已隐藏。"
    return message.strip()[:512] or "Setup 安装失败"


__all__ = ("SetupInstallationService",)
