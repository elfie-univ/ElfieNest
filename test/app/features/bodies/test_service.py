"""Authorization and credential boundaries for external-body use-cases."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.features.accounts import AccountPrincipal
from app.features.bodies import (
    AuthenticateBodyCommand,
    BodiesForbidden,
    BodiesService,
    EnrollBodyCommand,
    ListBodiesQuery,
)
from app.features.bodies.ports import BodyCredentialRecord, BodyRecord


@dataclass
class FakeBodiesPort:
    records: list[BodyRecord] = field(default_factory=list)

    def list_for_elfie(
        self, *, owner_user_id: int, elfie_id: str
    ) -> tuple[BodyRecord, ...]:
        assert owner_user_id == 1
        assert elfie_id == "00000001"
        return tuple(self.records)

    def enroll(
        self,
        *,
        owner_user_id: int,
        elfie_id: str,
        display_name: str,
        body_type: str,
    ) -> BodyCredentialRecord:
        assert (owner_user_id, elfie_id) == (1, "00000001")
        assert (display_name, body_type) == ("客厅身体", "toy")
        return BodyCredentialRecord(body_id="body_one", secret="one-time-secret")

    def rotate(
        self, *, owner_user_id: int, elfie_id: str, body_id: str
    ) -> BodyCredentialRecord:
        raise AssertionError("not used")

    def revoke(self, *, owner_user_id: int, elfie_id: str, body_id: str) -> None:
        raise AssertionError("not used")

    def authenticate(self, bearer_token: str) -> BodyRecord:
        assert bearer_token == "body_one.one-time-secret"
        return BodyRecord(
            body_id="body_one",
            owner_elfie_id="00000001",
            display_name="客厅身体",
            body_type="toy",
            status="available",
            last_heartbeat_at=None,
        )

    def record_activity(self, body_id: str, activity: str) -> None:
        raise AssertionError("not used")


OWNER = AccountPrincipal(1, "owner", "owner", "manage")
MEMBER = AccountPrincipal(2, "member", "user", "chat")


def test_manager_enrollment_returns_secret_once_and_body_auth_has_minimal_identity() -> (
    None
):
    service = BodiesService(FakeBodiesPort())

    credential = service.enroll_body(
        OWNER,
        EnrollBodyCommand(
            elfie_id="00000001",
            display_name=" 客厅身体 ",
            body_type=" toy ",
        ),
    )
    principal = service.authenticate_body(
        AuthenticateBodyCommand(bearer_token=credential.bearer_token)
    )

    assert credential.bearer_token == "body_one.one-time-secret"
    assert principal.body_id == "body_one"
    assert principal.elfie_id == "00000001"


def test_member_cannot_use_body_administration() -> None:
    service = BodiesService(FakeBodiesPort())

    with pytest.raises(BodiesForbidden):
        service.list_bodies(MEMBER, ListBodiesQuery(elfie_id="00000001"))
