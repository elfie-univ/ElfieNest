from __future__ import annotations

from dataclasses import replace

import pytest

from app.features.setup import (
    GetSetupStatusQuery,
    SaveSetupNestDraftCommand,
    SaveSetupOfflineDraftCommand,
    SaveSetupOwnerDraftCommand,
    SaveSetupRemoteDraftCommand,
    SetupConflict,
    SetupForbidden,
    SetupPrincipal,
    SetupService,
    SetupValidationError,
    StoredOllamaObservation,
    StoredSetupDraft,
    StoredSetupInstallation,
    StoredSetupModelOption,
)


class FakeBoundary:
    def __init__(self) -> None:
        self.draft = StoredSetupDraft(
            None, None, None, None, None, 12, False, False, False, None
        )
        self.install = StoredSetupInstallation(
            None, "not_started", None, None, "idle", 0, None, None
        )
        self.owner = False
        self.platform = "darwin"
        self.ollama = StoredOllamaObservation("stopped", "http://127.0.0.1:11434", None)
        self.inspect_calls = 0
        self.validated: list[int] = []

    def read_installation(self) -> StoredSetupInstallation:
        return self.install

    def read_draft(self) -> StoredSetupDraft:
        return self.draft

    def has_owner(self) -> bool:
        return self.owner

    def inspect(self) -> StoredOllamaObservation:
        self.inspect_calls += 1
        return self.ollama

    def validate_bed_count(self, bed_count: int) -> int:
        self.validated.append(bed_count)
        if bed_count not in {7, 12}:
            raise ValueError("Nest policy rejected bed count")
        return bed_count

    def list_setup_models(self) -> tuple[StoredSetupModelOption, ...]:
        return (StoredSetupModelOption("qwen2.5:0.5b", "Qwen", 398, True),)

    def save_nest_draft(self, *, bed_count: int) -> StoredSetupDraft:
        self.draft = replace(self.draft, bed_count=bed_count, nest_configured=True)
        return self.draft

    def save_owner_draft(self, **_kwargs: object) -> StoredSetupDraft:
        return self.draft

    def save_offline_draft(self, **_kwargs: object) -> StoredSetupDraft:
        return self.draft

    def save_remote_draft(
        self,
        *,
        configured: bool,
        connection_id: str | None,
    ) -> StoredSetupDraft:
        self.draft = replace(
            self.draft,
            use_local_ollama=False,
            model_id=None,
            remote_configured=configured,
            remote_skipped=not configured,
            remote_connection_id=connection_id if configured else None,
        )
        return self.draft


def _service(boundary: FakeBoundary) -> SetupService:
    return SetupService(
        state=boundary,
        owners=boundary,
        ollama=boundary,
        nest_choices=boundary,
        models=boundary,
    )


def test_status_projects_existing_state_without_mutation() -> None:
    boundary = FakeBoundary()
    result = _service(boundary).get_status(GetSetupStatusQuery())
    assert result.current_step == 1
    assert result.draft.ollama_installed is False
    assert boundary.inspect_calls == 0
    assert boundary.draft.owner_account_id is None


def test_nest_choice_is_validated_by_the_narrow_nest_policy_port() -> None:
    boundary = FakeBoundary()
    result = _service(boundary).save_nest_draft(
        SetupPrincipal("setup", local=True),
        SaveSetupNestDraftCommand(bed_count=7),
    )
    assert boundary.validated == [7]
    assert result.draft.bed_count == 7


def test_draft_mutations_reject_non_local_setup_principal() -> None:
    boundary = FakeBoundary()
    with pytest.raises(SetupForbidden):
        _service(boundary).save_nest_draft(
            SetupPrincipal("setup", local=False),
            SaveSetupNestDraftCommand(bed_count=7),
        )


def test_linux_local_ollama_draft_waits_for_the_user_installed_service() -> None:
    boundary = FakeBoundary()
    boundary.platform = "linux"
    boundary.ollama = StoredOllamaObservation("absent", None, None)

    with pytest.raises(SetupValidationError, match="终端"):
        _service(boundary).save_offline_draft(
            SetupPrincipal("setup", local=True),
            SaveSetupOfflineDraftCommand(
                use_local_ollama=True,
                model_id="qwen2.5:0.5b",
            ),
        )


def test_local_owner_can_revise_non_account_choices_after_failed_install() -> None:
    boundary = FakeBoundary()
    boundary.owner = True
    boundary.install = replace(
        boundary.install,
        status="in_progress",
        install_step=3,
        task_status="failed",
    )
    boundary.draft = replace(
        boundary.draft,
        owner_configured=True,
        offline_configured=True,
        nest_configured=True,
        locked_at=None,
    )

    result = _service(boundary).save_nest_draft(
        SetupPrincipal("owner", local=True),
        SaveSetupNestDraftCommand(bed_count=7),
    )

    assert result.draft.bed_count == 7


def test_remote_food_decision_does_not_write_the_nest_default() -> None:
    boundary = FakeBoundary()
    boundary.owner = True
    boundary.draft = replace(boundary.draft, owner_configured=True)

    result = _service(boundary).save_remote_draft(
        SetupPrincipal("owner", local=True),
        SaveSetupRemoteDraftCommand(configured=True, connection_id="connection-openai"),
    )

    assert boundary.validated == []
    assert result.draft.remote_configured is True
    assert result.draft.remote_skipped is False
    assert result.draft.remote_connection_id == "connection-openai"
    assert result.draft.bed_count == 12
    assert result.draft.nest_configured is False


def test_remote_food_can_be_explicitly_skipped_and_still_completes_setup_choices() -> (
    None
):
    boundary = FakeBoundary()
    boundary.owner = True
    boundary.draft = replace(boundary.draft, owner_configured=True)

    result = _service(boundary).save_remote_draft(
        SetupPrincipal("owner", local=True),
        SaveSetupRemoteDraftCommand(configured=False, connection_id=None),
    )

    assert result.draft.remote_configured is False
    assert result.draft.remote_skipped is True
    assert result.draft.remote_connection_id is None
    assert result.current_step == 3


def test_existing_owner_account_cannot_be_rewritten_through_setup_draft() -> None:
    boundary = FakeBoundary()
    boundary.owner = True
    boundary.install = replace(boundary.install, task_status="failed")

    with pytest.raises(SetupConflict, match="Owner"):
        _service(boundary).save_owner_draft(
            SetupPrincipal("owner", local=True),
            SaveSetupOwnerDraftCommand("changed", None, "new-secret"),
        )
