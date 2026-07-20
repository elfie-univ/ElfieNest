from types import SimpleNamespace

from app.features.accounts.auth import create_session, get_current_user, require_owner
from app.interfaces.api import (
    camera_routes,
    food_policy_routes,
    nest_routes,
    owner_routes,
    user_routes,
)
from app.infrastructure.persistence.store import init_db


class _Request:
    def __init__(self, token: str, db_path: str):
        self.cookies = {"session_token": token}
        self.app = SimpleNamespace(state=SimpleNamespace(db_path=db_path))


def test_all_http_routes_share_auth_dependency_functions():
    """Given the API modules, Then user and owner dependencies have one implementation."""
    assert owner_routes.get_current_user is get_current_user
    assert user_routes.get_current_user is get_current_user
    assert camera_routes.get_current_user is get_current_user
    assert food_policy_routes.get_current_user is get_current_user
    assert nest_routes.get_current_user is get_current_user
    assert owner_routes.require_owner is require_owner
    assert nest_routes.require_owner is require_owner


def test_session_verification_uses_request_database(tmp_path):
    """Given two databases, When the token belongs to the other one, Then it is rejected."""
    first_db = str(tmp_path / "first.db")
    second_db = str(tmp_path / "second.db")
    init_db(first_db)
    init_db(second_db)
    from test.app.interfaces.api._helpers import create_test_owner

    owner_id = create_test_owner(first_db)
    create_test_owner(second_db)
    token = create_session(owner_id, first_db)

    try:
        get_current_user(_Request(token, second_db))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401
    else:
        raise AssertionError("session token 不得跨数据库复用")
