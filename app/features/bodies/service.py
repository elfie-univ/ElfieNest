"""Authorized product use-cases for one Elfie's external bodies."""

from __future__ import annotations

from app.features.accounts import AccountPrincipal, is_manager

from .errors import (
    BodiesForbidden,
    BodiesUnavailable,
    BodyConflict,
    BodyCredentialRejected,
    BodyInputInvalid,
    BodyNotFound,
)
from .models import (
    AuthenticateBodyCommand,
    BodyCredentialResult,
    BodyPrincipal,
    BodyResult,
    EnrollBodyCommand,
    ListBodiesQuery,
    RecordBodyActivityCommand,
    RevokeBodyCommand,
    RotateBodyCredentialCommand,
)
from .ports import (
    BodiesPort,
    BodiesPortConflict,
    BodiesPortCredentialRejected,
    BodiesPortError,
    BodiesPortNotFound,
    BodyCredentialRecord,
    BodyRecord,
)


class BodiesService:
    def __init__(self, persistence: BodiesPort) -> None:
        self._persistence = persistence

    def list_bodies(
        self, principal: AccountPrincipal, query: ListBodiesQuery
    ) -> tuple[BodyResult, ...]:
        self._require_manager(principal)
        elfie_id = self._elfie_id(query.elfie_id)
        try:
            records = self._persistence.list_for_elfie(
                owner_user_id=principal.user_id,
                elfie_id=elfie_id,
            )
        except BodiesPortNotFound as error:
            raise BodyNotFound("Elfie not found") from error
        except BodiesPortError as error:
            raise BodiesUnavailable("Bodies unavailable") from error
        return tuple(self._body_result(record) for record in records)

    def enroll_body(
        self, principal: AccountPrincipal, command: EnrollBodyCommand
    ) -> BodyCredentialResult:
        self._require_manager(principal)
        elfie_id = self._elfie_id(command.elfie_id)
        display_name = command.display_name.strip()
        body_type = command.body_type.strip()
        if not display_name:
            raise BodyInputInvalid("Body display name is required")
        if not body_type:
            raise BodyInputInvalid("Body type is required")
        try:
            credential = self._persistence.enroll(
                owner_user_id=principal.user_id,
                elfie_id=elfie_id,
                display_name=display_name,
                body_type=body_type,
            )
        except BodiesPortNotFound as error:
            raise BodyNotFound("Elfie not found") from error
        except BodiesPortError as error:
            raise BodiesUnavailable("Body enrollment unavailable") from error
        return self._credential_result(credential)

    def rotate_credential(
        self, principal: AccountPrincipal, command: RotateBodyCredentialCommand
    ) -> BodyCredentialResult:
        self._require_manager(principal)
        try:
            credential = self._persistence.rotate(
                owner_user_id=principal.user_id,
                elfie_id=self._elfie_id(command.elfie_id),
                body_id=self._body_id(command.body_id),
            )
        except BodiesPortNotFound as error:
            raise BodyNotFound("Body not found") from error
        except BodiesPortError as error:
            raise BodiesUnavailable("Credential rotation unavailable") from error
        return self._credential_result(credential)

    def revoke_body(
        self, principal: AccountPrincipal, command: RevokeBodyCommand
    ) -> None:
        self._require_manager(principal)
        try:
            self._persistence.revoke(
                owner_user_id=principal.user_id,
                elfie_id=self._elfie_id(command.elfie_id),
                body_id=self._body_id(command.body_id),
            )
        except BodiesPortNotFound as error:
            raise BodyNotFound("Body not found") from error
        except BodiesPortConflict as error:
            raise BodyConflict("Active bodies cannot be revoked") from error
        except BodiesPortError as error:
            raise BodiesUnavailable("Body revocation unavailable") from error

    def authenticate_body(self, command: AuthenticateBodyCommand) -> BodyPrincipal:
        try:
            record = self._persistence.authenticate(command.bearer_token)
        except BodiesPortCredentialRejected as error:
            raise BodyCredentialRejected("Body credential rejected") from error
        except BodiesPortError as error:
            raise BodiesUnavailable("Body authentication unavailable") from error
        return BodyPrincipal(body_id=record.body_id, elfie_id=record.owner_elfie_id)

    def record_activity(self, command: RecordBodyActivityCommand) -> None:
        try:
            self._persistence.record_activity(command.body_id, command.activity)
        except BodiesPortCredentialRejected as error:
            raise BodyCredentialRejected("Body credential rejected") from error
        except BodiesPortError as error:
            raise BodiesUnavailable("Body activity unavailable") from error

    @staticmethod
    def _require_manager(principal: AccountPrincipal) -> None:
        if not is_manager(principal.role):
            raise BodiesForbidden("Body administration requires a manager")

    @staticmethod
    def _elfie_id(value: str) -> str:
        normalized = value.strip()
        if len(normalized) != 8 or not normalized.isdigit():
            raise BodyInputInvalid("Invalid Elfie ID")
        return normalized

    @staticmethod
    def _body_id(value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("body_"):
            raise BodyInputInvalid("Invalid body ID")
        return normalized

    @staticmethod
    def _body_result(record: BodyRecord) -> BodyResult:
        return BodyResult(
            body_id=record.body_id,
            display_name=record.display_name,
            body_type=record.body_type,
            status=record.status,
            last_heartbeat_at=record.last_heartbeat_at,
        )

    @staticmethod
    def _credential_result(record: BodyCredentialRecord) -> BodyCredentialResult:
        return BodyCredentialResult(
            body_id=record.body_id,
            bearer_token=f"{record.body_id}.{record.secret}",
        )


__all__ = ("BodiesService",)
