"""First-run decisions, draft validation and status projection."""

from __future__ import annotations

from app.features.accounts import (
    PasswordPolicyError,
    hash_password,
    validate_password_strength,
)

from .errors import (
    SetupConflict,
    SetupForbidden,
    SetupUnavailable,
    SetupValidationError,
)
from .models import (
    GetSetupStatusQuery,
    InspectSetupOllamaQuery,
    ListSetupModelsQuery,
    SaveSetupNestDraftCommand,
    SaveSetupOfflineDraftCommand,
    SaveSetupOwnerDraftCommand,
    SaveSetupRemoteDraftCommand,
    SetupDraftResult,
    SetupInstallResult,
    SetupModelOptionResult,
    SetupOllamaResult,
    SetupPrincipal,
    SetupStatusResult,
    SetupStepResult,
)
from .port_models import (
    StoredOllamaObservation,
    StoredSetupDraft,
    StoredSetupInstallation,
)
from .ports import (
    SetupModelCatalogPort,
    SetupNestChoicePort,
    SetupOllamaInspectionPort,
    SetupOwnerStatusPort,
    SetupPortError,
    SetupStatePort,
)


class SetupService:
    def __init__(
        self,
        *,
        state: SetupStatePort,
        owners: SetupOwnerStatusPort,
        ollama: SetupOllamaInspectionPort,
        nest_choices: SetupNestChoicePort,
        models: SetupModelCatalogPort,
    ) -> None:
        self._state = state
        self._owners = owners
        self._ollama = ollama
        self._nest_choices = nest_choices
        self._models = models

    def get_status(self, query: GetSetupStatusQuery) -> SetupStatusResult:
        _ = query
        try:
            install = self._state.read_installation()
            draft = self._state.read_draft()
            owner_exists = self._owners.has_owner()
        except SetupPortError as error:
            raise SetupUnavailable("Setup state unavailable") from error
        # The current Setup flow no longer configures local Ollama.  Keep the
        # legacy inspection endpoint available for compatibility, but do not
        # probe the local service on every status refresh.
        return self._status(
            install,
            draft,
            owner_exists,
            StoredOllamaObservation(state="absent", endpoint=None, version=None),
        )

    def list_models(
        self, query: ListSetupModelsQuery
    ) -> tuple[SetupModelOptionResult, ...]:
        _ = query
        try:
            return tuple(
                SetupModelOptionResult(**option.__dict__)
                for option in self._models.list_setup_models()
            )
        except SetupPortError as error:
            raise SetupUnavailable("Setup model catalog unavailable") from error

    def inspect_ollama(
        self, principal: SetupPrincipal, query: InspectSetupOllamaQuery
    ) -> SetupOllamaResult:
        _ = query
        self._require_ollama_inspection(principal)
        try:
            item = self._ollama.inspect()
        except SetupPortError as error:
            raise SetupUnavailable("Ollama inspection unavailable") from error
        return SetupOllamaResult(
            state=item.state,
            endpoint=item.endpoint,
            version=item.version,
            platform=self._ollama.platform,
        )

    def save_owner_draft(
        self, principal: SetupPrincipal, command: SaveSetupOwnerDraftCommand
    ) -> SetupStatusResult:
        self._require_open_local_setup(principal)
        account_id = command.account_id.strip()
        if not 3 <= len(account_id) <= 32:
            raise SetupValidationError("Setup Owner 账号长度必须为 3 到 32 个字符")
        try:
            draft = self._state.read_draft()
            password_hash = None
            if command.password is not None:
                validate_password_strength(command.password)
                password_hash = hash_password(command.password)
            elif draft.password_hash is None:
                raise SetupValidationError("首次保存 Owner 时必须设置密码")
            self._state.save_owner_draft(
                account_id=account_id,
                display_name=command.display_name,
                password_hash=password_hash,
            )
        except PasswordPolicyError as error:
            raise SetupValidationError(str(error)) from error
        except SetupPortError as error:
            raise SetupUnavailable("Setup draft unavailable") from error
        return self.get_status(GetSetupStatusQuery())

    def save_offline_draft(
        self, principal: SetupPrincipal, command: SaveSetupOfflineDraftCommand
    ) -> SetupStatusResult:
        self._require_editable_local_setup(principal)
        model_id = command.model_id if command.use_local_ollama else None
        if command.use_local_ollama and model_id is None:
            raise SetupValidationError("启用本地 Ollama 时必须选择模型")
        try:
            if model_id is not None and model_id not in {
                item.model_id for item in self._models.list_setup_models()
            }:
                raise SetupValidationError("Setup 只支持固定的本地模型")
            if command.use_local_ollama and self._ollama.platform == "linux":
                observation = self._ollama.inspect()
                if observation.state not in {"healthy", "stopped"}:
                    raise SetupValidationError(
                        "Linux 上请先在终端安装并启动 Ollama，然后重新检测"
                    )
            self._state.save_offline_draft(
                use_local_ollama=command.use_local_ollama, model_id=model_id
            )
        except SetupPortError as error:
            raise SetupUnavailable("Setup draft unavailable") from error
        return self.get_status(GetSetupStatusQuery())

    def save_nest_draft(
        self, principal: SetupPrincipal, command: SaveSetupNestDraftCommand
    ) -> SetupStatusResult:
        self._require_editable_local_setup(principal)
        try:
            bed_count = self._nest_choices.validate_bed_count(command.bed_count)
            self._state.save_nest_draft(bed_count=bed_count)
        except ValueError as error:
            raise SetupValidationError(str(error)) from error
        except SetupPortError as error:
            raise SetupUnavailable("Setup draft unavailable") from error
        return self.get_status(GetSetupStatusQuery())

    def save_remote_draft(
        self, principal: SetupPrincipal, command: SaveSetupRemoteDraftCommand
    ) -> SetupStatusResult:
        """Persist only the remote Food decision for the Setup workflow."""
        self._require_editable_local_setup(principal)
        connection_id = (
            command.connection_id.strip() if command.connection_id is not None else None
        )
        if command.configured and not connection_id:
            raise SetupValidationError("准备粮食时必须保存远程订阅")
        if not command.configured:
            connection_id = None
        try:
            self._state.save_remote_draft(
                configured=command.configured,
                connection_id=connection_id,
            )
        except ValueError as error:
            raise SetupValidationError(str(error)) from error
        except SetupPortError as error:
            raise SetupUnavailable("Setup draft unavailable") from error
        return self.get_status(GetSetupStatusQuery())

    def _require_open_local_setup(self, principal: SetupPrincipal) -> None:
        if not principal.local or principal.kind not in {"setup", "owner"}:
            raise SetupForbidden("首次设置仅允许本机 Setup principal")
        try:
            if self._owners.has_owner():
                raise SetupConflict("系统已有 Owner，Setup 草稿已关闭")
            if principal.kind != "setup":
                raise SetupForbidden("首次设置仅允许本机 Setup principal")
            if self._state.read_draft().locked_at is not None:
                raise SetupConflict("Setup 配置已锁定")
        except SetupPortError as error:
            raise SetupUnavailable("Setup state unavailable") from error

    def _require_editable_local_setup(self, principal: SetupPrincipal) -> None:
        if not principal.local or principal.kind not in {"setup", "owner"}:
            raise SetupForbidden("Setup 配置修改仅允许本机 Setup 或 Owner principal")
        try:
            owner_exists = self._owners.has_owner()
            installation = self._state.read_installation()
            draft = self._state.read_draft()
            if installation.status == "completed":
                raise SetupConflict("Setup 已完成，初始化草稿不可再修改")
            if draft.locked_at is not None:
                raise SetupConflict("Setup 配置已锁定")
            if owner_exists and principal.kind != "owner":
                raise SetupForbidden("已有 Owner 的 Setup 修改需要本机 Owner 权限")
            if not owner_exists and principal.kind != "setup":
                raise SetupForbidden("首次设置仅允许本机 Setup principal")
        except SetupPortError as error:
            raise SetupUnavailable("Setup state unavailable") from error

    @staticmethod
    def _require_owner(principal: SetupPrincipal) -> None:
        if principal.kind != "owner":
            raise SetupForbidden("需要 Owner 权限")

    @staticmethod
    def _require_ollama_inspection(principal: SetupPrincipal) -> None:
        if principal.kind == "owner":
            return
        if principal.kind == "setup" and principal.local:
            return
        raise SetupForbidden("Ollama 检测仅允许本机 Setup 或 Owner")

    @staticmethod
    def _status(
        install: StoredSetupInstallation,
        draft: StoredSetupDraft,
        owner_exists: bool,
        ollama: StoredOllamaObservation,
    ) -> SetupStatusResult:
        complete = install.status == "completed"
        owner_configured = draft.owner_configured or owner_exists
        current_step = (
            3
            if draft.locked_at or complete
            else 1
            if not owner_configured
            else 2
            if not draft.remote_decided
            else 3
        )
        configured = (
            owner_configured,
            draft.remote_decided,
            complete,
        )
        names = (
            "创建账号",
            "准备粮食",
            "准备完成",
        )
        steps = tuple(
            SetupStepResult(
                number=index,
                name=names[index - 1],
                status="completed"
                if value
                else "current"
                if index == current_step
                else "pending",
                retry_action="retry_install"
                if index == 3 and install.task_status in {"failed", "cancelled"}
                else None,
            )
            for index, value in enumerate(configured, start=1)
        )
        phase = {
            2: "model_validation",
            3: "common_food",
            4: "nest",
            5: "runtime",
        }.get(install.install_step or 2, "model_validation")
        return SetupStatusResult(
            need_setup=not complete,
            complete=complete,
            current_step=current_step,
            steps=steps,
            last_error=install.last_error,
            draft=SetupDraftResult(
                owner_account_id=draft.owner_account_id,
                display_name=draft.display_name,
                password_configured=draft.password_hash is not None,
                use_local_ollama=draft.use_local_ollama,
                ollama_installed=ollama.state
                in {"healthy", "stopped", "repair_required"},
                model_id=draft.model_id,
                bed_count=draft.bed_count,
                owner_configured=draft.owner_configured,
                offline_configured=draft.offline_configured,
                nest_configured=draft.nest_configured,
                locked_at=draft.locked_at,
                remote_configured=draft.remote_configured,
                remote_skipped=draft.remote_skipped,
                remote_connection_id=draft.remote_connection_id,
            ),
            install=SetupInstallResult(
                phase=phase,  # type: ignore[arg-type]
                action_key=install.install_action or "idle",
                state=install.task_status,
                progress=install.task_progress,
                error_key=(
                    "setup.install.failed"
                    if install.task_status == "failed"
                    else "setup.install.cancelled"
                    if install.task_status == "cancelled"
                    else None
                ),
            ),
            locked=draft.locked_at is not None,
        )


__all__ = ("SetupService",)
