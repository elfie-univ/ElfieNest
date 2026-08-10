from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional

from app.features.setup import SetupPrincipal, StoredSetupDraft, StoredSetupInstallation
from app.orchestration.setup_installation import (
    ConfirmSetupInstallationCommand,
    CreatedSetupOwner,
    SetupInstallationService,
)


class FakeWorkflowPorts:
    def __init__(self, *, phase: int = 2) -> None:
        self.draft = StoredSetupDraft(
            "owner", None, "hash", True, "qwen2.5:0.5b", 8, True, True, True, "locked"
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

    def read_draft(self) -> StoredSetupDraft:
        return self.draft

    def lock_draft(self) -> StoredSetupDraft:
        return self.draft

    def read_installation(self) -> StoredSetupInstallation:
        return self.install

    def create_first_owner(self, _draft: StoredSetupDraft) -> CreatedSetupOwner:
        return CreatedSetupOwner(1, "owner", None)

    def issue_session(self, _user_id: int) -> tuple[str, int]:
        return "session", 3600

    def mark_owner_completed(self, _user_id: int) -> None:
        pass

    def begin_or_resume(self) -> StoredSetupInstallation:
        self.install = replace(self.install, task_status="running")
        return self.install

    def start(self, _key: str, worker: Callable[[], None]) -> bool:
        self.worker = worker
        return True

    def ensure_installation(self, report: Callable[[str], None]) -> None:
        report("ollama.reuse")

    def ensure_model(self, _model_id: str, report: Callable[[str], None]) -> str:
        report("model.reuse")
        return "ollama_0001/qwen2.5:0.5b"

    def configured_model_reference(self, _model_id: str) -> str:
        return "ollama_0001/qwen2.5:0.5b"

    def ensure_emergency_food(self, _reference: str) -> None:
        self.actions.append("food")

    def set_bed_count(self, bed_count: int) -> None:
        self.actions.append(f"nest:{bed_count}")

    def report(self, *, phase: int, action_key: str, progress: int) -> None:
        self.actions.append(action_key)
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

    def recover_running(self, error: str) -> None:
        if self.install.task_status == "running":
            self.install = replace(
                self.install,
                task_status="failed",
                last_error=error,
            )


def _workflow(ports: FakeWorkflowPorts) -> SetupInstallationService:
    return SetupInstallationService(
        key="db",
        state=ports,
        accounts=ports,
        ollama=ports,
        providers=ports,
        food=ports,
        nest=ports,
        runner=ports,
    )


def test_confirm_schedules_external_actions_through_runner() -> None:
    ports = FakeWorkflowPorts()
    result = _workflow(ports).confirm(
        ConfirmSetupInstallationCommand(SetupPrincipal("setup", True), True)
    )
    assert result.session_token == "session"
    assert ports.worker is not None
    assert ports.actions == []
    ports.worker()
    assert ports.actions == [
        "ollama.reuse",
        "model.reuse",
        "food.emergency",
        "food",
        "nest.apply",
        "nest:8",
    ]


def test_resume_from_food_phase_does_not_repeat_ollama_or_model() -> None:
    ports = FakeWorkflowPorts(phase=4)
    _workflow(ports).confirm(
        ConfirmSetupInstallationCommand(SetupPrincipal("owner", True), True)
    )
    assert ports.worker is not None
    ports.worker()
    assert ports.actions == ["food.emergency", "food", "nest.apply", "nest:8"]


def test_recover_marks_orphaned_running_job_failed() -> None:
    ports = FakeWorkflowPorts()
    ports.install = replace(ports.install, task_status="running")
    _workflow(ports).recover()
    assert ports.install.task_status == "failed"
