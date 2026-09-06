"""Resumable first-run preparation workflow."""

from __future__ import annotations

import logging
from typing import Callable, Final

from app.features.nest_management import NestPortError
from app.features.setup import SetupPrincipal, StoredSetupDraft

from .errors import (
    SetupInstallationConflict,
    SetupInstallationForbidden,
    SetupInstallationInvalid,
    SetupInstallationUnavailable,
)
from .models import (
    CancelSetupInstallationCommand,
    CancelSetupInstallationResult,
    ConfirmSetupInstallationCommand,
    ConfirmSetupInstallationResult,
)
from .ports import (
    SetupAccountPort,
    SetupInstallationPortError,
    SetupInstallationRunnerPort,
    SetupInstallationStatePort,
    SetupNestPort,
    SetupRemotePreparationPort,
    SetupRuntimeReadinessPort,
)

logger = logging.getLogger("app.orchestration.setup_installation")
SETUP_INSTALLATION_TIMEOUT_SECONDS: Final[float] = 3600.0


class _SetupInstallationStopped(RuntimeError):
    """The persisted task is terminal, so the cooperative worker must stop."""


class SetupInstallationService:
    def __init__(
        self,
        *,
        key: str,
        state: SetupInstallationStatePort,
        accounts: SetupAccountPort,
        preparation: SetupRemotePreparationPort,
        nest: SetupNestPort,
        runtime: SetupRuntimeReadinessPort,
        runner: SetupInstallationRunnerPort,
        timeout_seconds: float = SETUP_INSTALLATION_TIMEOUT_SECONDS,
    ) -> None:
        self._key = key
        self._state = state
        self._accounts = accounts
        self._preparation = preparation
        self._nest = nest
        self._runtime = runtime
        self._runner = runner
        self._timeout_seconds = timeout_seconds

    def ensure_owner_session(self, principal: SetupPrincipal) -> tuple[str, int]:
        """Create the first Owner as soon as step one is saved.

        Setup keeps its short-lived local token until the installation is
        started, while the regular session lets the next step use the existing
        Provider and Food administration features.  The persisted owner id
        makes retries idempotent.
        """
        if not principal.local or principal.kind not in {"setup", "owner"}:
            raise SetupInstallationForbidden(
                "创建首个 Owner 仅允许本机 Setup 或 Owner principal"
            )
        try:
            draft = self._state.read_draft()
            if not draft.owner_configured or draft.password_hash is None:
                raise SetupInstallationInvalid("Setup Owner 草稿不完整")
            installation = self._state.read_installation()
            owner_user_id = installation.owner_user_id
            if owner_user_id is None:
                owner = self._accounts.find_owner()
                if owner is not None:
                    if owner.account_id != draft.owner_account_id:
                        raise SetupInstallationConflict(
                            "系统已有不同的 Owner，无法继续当前 Setup"
                        )
                else:
                    owner = self._accounts.create_first_owner(draft)
                owner_user_id = owner.user_id
                self._state.mark_owner_completed(owner_user_id)
            return self._accounts.issue_session(owner_user_id)
        except (
            SetupInstallationConflict,
            SetupInstallationForbidden,
            SetupInstallationInvalid,
        ):
            raise
        except SetupInstallationPortError as error:
            raise SetupInstallationUnavailable("Owner session unavailable") from error

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
            previous = self._state.read_installation()
            if draft.locked_at is None:
                draft = self._state.lock_draft()
            owner_user_id = previous.owner_user_id
            if owner_user_id is None:
                owner = self._accounts.find_owner()
                if owner is not None:
                    if owner.account_id != draft.owner_account_id:
                        raise SetupInstallationConflict(
                            "系统已有不同的 Owner，无法继续当前 Setup"
                        )
                else:
                    owner = self._accounts.create_first_owner(draft)
                owner_user_id = owner.user_id
                self._state.mark_owner_completed(owner_user_id)
            session_token, ttl = self._accounts.issue_session(owner_user_id)
            installation = self._state.begin_or_resume()
            if installation.task_status != "completed":
                started = self._runner.start(
                    self._key,
                    self._run_safely,
                    timeout_seconds=self._timeout_seconds,
                    on_timeout=self._timeout_safely,
                )
                if not started and previous.task_status != "running":
                    self._state.fail(
                        "installation.busy",
                        "上一个 Setup 安装任务仍在收尾，请稍后重试",
                    )
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

    def cancel(
        self, command: CancelSetupInstallationCommand
    ) -> CancelSetupInstallationResult:
        if not command.principal.local or command.principal.kind not in {
            "setup",
            "owner",
        }:
            raise SetupInstallationForbidden(
                "Setup 安装取消仅允许本机 Setup 或 Owner principal"
            )
        try:
            current = self._state.read_installation()
            if current.task_status != "running":
                raise SetupInstallationConflict("Setup 安装任务当前不可取消")
            self._runner.cancel(self._key)
            return CancelSetupInstallationResult(self._state.cancel_installation())
        except (SetupInstallationConflict, SetupInstallationForbidden):
            raise
        except SetupInstallationPortError as error:
            raise SetupInstallationUnavailable(
                "Setup cancellation unavailable"
            ) from error

    def recover(self) -> None:
        try:
            self._state.recover_running("应用重启前的 Setup 安装任务未完成")
        except SetupInstallationPortError as error:
            raise SetupInstallationUnavailable("Setup recovery unavailable") from error

    def _run_safely(self, cancelled: Callable[[], bool]) -> None:
        try:
            self._run(cancelled)
        except _SetupInstallationStopped:
            return
        except Exception as error:  # noqa: BLE001 - workflow boundary persists failure
            logger.exception("Setup installation worker failed")
            try:
                current = self._state.read_installation()
                if current.task_status != "running":
                    return
                self._state.fail(
                    current.install_action or "unknown", _safe_error(str(error))
                )
            except SetupInstallationPortError:
                logger.exception("Setup installation failure could not be persisted")

    def _run(self, cancelled: Callable[[], bool]) -> None:
        self._checkpoint(cancelled)
        draft = self._state.read_draft()
        if not draft.complete or draft.locked_at is None:
            raise SetupInstallationInvalid("Setup 安装草稿未锁定或不完整")
        current = self._state.read_installation()
        if current.task_status == "completed":
            return
        phase = current.install_step or 2
        owner = self._owner_for_installation(current.owner_user_id, draft)

        if phase <= 2:
            if draft.remote_configured:
                connection_id = draft.remote_connection_id
                if connection_id is None:
                    raise SetupInstallationInvalid("远程订阅连接记录缺失")
                self._reporter(2, cancelled)("model.validation.start")
                validation = self._preparation.validate_models(owner, connection_id)
                if validation.total <= 0 or validation.passed <= 0:
                    raise SetupInstallationInvalid("没有可用的远程模型")
                self._reporter(2, cancelled, progress=35)(
                    f"model.validation.complete:{validation.passed}:{validation.total}"
                )
            else:
                self._reporter(2, cancelled)("model.validation.skipped")
            self._checkpoint(cancelled)
            self._state.complete_phase(2)
            phase = 3

        if phase <= 3:
            if draft.remote_configured:
                connection_id = draft.remote_connection_id
                if connection_id is None:
                    raise SetupInstallationInvalid("远程订阅连接记录缺失")
                self._reporter(3, cancelled)("food.common.start")
                self._preparation.prepare_common_food(owner, connection_id)
                self._reporter(3, cancelled)("food.common.complete")
            else:
                self._reporter(3, cancelled)("food.common.skipped")
            self._checkpoint(cancelled)
            self._state.complete_phase(3)
            phase = 4

        if phase <= 4:
            self._reporter(4, cancelled)("nest.initialize")
            try:
                # The first-run Nest default is a persistence/runtime fact,
                # not a Setup form field.
                self._nest.initialize_bed_count(12)
            except NestPortError as error:
                raise SetupInstallationPortError(
                    "unable to initialize Nest configuration"
                ) from error
            self._reporter(4, cancelled, progress=80)("account.default_landing.start")
            self._accounts.set_default_landing_page(
                owner.user_id,
                "chat" if draft.remote_configured else "manage",
            )
            self._reporter(4, cancelled, progress=80)(
                "account.default_landing.complete"
            )
            self._checkpoint(cancelled)
            self._state.complete_phase(4)
            phase = 5

        if phase <= 5:
            self._reporter(5, cancelled)("runtime.ready.start")
            self._runtime.ensure_ready(cancelled)
            self._reporter(5, cancelled)("runtime.ready.complete")
            self._checkpoint(cancelled)
            self._state.complete_phase(5)

    def _owner_for_installation(
        self,
        owner_user_id: int | None,
        draft: StoredSetupDraft,
    ):
        if owner_user_id is None:
            raise SetupInstallationInvalid("Setup Owner 记录缺失")
        owner = self._accounts.find_owner()
        if owner is None or owner.user_id != owner_user_id:
            raise SetupInstallationInvalid("Setup Owner 无法读取")
        if getattr(draft, "owner_account_id", None) != owner.account_id:
            raise SetupInstallationConflict("Setup Owner 与当前草稿不一致")
        return owner

    def _reporter(
        self,
        phase: int,
        cancelled: Callable[[], bool],
        *,
        progress: int | None = None,
    ) -> Callable[[str], None]:
        phase_progress = {2: 20, 3: 45, 4: 70, 5: 90}[phase]

        def report(action_key: str) -> None:
            self._checkpoint(cancelled)
            self._state.report(
                phase=phase,
                action_key=action_key,
                progress=phase_progress if progress is None else progress,
            )

        return report

    def _timeout_safely(self) -> None:
        try:
            current = self._state.read_installation()
            if current.task_status == "running":
                self._state.fail(
                    "installation.timeout",
                    "Setup 安装超过一小时未完成，已停止等待；请检查网络或本机服务后重试",
                )
        except SetupInstallationPortError:
            logger.exception("Setup installation timeout could not be persisted")

    @staticmethod
    def _checkpoint(cancelled: Callable[[], bool]) -> None:
        if cancelled():
            raise _SetupInstallationStopped


def _safe_error(message: str) -> str:
    lowered = message.lower()
    if any(marker in lowered for marker in ("password", "token", "secret", "api key")):
        return "安装失败；敏感错误详情已隐藏。"
    return message.strip()[:512] or "Setup 安装失败"


__all__ = ("SetupInstallationService",)
