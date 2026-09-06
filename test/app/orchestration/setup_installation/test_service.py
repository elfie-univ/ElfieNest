from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional

from app.features.setup import SetupPrincipal, StoredSetupDraft, StoredSetupInstallation
from app.orchestration.setup_installation import (
    CancelSetupInstallationCommand,
    ConfirmSetupInstallationCommand,
    CreatedSetupOwner,
    SetupInstallationService,
    SetupModelValidationResult,
)


class FakeWorkflowPorts:
    def __init__(self, *, phase: int = 2) -> None:
        self.draft = StoredSetupDraft(
            owner_account_id="owner",
            display_name=None,
            password_hash="hash",
            use_local_ollama=False,
            model_id=None,
            bed_count=12,
            owner_configured=True,
            offline_configured=True,
            nest_configured=True,
            locked_at="locked",
            remote_configured=True,
            remote_skipped=False,
            remote_connection_id="connection-openai",
        )
        self.install = StoredSetupInstallation(
            1,
            "in_progress",
            phase,
            "pending",
            "failed",
            {2: 20, 3: 40, 4: 60, 5: 80}[phase],
            None,
            None,
        )
        self.actions: list[str] = []
        self.worker: Optional[Callable[[], None]] = None
        self.cancelled = False
        self.on_timeout: Optional[Callable[[], None]] = None
        self.owner_lookup: CreatedSetupOwner | None = CreatedSetupOwner(
            1, "owner", None
        )
        self.created_owner_calls = 0
        self.validation = SetupModelValidationResult(total=2, passed=2)
        self.preparation_actions: list[str] = []
        self.reported_progress: dict[str, int] = {}
        self.runtime_ready_calls = 0
        self.default_landing_page: str | None = None

    def read_draft(self) -> StoredSetupDraft:
        return self.draft

    def lock_draft(self) -> StoredSetupDraft:
        return self.draft

    def read_installation(self) -> StoredSetupInstallation:
        return self.install

    def create_first_owner(self, _draft: StoredSetupDraft) -> CreatedSetupOwner:
        self.created_owner_calls += 1
        return CreatedSetupOwner(1, "owner", None)

    def find_owner(self) -> CreatedSetupOwner | None:
        return self.owner_lookup

    def issue_session(self, _user_id: int) -> tuple[str, int]:
        return "session", 3600

    def set_default_landing_page(self, _user_id: int, page: str) -> None:
        self.default_landing_page = page

    def mark_owner_completed(self, _user_id: int) -> None:
        pass

    def begin_or_resume(self) -> StoredSetupInstallation:
        self.install = replace(self.install, task_status="running")
        return self.install

    def start(
        self,
        _key: str,
        worker: Callable[[Callable[[], bool]], None],
        *,
        timeout_seconds: float,
        on_timeout: Callable[[], None],
    ) -> bool:
        assert timeout_seconds > 0
        self.worker = lambda: worker(lambda: self.cancelled)
        self.on_timeout = on_timeout
        return True

    def cancel(self, _key: str) -> bool:
        self.cancelled = True
        return True

    def validate_models(
        self, owner: CreatedSetupOwner, connection_id: str
    ) -> SetupModelValidationResult:
        assert owner.user_id == 1
        assert connection_id == "connection-openai"
        self.preparation_actions.append("validate_models")
        return self.validation

    def prepare_common_food(self, owner: CreatedSetupOwner, connection_id: str) -> None:
        assert owner.user_id == 1
        assert connection_id == "connection-openai"
        self.preparation_actions.append("prepare_common_food")

    def ensure_ready(self, cancelled: Callable[[], bool]) -> None:
        assert not cancelled()
        self.runtime_ready_calls += 1

    def initialize_bed_count(self, bed_count: int) -> None:
        self.actions.append(f"nest:{bed_count}")

    def report(self, *, phase: int, action_key: str, progress: int) -> None:
        self.actions.append(action_key)
        self.reported_progress[action_key] = progress
        self.install = replace(
            self.install,
            install_step=phase,
            install_action=action_key,
            task_progress=progress,
        )

    def complete_phase(self, phase: int) -> StoredSetupInstallation:
        self.install = replace(
            self.install,
            install_step=phase + 1 if phase < 5 else 5,
            task_status="completed" if phase == 5 else "running",
        )
        return self.install

    def fail(self, action_key: str, error: str) -> None:
        self.install = replace(
            self.install,
            install_action=action_key,
            task_status="failed",
            last_error=error,
        )
        self.draft = replace(self.draft, locked_at=None)

    def cancel_installation(self) -> StoredSetupInstallation:
        self.install = replace(
            self.install,
            install_action="cancelled",
            task_status="cancelled",
            last_error=None,
        )
        self.draft = replace(self.draft, locked_at=None)
        return self.install

    def recover_running(self, error: str) -> None:
        if self.install.task_status == "running":
            self.install = replace(
                self.install,
                task_status="failed",
                last_error=error,
            )
            self.draft = replace(self.draft, locked_at=None)


def _workflow(ports: FakeWorkflowPorts) -> SetupInstallationService:
    return SetupInstallationService(
        key="db",
        state=ports,
        accounts=ports,
        preparation=ports,
        nest=ports,
        runtime=ports,
        runner=ports,
    )


def test_configured_setup_validates_models_prepares_only_common_food_and_waits_for_runtime() -> (
    None
):
    ports = FakeWorkflowPorts()
    result = _workflow(ports).confirm(
        ConfirmSetupInstallationCommand(SetupPrincipal("setup", True), True)
    )
    assert result.session_token == "session"
    assert ports.worker is not None
    assert ports.actions == []
    ports.worker()

    assert ports.preparation_actions == ["validate_models", "prepare_common_food"]
    assert ports.reported_progress["model.validation.complete:2:2"] == 35
    assert ports.runtime_ready_calls == 1
    assert ports.actions == [
        "model.validation.start",
        "model.validation.complete:2:2",
        "food.common.start",
        "food.common.complete",
        "nest.initialize",
        "nest:12",
        "account.default_landing.start",
        "account.default_landing.complete",
        "runtime.ready.start",
        "runtime.ready.complete",
    ]
    assert ports.install.task_status == "completed"
    assert ports.default_landing_page == "chat"


def test_partial_model_validation_continues_when_at_least_one_model_passes() -> None:
    ports = FakeWorkflowPorts()
    ports.validation = SetupModelValidationResult(total=2, passed=1)

    _workflow(ports).confirm(
        ConfirmSetupInstallationCommand(SetupPrincipal("owner", True), True)
    )
    assert ports.worker is not None
    ports.worker()

    assert "model.validation.complete:1:2" in ports.actions
    assert ports.preparation_actions == ["validate_models", "prepare_common_food"]
    assert ports.install.task_status == "completed"


def test_zero_usable_models_fails_before_common_food_and_runtime() -> None:
    ports = FakeWorkflowPorts()
    ports.validation = SetupModelValidationResult(total=2, passed=0)

    _workflow(ports).confirm(
        ConfirmSetupInstallationCommand(SetupPrincipal("owner", True), True)
    )
    assert ports.worker is not None
    ports.worker()

    assert ports.preparation_actions == ["validate_models"]
    assert ports.runtime_ready_calls == 0
    assert ports.install.task_status == "failed"
    assert ports.draft.locked_at is None


def test_skipped_remote_setup_skips_model_and_common_food_work() -> None:
    ports = FakeWorkflowPorts()
    ports.draft = replace(
        ports.draft,
        remote_configured=False,
        remote_skipped=True,
        remote_connection_id=None,
    )

    _workflow(ports).confirm(
        ConfirmSetupInstallationCommand(SetupPrincipal("owner", True), True)
    )
    assert ports.worker is not None
    ports.worker()

    assert ports.preparation_actions == []
    assert ports.actions == [
        "model.validation.skipped",
        "food.common.skipped",
        "nest.initialize",
        "nest:12",
        "account.default_landing.start",
        "account.default_landing.complete",
        "runtime.ready.start",
        "runtime.ready.complete",
    ]
    assert ports.install.task_status == "completed"
    assert ports.default_landing_page == "manage"


def test_resume_from_common_food_does_not_repeat_model_validation() -> None:
    ports = FakeWorkflowPorts(phase=3)
    _workflow(ports).confirm(
        ConfirmSetupInstallationCommand(SetupPrincipal("owner", True), True)
    )
    assert ports.worker is not None
    ports.worker()

    assert ports.preparation_actions == ["prepare_common_food"]
    assert ports.actions == [
        "food.common.start",
        "food.common.complete",
        "nest.initialize",
        "nest:12",
        "account.default_landing.start",
        "account.default_landing.complete",
        "runtime.ready.start",
        "runtime.ready.complete",
    ]


def test_owner_session_is_created_idempotently_when_step_one_is_saved() -> None:
    ports = FakeWorkflowPorts()
    ports.install = replace(ports.install, owner_user_id=None)
    ports.owner_lookup = None

    result = _workflow(ports).ensure_owner_session(SetupPrincipal("setup", True))

    assert result == ("session", 3600)
    assert ports.created_owner_calls == 1


def test_recover_marks_orphaned_running_job_failed() -> None:
    ports = FakeWorkflowPorts()
    ports.install = replace(ports.install, task_status="running")
    _workflow(ports).recover()
    assert ports.install.task_status == "failed"
    assert ports.draft.locked_at is None


def test_cancel_signals_worker_and_persists_unlocked_cancelled_state() -> None:
    ports = FakeWorkflowPorts()
    workflow = _workflow(ports)
    workflow.confirm(
        ConfirmSetupInstallationCommand(SetupPrincipal("setup", True), True)
    )
    assert ports.worker is not None

    result = workflow.cancel(
        CancelSetupInstallationCommand(SetupPrincipal("owner", True))
    )
    ports.worker()

    assert ports.cancelled is True
    assert result.installation.task_status == "cancelled"
    assert ports.draft.locked_at is None
    assert ports.actions == []


def test_timeout_marks_the_running_task_failed_and_unlocks_retry() -> None:
    ports = FakeWorkflowPorts()
    _workflow(ports).confirm(
        ConfirmSetupInstallationCommand(SetupPrincipal("setup", True), True)
    )
    assert ports.on_timeout is not None

    ports.on_timeout()

    assert ports.install.task_status == "failed"
    assert ports.install.install_action == "installation.timeout"
    assert ports.draft.locked_at is None
