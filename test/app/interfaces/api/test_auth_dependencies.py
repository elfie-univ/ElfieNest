from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.bootstrap import build_application_container
from app.infrastructure.persistence.store import init_db
from app.interfaces.api import elfie_food_routes, nest_routes, user_routes
from app.interfaces.api.v1.auth import get_current_user, require_manager
from test.app.interfaces.api._helpers import create_test_owner


class _Request:
    def __init__(self, token: str, accounts) -> None:
        self.cookies = {"session_token": token}
        self.app = SimpleNamespace(state=SimpleNamespace(accounts=accounts))


def test_all_http_routes_share_interface_auth_dependency_functions() -> None:
    assert user_routes.get_current_user is get_current_user
    assert elfie_food_routes.get_current_user is get_current_user
    assert nest_routes.require_manager is require_manager


def test_session_verification_uses_injected_application_container(tmp_path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first_db = str(first_root / "nest.db")
    second_db = str(second_root / "nest.db")
    init_db(first_db)
    init_db(second_db)
    owner_id = create_test_owner(first_db)
    create_test_owner(second_db)
    first_accounts = build_application_container(first_db).accounts
    second_accounts = build_application_container(second_db).accounts
    token = first_accounts.create_session(owner_id)

    with pytest.raises(HTTPException) as error:
        get_current_user(_Request(token, second_accounts))
    assert error.value.status_code == 401
