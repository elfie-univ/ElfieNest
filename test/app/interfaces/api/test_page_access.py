from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from infrastructure.persistence.nest_db.store import get_db, hash_password

from ._helpers import complete_test_setup


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def client(tmp_path: Path, db_path: str) -> TestClient:
    build_dir = _web_build(tmp_path)
    application = create_app(engine=None, db_path=db_path, web_build_dir=build_dir)
    with TestClient(application, base_url="http://127.0.0.1:8000") as test_client:
        yield test_client


def _web_build(tmp_path: Path) -> Path:
    build_dir = tmp_path / "build" / "web"
    assets = build_dir / "assets"
    assets.mkdir(parents=True)
    (build_dir / "index.html").write_text("app", encoding="utf-8")
    (assets / "app.js").write_text("app", encoding="utf-8")
    (build_dir / "manifest.json").write_text(
        """{
          "index.html": {"file": "assets/app.js"}
        }""",
        encoding="utf-8",
    )
    return build_dir


def _create_user(db_path: str, account_id: str, role: str) -> None:
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users (account_id, password_hash, role) VALUES (?, ?, ?)",
            (account_id, hash_password("pass123"), role),
        )
        connection.commit()


def _complete_setup(db_path: str) -> None:
    complete_test_setup(db_path)


def _login(client: TestClient, account_id: str) -> None:
    response = client.post(
        "/api/v1/auth/login", data={"account_id": account_id, "password": "pass123"}
    )
    assert response.status_code == 200


def test_pages_redirect_anonymous_users_to_login_with_safe_next(
    client: TestClient,
) -> None:
    # Given: no session.
    # When: an anonymous browser requests protected pages.
    # Then: a fresh installation always enters the setup wizard first.
    chat = client.get("/chat", follow_redirects=False)
    manage = client.get("/manage", follow_redirects=False)

    assert chat.status_code == 303
    assert chat.headers["location"] == "/setup"
    assert manage.status_code == 303
    assert manage.headers["location"] == "/setup"


def test_legacy_ws_configuration_resource_is_retired(client: TestClient) -> None:
    # The browser now uses the same-origin versioned WebSocket resource directly.
    response = client.get("/api/ws-config")

    assert response.status_code == 404


def test_login_discards_malformed_or_external_next(client: TestClient) -> None:
    # Given: no session and hostile next values.
    # When: the browser requests the login entry point.
    # Then: no open redirect target survives and setup owns first launch.
    external = client.get(
        "/login?next=https://attacker.invalid", follow_redirects=False
    )
    malformed = client.get("/login?next=//attacker.invalid", follow_redirects=False)

    assert external.status_code == 303
    assert external.headers["location"] == "/setup"
    assert malformed.status_code == 303
    assert malformed.headers["location"] == "/setup"


def test_anonymous_clients_receive_public_shell_assets_but_no_product_data(
    client: TestClient,
) -> None:
    # Given: a generated single-page application bundle.
    # When: an anonymous client asks for its static asset and protected data.
    shell_asset = client.get("/assets/app.js")
    conversations = client.get("/api/v1/me/conversations")

    # Then: JavaScript is public but data remains session-protected.
    assert shell_asset.status_code == 200
    assert conversations.status_code == 401


def test_asset_request_refreshes_the_manifest_after_a_frontend_rebuild(
    client: TestClient,
) -> None:
    """服务存活期间的新 Vite hash 不得让 React shell 失去 JS 资源。"""
    build_dir = client.app.state.web_build.directory
    (build_dir / "assets" / "app-new.js").write_text("new app", encoding="utf-8")
    (build_dir / "manifest.json").write_text(
        '{"index.html": {"file": "assets/app-new.js"}}', encoding="utf-8"
    )

    response = client.get("/assets/app-new.js")

    assert response.status_code == 200
    assert response.text == "new app"


def test_login_returns_only_an_allowed_post_login_page(
    client: TestClient, db_path: str
) -> None:
    # Given: an Owner account and both local and hostile next values.
    _create_user(db_path, "owner", "owner")

    # When: the same credentials are submitted through each login target.
    chat_next = client.post(
        "/api/v1/auth/login?next=/chat",
        data={"account_id": "owner", "password": "pass123"},
    )
    client.cookies.clear()
    manage_next = client.post(
        "/api/v1/auth/login?next=/manage",
        data={"account_id": "owner", "password": "pass123"},
    )
    client.cookies.clear()
    monitor_next = client.post(
        "/api/v1/auth/login?next=/monitor",
        data={"account_id": "owner", "password": "pass123"},
    )
    client.cookies.clear()
    hostile = client.post(
        "/api/v1/auth/login?next=https://attacker.invalid",
        data={"account_id": "owner", "password": "pass123"},
    )

    # Then: only Owner product pages may override the established default.
    assert chat_next.json()["landing_path"] == "/manage"
    assert manage_next.json()["landing_path"] == "/manage"
    assert monitor_next.json()["landing_path"] == "/monitor"
    assert hostile.json()["landing_path"] == "/manage"


def test_owner_chat_next_keeps_the_management_default_landing(
    client: TestClient,
    db_path: str,
) -> None:
    # Given: an Owner whose existing default landing is management.
    _create_user(db_path, "owner", "owner")

    # When: the login request carries the generic chat return target.
    response = client.post(
        "/api/v1/auth/login?next=/chat",
        data={"account_id": "owner", "password": "pass123"},
    )

    # Then: chat cannot override the Owner's established management default.
    assert response.json()["landing_path"] == "/manage"


def test_owner_and_user_receive_server_side_landing_routes(
    client: TestClient, db_path: str
) -> None:
    # Given: one Owner, one Admin and one ordinary user.
    _create_user(db_path, "owner", "owner")
    _create_user(db_path, "admin", "admin")
    _create_user(db_path, "alice", "user")
    _complete_setup(db_path)

    # When: each authenticated user opens the root and management page.
    _login(client, "owner")
    owner_root = client.get("/", follow_redirects=False)
    owner_manage = client.get("/manage", follow_redirects=False)
    owner_monitor = client.get("/monitor", follow_redirects=False)
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": ""})
    client.cookies.clear()
    _login(client, "alice")
    user_root = client.get("/", follow_redirects=False)
    user_manage = client.get("/manage", follow_redirects=False)
    user_monitor = client.get("/monitor", follow_redirects=False)

    # Then: the Owner defaults to manage; a user cannot enter Owner pages.
    assert owner_root.headers["location"] == "/manage"
    assert owner_manage.status_code == 200
    assert owner_monitor.status_code == 200
    assert "no-store" in owner_monitor.headers["cache-control"]
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": ""})
    client.cookies.clear()
    _login(client, "admin")
    admin_root = client.get("/", follow_redirects=False)
    admin_manage = client.get("/manage", follow_redirects=False)
    admin_monitor = client.get("/monitor", follow_redirects=False)
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": ""})
    client.cookies.clear()
    assert user_root.headers["location"] == "/chat"
    assert user_manage.headers["location"] == "/chat"
    assert user_monitor.headers["location"] == "/chat"
    assert admin_root.headers["location"] == "/manage"
    assert admin_manage.status_code == 200
    assert admin_monitor.status_code == 200


def test_monitor_route_redirects_setup_and_anonymous_requests_safely(
    client: TestClient,
    db_path: str,
) -> None:
    # Given: first a fresh installation, then a configured application without a session.
    before_setup = client.get("/monitor", follow_redirects=False)
    _create_user(db_path, "owner", "owner")
    _complete_setup(db_path)

    # When: the monitor route is requested at each lifecycle stage.
    anonymous = client.get("/monitor", follow_redirects=False)

    # Then: setup owns first run and anonymous users receive only a local login target.
    assert before_setup.status_code == 303
    assert before_setup.headers["location"] == "/setup"
    assert anonymous.status_code == 303
    assert anonymous.headers["location"] == "/login?next=/monitor"


def test_owner_manage_query_still_returns_the_react_shell(
    client: TestClient,
    db_path: str,
) -> None:
    _create_user(db_path, "owner", "owner")
    _login(client, "owner")

    response = client.get("/manage?mode=classic")

    assert response.status_code == 200
    assert response.text == "app"


def test_react_shell_pages_are_not_cached_by_the_browser(
    client: TestClient, db_path: str
) -> None:
    _create_user(db_path, "owner", "owner")
    _login(client, "owner")

    response = client.get("/manage")

    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["pragma"] == "no-cache"


def test_lan_rejects_unrecognized_host_and_origin(tmp_path: Path) -> None:
    # Given: a LAN-facing application with one explicitly recognized address.
    db_path = str(tmp_path / "nest.db")
    with patch(
        "app.interfaces.api.service_access.private_ipv4_addresses",
        return_value=("192.168.1.8",),
    ):
        application = create_app(engine=None, db_path=db_path, service_mode="lan")
        with TestClient(application) as client:
            # When: a forged Host or Origin reaches the public login page.
            bad_host = client.get("/login", headers={"Host": "attacker.invalid"})
            wrong_port = client.get("/login", headers={"Host": "192.168.1.8:9001"})
            bad_origin = client.get(
                "/login",
                headers={
                    "Host": "192.168.1.8:8000",
                    "Origin": "http://attacker.invalid",
                },
            )
            malformed_origin = client.get(
                "/login",
                headers={
                    "Host": "192.168.1.8:8000",
                    "Origin": "http://192.168.1.8:not-a-port",
                },
            )

    # Then: neither request is trusted.
    assert bad_host.status_code == 400
    assert wrong_port.status_code == 400
    assert bad_origin.status_code == 403
    assert malformed_origin.status_code == 403


def test_owner_mobile_access_exposes_only_active_lan_addresses(tmp_path: Path) -> None:
    # Given: an Owner session on a LAN-facing Core with one allowed address.
    db_path = str(tmp_path / "nest.db")
    with patch(
        "app.interfaces.api.service_access.private_ipv4_addresses",
        return_value=("192.168.1.8",),
    ):
        application = create_app(engine=None, db_path=db_path, service_mode="lan")
        with TestClient(application) as client:
            _create_user(db_path, "owner", "owner")
            headers = {"Host": "192.168.1.8:8000"}
            login = client.post(
                "/api/v1/auth/login",
                data={"account_id": "owner", "password": "pass123"},
                headers=headers,
            )

            # When: the Owner asks the current Core for its mobile access URL.
            response = client.get(
                "/api/v1/admin/runtime/mobile-access", headers=headers
            )
            legacy = client.get("/api/owner/mobile-access", headers=headers)

    # Then: the response advertises the real LAN root, never a loopback URL.
    assert login.status_code == 200
    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "urls": ["http://192.168.1.8:8000/"],
    }
    assert legacy.status_code == 404


def test_core_reads_the_packaged_web_build_directory_from_its_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_dir = _web_build(tmp_path)
    monkeypatch.setenv("ELFIENEST_WEB_BUILD_DIR", str(build_dir))
    application = create_app(engine=None, db_path=str(tmp_path / "nest.db"))
    with TestClient(application) as test_client:
        response = test_client.get("/login")

    assert response.status_code == 200
    assert response.text == "app"
