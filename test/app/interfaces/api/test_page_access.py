from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.persistence.store import get_db, hash_password
from app.interfaces.api.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_path = str(tmp_path / "nest.db")
    build_dir = _web_build(tmp_path)
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(
            engine=None, db_path=db_path, ws_port=9876, web_build_dir=build_dir
        )
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


def _create_user(client: TestClient, username: str, role: str) -> None:
    with get_db(client.app.state.db_path) as connection:
        connection.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, hash_password("pass123"), role),
        )
        connection.commit()


def _login(client: TestClient, username: str) -> None:
    response = client.post(
        "/api/auth/login", data={"username": username, "password": "pass123"}
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


def test_ws_configuration_requires_an_authenticated_session(client: TestClient) -> None:
    # Given: the WebSocket port is deployment metadata, not public bootstrap data.
    # When: an anonymous browser requests it.
    # Then: it cannot discover the authenticated gateway configuration.
    response = client.get("/api/ws-config")

    assert response.status_code == 401


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
    conversations = client.get("/api/v1/conversations")

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


def test_login_returns_only_an_allowed_post_login_page(client: TestClient) -> None:
    # Given: an Owner account and both local and hostile next values.
    _create_user(client, "owner", "owner")

    # When: the same credentials are submitted through each login target.
    chat_next = client.post(
        "/api/auth/login?next=/chat",
        data={"username": "owner", "password": "pass123"},
    )
    client.cookies.clear()
    manage_next = client.post(
        "/api/auth/login?next=/manage",
        data={"username": "owner", "password": "pass123"},
    )
    client.cookies.clear()
    hostile = client.post(
        "/api/auth/login?next=https://attacker.invalid",
        data={"username": "owner", "password": "pass123"},
    )

    # Then: generic chat redirects cannot steal the Owner's management default.
    assert chat_next.json()["landing_path"] == "/manage"
    assert manage_next.json()["landing_path"] == "/manage"
    assert hostile.json()["landing_path"] == "/manage"


def test_owner_and_user_receive_server_side_landing_routes(client: TestClient) -> None:
    # Given: one Owner and one ordinary user.
    _create_user(client, "owner", "owner")
    _create_user(client, "alice", "user")

    # When: each authenticated user opens the root and management page.
    _login(client, "owner")
    owner_root = client.get("/", follow_redirects=False)
    owner_manage = client.get("/manage", follow_redirects=False)
    client.post("/api/auth/logout", headers={"X-CSRF-Token": ""})
    client.cookies.clear()
    _login(client, "alice")
    user_root = client.get("/", follow_redirects=False)
    user_manage = client.get("/manage", follow_redirects=False)

    # Then: the Owner defaults to manage; a user cannot enter it.
    assert owner_root.headers["location"] == "/manage"
    assert owner_manage.status_code == 200
    assert user_root.headers["location"] == "/chat"
    assert user_manage.headers["location"] == "/chat"


def test_owner_manage_query_still_returns_the_react_shell(
    client: TestClient,
) -> None:
    _create_user(client, "owner", "owner")
    _login(client, "owner")

    response = client.get("/manage?mode=classic")

    assert response.status_code == 200
    assert response.text == "app"


def test_react_shell_pages_are_not_cached_by_the_browser(client: TestClient) -> None:
    _create_user(client, "owner", "owner")
    _login(client, "owner")

    response = client.get("/manage")

    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["pragma"] == "no-cache"


def test_lan_rejects_unrecognized_host_and_origin(tmp_path: Path) -> None:
    # Given: a LAN-facing application with one explicitly recognized address.
    db_path = str(tmp_path / "nest.db")
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        patch(
            "app.interfaces.api.service_access.private_ipv4_addresses",
            return_value=("192.168.1.8",),
        ),
    ):
        application = create_app(
            engine=None, db_path=db_path, ws_port=9876, service_mode="lan"
        )
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
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        patch(
            "app.interfaces.api.service_access.private_ipv4_addresses",
            return_value=("192.168.1.8",),
        ),
    ):
        application = create_app(
            engine=None, db_path=db_path, ws_port=9876, service_mode="lan"
        )
        with TestClient(application) as client:
            _create_user(client, "owner", "owner")
            headers = {"Host": "192.168.1.8:8000"}
            login = client.post(
                "/api/auth/login",
                data={"username": "owner", "password": "pass123"},
                headers=headers,
            )

            # When: the Owner asks the current Core for its mobile access URL.
            response = client.get("/api/owner/mobile-access", headers=headers)

    # Then: the response advertises the real LAN root, never a loopback URL.
    assert login.status_code == 200
    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "urls": ["http://192.168.1.8:8000/"],
    }


def test_core_reads_the_packaged_web_build_directory_from_its_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_dir = _web_build(tmp_path)
    monkeypatch.setenv("ELFIENEST_WEB_BUILD_DIR", str(build_dir))
    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(
            engine=None, db_path=str(tmp_path / "nest.db"), ws_port=9876
        )
        with TestClient(application) as test_client:
            response = test_client.get("/login")

    assert response.status_code == 200
    assert response.text == "app"
