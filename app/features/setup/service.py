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
            observation = self._safe_ollama_observation()
        except SetupPortError as error:
            raise SetupUnavailable("Setup state unavailable") from error
        return self._status(install, draft, owner_exists, observation)

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
        self._require_open_local_setup(principal)
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
        self._require_open_local_setup(principal)
        try:
            bed_count = self._nest_choices.validate_bed_count(command.bed_count)
            self._state.save_nest_draft(bed_count=bed_count)
        except ValueError as error:
            raise SetupValidationError(str(error)) from error
        except SetupPortError as error:
            raise SetupUnavailable("Setup draft unavailable") from error
        return self.get_status(GetSetupStatusQuery())

    def _require_open_local_setup(self, principal: SetupPrincipal) -> None:
        if principal.kind != "setup" or not principal.local:
            raise SetupForbidden("首次设置仅允许本机 Setup principal")
        try:
            if self._owners.has_owner():
                raise SetupConflict("系统已有 Owner，Setup 草稿已关闭")
            if self._state.read_draft().locked_at is not None:
                raise SetupConflict("Setup 配置已锁定")
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

    def _safe_ollama_observation(self) -> StoredOllamaObservation:
        try:
            return self._ollama.inspect()
        except SetupPortError:
            return StoredOllamaObservation(state="absent", endpoint=None, version=None)

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
            4
            if draft.locked_at
            else (
                1
                if not owner_configured
                else 2
                if not draft.offline_configured
                else 3
                if not draft.nest_configured
                else 4
            )
        )
        configured = (
            owner_configured,
            draft.offline_configured,
            draft.nest_configured,
            complete,
        )
        names = (
            "创建 Owner 账号",
            "配置本地离线保障（可选）",
            "设置精灵巢床位",
            "确认并安装",
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
                if index == 4 and install.task_status == "failed"
                else None,
            )
            for index, value in enumerate(configured, start=1)
        )
        phase = {
            1: "owner",
            2: "ollama",
            3: "model",
            4: "emergency_food",
            5: "nest",
        }.get(install.install_step or 5, "nest")
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
            ),
            install=SetupInstallResult(
                phase=phase,  # type: ignore[arg-type]
                action_key=install.install_action or "idle",
                state=install.task_status,
                progress=install.task_progress,
                error_key="setup.install.failed"
                if install.task_status == "failed"
                else None,
            ),
            locked=draft.locked_at is not None,
        )


__all__ = ("SetupService",)
