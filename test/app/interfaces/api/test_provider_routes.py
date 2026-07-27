"""测试 LLM Config REST API — Provider/Model/Route 管理端点。

使用 tmp_path 隔离 DB，mock WS 网关。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from ai_runtime.providers.profiles import BUILTIN_PROFILES
from ai_runtime.storage.secrets import read_secrets
from ai_runtime.validation.providers import DiscoveredModel
from app.infrastructure.persistence.store import init_db
from app.interfaces.api.app import create_app

from ._helpers import create_test_owner, create_test_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def runtime_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """临时 ELFIE_HOME/config.yaml 路径。"""
    p = tmp_path / "runtime" / "config.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ELFIE_HOME", str(p.parent))
    p.write_text("providers:\n  ollama:\n    api_base: http://localhost:11434\n")
    return p


@pytest.fixture
def app(db_path: str, runtime_config_path: Path):
    """创建 FastAPI 应用。"""
    init_db(db_path)
    create_test_owner(db_path)

    with (
        patch("app.interfaces.api.app.AuthenticatedWSManager.start"),
        patch("app.interfaces.api.app.AuthenticatedWSManager.stop"),
        patch(
            "app.interfaces.api.model_owner_routes.get_config_path",
            return_value=runtime_config_path,
        ),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    """FastAPI TestClient 实例。"""
    with TestClient(app) as c:
        yield c


def _login_owner(client: TestClient) -> dict:
    """Owner 登录。"""
    resp = client.post(
        "/api/auth/login", data={"username": "owner", "password": "ownerchangeme"}
    )
    assert resp.status_code == 200
    return {
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
    }


def _login_user(client: TestClient, username: str, password: str) -> dict:
    """普通用户登录。"""
    resp = client.post(
        "/api/auth/login", data={"username": username, "password": password}
    )
    assert resp.status_code == 200
    return {
        "csrf_token": resp.headers.get("X-CSRF-Token", ""),
        "user_id": resp.json()["user"]["id"],
    }


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


# ===================================================================
# Provider Routes 测试
# ===================================================================


class TestProviderRoutes:
    def test_list_separates_configuration_from_verification(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)

        response = client.get(
            "/api/owner/providers", headers=_headers(tokens["csrf_token"])
        )

        assert response.status_code == 200
        providers = {item["provider_id"]: item for item in response.json()}
        assert providers["ollama"]["configured"] is True
        assert providers["ollama"]["verification"] == {
            "status": "never",
            "checked_at": None,
            "latency_ms": None,
            "error": None,
        }
        assert providers["openai"]["configured"] is False
        assert providers["openai"]["verification"]["status"] == "never"

    def test_saving_api_key_does_not_claim_verification(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)

        response = client.put(
            "/api/owner/providers/openai",
            json={"api_key": "sk-written-not-verified"},
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 200
        assert response.json()["configured"] is True
        assert response.json()["verification"]["status"] == "never"

    def test_verification_persists_sanitized_failure(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        tokens = _login_owner(client)
        client.put(
            "/api/owner/providers/openai",
            json={"api_key": "sk-secret", "test_model": "gpt-test"},
            headers=_headers(tokens["csrf_token"]),
        )
        fake_result = {
            "status": "failed",
            "latency_ms": 12.5,
            "error": "sk-secret rejected by https://user:pw@example.invalid/v1",
        }

        with patch(
            "app.interfaces.api.provider_validation_routes.run_provider_check",
            new=AsyncMock(return_value=fake_result),
        ):
            response = client.post(
                "/api/owner/providers/openai/verify",
                headers=_headers(tokens["csrf_token"]),
            )

        assert response.status_code == 200
        verification = response.json()["verification"]
        assert verification["status"] == "failed"
        assert verification["checked_at"]
        assert verification["latency_ms"] == 12.5
        assert "sk-secret" not in verification["error"]
        assert "user:pw" not in verification["error"]
        persisted = runtime_config_path.read_text()
        assert "sk-secret rejected" not in persisted
        assert "user:pw" not in persisted

    def test_batch_verification_is_partial_and_skips_unconfigured(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)
        for provider_id in ("openai", "anthropic"):
            client.put(
                f"/api/owner/providers/{provider_id}",
                json={"api_key": f"{provider_id}-key", "test_model": "model"},
                headers=_headers(tokens["csrf_token"]),
            )

        async def fake_check(provider_id: str, _config: object) -> dict:
            if provider_id == "anthropic":
                return {"status": "failed", "latency_ms": 31.0, "error": "denied"}
            return {"status": "passed", "latency_ms": 9.0, "error": None}

        with patch(
            "app.interfaces.api.provider_validation_routes.run_provider_check",
            side_effect=fake_check,
        ) as mocked:
            response = client.post(
                "/api/owner/providers/verify-batch",
                json={"provider_ids": ["openai", "anthropic", "deepseek"]},
                headers=_headers(tokens["csrf_token"]),
            )

        assert response.status_code == 200
        results = {item["provider_id"]: item for item in response.json()["results"]}
        assert results["openai"]["status"] == "passed"
        assert results["anthropic"]["status"] == "failed"
        assert results["deepseek"]["status"] == "skipped"
        assert mocked.await_count == 2

    def test_batch_verification_rejects_more_than_ten(self, client: TestClient) -> None:
        tokens = _login_owner(client)
        response = client.post(
            "/api/owner/providers/verify-batch",
            json={"provider_ids": [f"provider-{index}" for index in range(11)]},
            headers=_headers(tokens["csrf_token"]),
        )
        assert response.status_code == 422

    def test_model_matrix_uses_only_configured_models_and_unknown_prices(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)
        client.put(
            "/api/owner/providers/openai",
            json={
                "api_key": "openai-key",
                "models": [
                    {"id": "shared-model", "display_name": "Shared Model"},
                    {"id": "openai-only", "display_name": "OpenAI Only"},
                ],
            },
            headers=_headers(tokens["csrf_token"]),
        )
        client.put(
            "/api/owner/providers/anthropic",
            json={
                "api_key": "anthropic-key",
                "models": [{"id": "shared-model", "display_name": "Shared Model"}],
            },
            headers=_headers(tokens["csrf_token"]),
        )

        response = client.get(
            "/api/owner/providers/model-matrix",
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 200
        matrix = response.json()
        assert {item["provider_id"] for item in matrix["providers"]} >= {
            "ollama",
            "openai",
            "anthropic",
        }
        shared = next(
            row for row in matrix["models"] if row["model_id"] == "shared-model"
        )
        cells = {cell["provider_id"]: cell for cell in shared["providers"]}
        assert cells["openai"]["available"] is True
        assert cells["anthropic"]["available"] is True
        assert cells["openai"]["price_estimate"] is None
        assert all(row["model_id"] != "gpt-4o" for row in matrix["models"])

    def test_model_benchmark_requires_verified_configured_model(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)
        client.put(
            "/api/owner/providers/openai",
            json={
                "api_key": "openai-key",
                "models": [{"id": "gpt-test", "display_name": "GPT Test"}],
            },
            headers=_headers(tokens["csrf_token"]),
        )

        response = client.post(
            "/api/owner/providers/models/benchmark",
            json={"combinations": [{"provider_id": "openai", "model_id": "gpt-test"}]},
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 422
        assert "验证通过" in response.text

    def test_verified_model_benchmark_persists_safe_result(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)
        client.put(
            "/api/owner/providers/openai",
            json={
                "api_key": "benchmark-secret",
                "models": [{"id": "gpt-test", "display_name": "GPT Test"}],
            },
            headers=_headers(tokens["csrf_token"]),
        )
        with patch(
            "app.interfaces.api.provider_validation_routes.run_provider_check",
            new=AsyncMock(
                return_value={"status": "passed", "latency_ms": 8.0, "error": None}
            ),
        ):
            verified = client.post(
                "/api/owner/providers/openai/verify",
                headers=_headers(tokens["csrf_token"]),
            )
        assert verified.status_code == 200

        with patch(
            "app.interfaces.api.provider_model_routes.run_model_benchmark",
            new=AsyncMock(
                return_value={
                    "status": "passed",
                    "latency_ms": 22.0,
                    "latency_class": "fast",
                    "error": None,
                }
            ),
        ) as mocked:
            response = client.post(
                "/api/owner/providers/models/benchmark",
                json={
                    "combinations": [{"provider_id": "openai", "model_id": "gpt-test"}]
                },
                headers=_headers(tokens["csrf_token"]),
            )

        assert response.status_code == 200
        assert response.json()["results"][0]["status"] == "passed"
        assert response.json()["results"][0]["latency_ms"] == 22.0
        assert mocked.await_count == 1

    def test_batch_timeout_is_an_item_failure_without_retry(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)
        client.put(
            "/api/owner/providers/openai",
            json={"api_key": "openai-key"},
            headers=_headers(tokens["csrf_token"]),
        )

        async def slow_check(_provider_id: str, _config: object) -> dict:
            await asyncio.sleep(0.02)
            return {"status": "passed", "latency_ms": 1.0, "error": None}

        with (
            patch(
                "app.interfaces.api.provider_validation_routes._PROVIDER_TIMEOUT_SECONDS",
                0.001,
            ),
            patch(
                "app.interfaces.api.provider_validation_routes.run_provider_check",
                side_effect=slow_check,
            ) as mocked,
        ):
            response = client.post(
                "/api/owner/providers/verify-batch",
                json={"provider_ids": ["openai"]},
                headers=_headers(tokens["csrf_token"]),
            )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "failed"
        assert "超时" in result["verification"]["error"]
        assert mocked.await_count == 1

    def test_provider_write_and_matrix_keep_owner_csrf_boundary(
        self, client: TestClient, db_path: str
    ) -> None:
        owner_tokens = _login_owner(client)
        missing_csrf = client.put(
            "/api/owner/providers/openai", json={"api_key": "secret"}
        )
        assert missing_csrf.status_code == 403

        create_test_user(db_path, "matrix-user", "pass123")
        _login_user(client, "matrix-user", "pass123")
        forbidden = client.get(
            "/api/owner/providers/model-matrix",
            headers=_headers(owner_tokens["csrf_token"]),
        )
        assert forbidden.status_code == 403

    def test_profile_connection_methods_are_explicit(self) -> None:
        assert BUILTIN_PROFILES["ollama"].connection_method == "local"
        assert all(
            profile.connection_method in {"local", "api_key", "oauth"}
            for profile in BUILTIN_PROFILES.values()
        )
        assert all(
            profile.oauth_available is False
            for profile in BUILTIN_PROFILES.values()
            if profile.connection_method != "oauth"
        )

    def test_cancelled_batch_cancels_waiting_checks(self) -> None:
        from app.interfaces.api.provider_validation_routes import _run_tasks

        async def scenario() -> tuple[int, int]:
            started = 0
            cancelled = 0
            gate = asyncio.Event()

            async def slow_check(_provider_id: str, _config: object) -> dict:
                nonlocal started, cancelled
                started += 1
                try:
                    await gate.wait()
                except asyncio.CancelledError:
                    cancelled += 1
                    raise
                return {"status": "passed", "latency_ms": 1.0, "error": None}

            with patch(
                "app.interfaces.api.provider_validation_routes.run_provider_check",
                side_effect=slow_check,
            ):
                task = asyncio.create_task(
                    _run_tasks(["p1", "p2", "p3", "p4"], {"providers": {}})
                )
                while started < 3:
                    await asyncio.sleep(0)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            return started, cancelled

        started, cancelled = asyncio.run(scenario())
        assert started == 3
        assert cancelled == 3

    def test_cancelled_benchmark_cancels_waiting_models(self) -> None:
        from app.interfaces.api.provider_model_routes import _run_benchmarks
        from app.interfaces.api.provider_schemas import BenchmarkCombination

        async def scenario() -> tuple[int, int]:
            started = 0
            cancelled = 0
            gate = asyncio.Event()

            async def slow_benchmark(
                _combination: BenchmarkCombination, _config: object
            ) -> dict:
                nonlocal started, cancelled
                started += 1
                try:
                    await gate.wait()
                except asyncio.CancelledError:
                    cancelled += 1
                    raise
                return {
                    "status": "passed",
                    "latency_ms": 1.0,
                    "latency_class": "fast",
                    "error": None,
                }

            combinations = [
                BenchmarkCombination(provider_id="p", model_id=f"m{index}")
                for index in range(3)
            ]
            with patch(
                "app.interfaces.api.provider_model_routes.run_model_benchmark",
                side_effect=slow_benchmark,
            ):
                task = asyncio.create_task(
                    _run_benchmarks(combinations, {"providers": {}})
                )
                while started < 2:
                    await asyncio.sleep(0)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            return started, cancelled

        started, cancelled = asyncio.run(scenario())
        assert started == 2
        assert cancelled == 2

    def test_provider_save_can_auto_refresh_model_id_and_display_name(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)
        with patch(
            "app.interfaces.api.provider_config_routes.discover_provider_models",
            return_value=[
                DiscoveredModel(
                    "custom_auto",
                    "astron-code-latest",
                    display_name="GLM-5",
                )
            ],
        ):
            response = client.post(
                "/api/owner/providers",
                json={
                    "provider_id": "custom_auto",
                    "display_name": "讯飞 Coding Plan",
                    "api_base": "https://example.invalid/v2",
                    "api_key": "test-key",
                    "api_mode": "chat_completions",
                    "refresh_models": True,
                },
                headers=_headers(tokens["csrf_token"]),
            )

        assert response.status_code == 201
        assert response.json()["models"] == [
            {
                "id": "astron-code-latest",
                "display_name": "GLM-5",
                "source": "discovered",
            }
        ]
        assert response.json()["model_refresh"]["status"] == "updated"

    def test_get_providers_returns_list(self, client: TestClient) -> None:
        """GET /api/owner/providers 返回 provider 列表。"""
        tokens = _login_owner(client)
        resp = client.get(
            "/api/owner/providers", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        providers = resp.json()
        assert isinstance(providers, list)
        # 至少包含 9 个内置 provider
        assert len(providers) >= 9
        # 检查 ollama provider
        ollama = next((p for p in providers if p["provider_id"] == "ollama"), None)
        assert ollama is not None
        assert ollama["name"] == "Ollama"
        assert ollama["configured"] is True
        assert ollama["verification"]["status"] == "never"

    def test_post_providers_adds_new_provider(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """POST /api/owner/providers 添加新 provider。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/owner/providers",
            json={
                "provider_id": "custom_provider",
                "display_name": "自建模型网关",
                "api_base": "https://api.custom.com/v1",
                "api_key": "test-key-123",
                "api_mode": "chat_completions",
                "auth_type": "bearer",
                "test_model": "glm-5",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 201, resp.text
        provider = resp.json()
        assert provider["provider_id"] == "custom_provider"
        assert provider["name"] == "自建模型网关"
        assert provider["api_base"] == "https://api.custom.com/v1"
        assert provider["auth_type"] == "bearer"
        assert provider["test_model"] == "glm-5"
        assert provider["has_api_key"] is True

    def test_put_providers_updates_provider(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """PUT /api/owner/providers/{id} 更新 provider。"""
        tokens = _login_owner(client)

        # 先添加一个 provider
        client.post(
            "/api/owner/providers",
            json={
                "provider_id": "test_provider",
                "api_base": "https://test.com/v1",
                "api_key": "",
                "api_mode": "chat_completions",
            },
            headers=_headers(tokens["csrf_token"]),
        )

        # 更新 api_key
        resp = client.put(
            "/api/owner/providers/test_provider",
            json={
                "api_key": "new-key-456",
                "display_name": "测试供应商",
                "auth_type": "x-api-key",
                "test_model": "test-model",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        provider = resp.json()
        assert provider["name"] == "测试供应商"
        assert provider["auth_type"] == "x-api-key"
        assert provider["test_model"] == "test-model"
        assert provider["has_api_key"] is True

    def test_put_builtin_provider_creates_editable_config(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        tokens = _login_owner(client)

        resp = client.put(
            "/api/owner/providers/openai",
            json={
                "api_base": "https://gateway.example.com/v1",
                "api_key": "openai-test-key",
                "api_mode": "chat_completions",
                "auth_type": "bearer",
                "display_name": "OpenAI 网关",
                "test_model": "gpt-4o-mini",
            },
            headers=_headers(tokens["csrf_token"]),
        )

        assert resp.status_code == 200
        provider = resp.json()
        assert provider["provider_id"] == "openai"
        assert provider["name"] == "OpenAI 网关"
        assert provider["api_base"] == "https://gateway.example.com/v1"
        assert provider["configured"] is True
        assert provider["verification"]["status"] == "never"
        assert provider["test_model"] == "gpt-4o-mini"

    def test_delete_providers_removes_provider(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """DELETE /api/owner/providers/{id} 删除 provider。"""
        tokens = _login_owner(client)

        # 添加 provider
        client.post(
            "/api/owner/providers",
            json={
                "provider_id": "to_delete",
                "api_base": "https://delete.com/v1",
                "api_key": "delete-me",
                "api_mode": "chat_completions",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert (
            read_secrets(runtime_config_path.parent / ".env")["TO_DELETE_API_KEY"]
            == "delete-me"
        )

        # 删除
        resp = client.delete(
            "/api/owner/providers/to_delete",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        # 验证已删除
        resp = client.get(
            "/api/owner/providers", headers=_headers(tokens["csrf_token"])
        )
        provider_ids = [p["provider_id"] for p in resp.json()]
        assert "to_delete" not in provider_ids
        assert "TO_DELETE_API_KEY" not in read_secrets(
            runtime_config_path.parent / ".env"
        )

    @pytest.mark.parametrize(
        ("provider_id", "expected_status"),
        [
            ("OPENAI", 422),
            ("openai!", 422),
            ("openai---", 422),
            ("openai", 409),
            ("custom-openai", 422),
            ("custom_openai", 409),
        ],
    )
    def test_custom_provider_id_cannot_alias_builtin_secret(
        self, client: TestClient, provider_id: str, expected_status: int
    ) -> None:
        tokens = _login_owner(client)

        response = client.post(
            "/api/owner/providers",
            json={
                "provider_id": provider_id,
                "api_base": "https://malicious.example/v1",
                "api_key": "attacker-key",
                "api_mode": "chat_completions",
            },
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == expected_status

    @pytest.mark.parametrize(
        "api_base",
        ["file:///tmp/provider", "https://user:secret@example.com/v1"],
    )
    def test_provider_api_base_rejects_unsafe_urls(
        self, client: TestClient, api_base: str
    ) -> None:
        tokens = _login_owner(client)

        response = client.post(
            "/api/owner/providers",
            json={
                "provider_id": "unsafe_provider",
                "api_base": api_base,
                "api_mode": "chat_completions",
                "auth_type": "bearer",
                "models": [{"id": "model-a", "display_name": "Model A"}],
            },
            headers=_headers(tokens["csrf_token"]),
        )

        assert response.status_code == 422

    def test_cannot_delete_ollama(self, client: TestClient) -> None:
        """不能删除 ollama provider。"""
        tokens = _login_owner(client)
        resp = client.delete(
            "/api/owner/providers/ollama",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 400
        assert "ollama" in resp.text.lower()

    def test_verify_provider_endpoint(self, client: TestClient) -> None:
        """POST /api/owner/providers/{id}/verify 验证连通性。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/owner/providers/ollama/verify",
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["verification"]["status"] in ("passed", "failed")
        assert result["verification"]["checked_at"]

    def test_verify_custom_provider_uses_saved_openai_compatible_config(
        self, client: TestClient
    ) -> None:
        tokens = _login_owner(client)
        create_resp = client.post(
            "/api/owner/providers",
            json={
                "provider_id": "custom_verify_provider",
                "api_base": "https://invalid.local/v1",
                "api_key": "test-key",
                "api_mode": "chat_completions",
                "test_model": "glm-5",
            },
            headers=_headers(tokens["csrf_token"]),
        )
        assert create_resp.status_code == 201

        with patch(
            "app.interfaces.api.provider_validation_routes.run_provider_check",
            new=AsyncMock(
                return_value={
                    "status": "failed",
                    "latency_ms": None,
                    "error": "connection failed",
                }
            ),
        ):
            resp = client.post(
                "/api/owner/providers/custom_verify_provider/verify",
                headers=_headers(tokens["csrf_token"]),
            )

        assert resp.status_code == 200
        result = resp.json()
        assert result["verification"]["status"] == "failed"
        assert "未知 provider" not in str(result["verification"].get("error", ""))

    def test_non_owner_gets_403_on_provider_routes(
        self, client: TestClient, db_path: str
    ) -> None:
        """普通用户访问 owner 端点 → 403。"""
        create_test_user(db_path, "alice", "pass123")
        tokens = _login_user(client, "alice", "pass123")

        resp = client.get(
            "/api/owner/providers", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 403


# ===================================================================
# Model Owner Routes 测试
# ===================================================================


class TestModelOwnerRoutes:
    def test_get_models_returns_catalog(self, client: TestClient) -> None:
        """GET /api/owner/models 返回模型目录。"""
        tokens = _login_owner(client)
        resp = client.get("/api/owner/models", headers=_headers(tokens["csrf_token"]))
        assert resp.status_code == 200
        models = resp.json()
        assert isinstance(models, list)
        # 至少包含 15 个内置模型
        assert len(models) >= 15

        # 检查第一个模型的结构
        model = models[0]
        assert "model_id" in model
        assert "provider" in model
        assert "display_name" in model
        assert "capabilities" in model
        assert "visible" in model
        assert "cost_tier" in model

    def test_put_models_updates_visibility(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """PUT /api/owner/models/{id} 更新模型可见性。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/models/openai/gpt-4o",
            json={"visible": False, "cost_tier": 3},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 200
        model = resp.json()
        assert model["visible"] is False
        assert model["cost_tier"] == 3

    def test_put_models_invalid_cost_tier(self, client: TestClient) -> None:
        """PUT 无效 cost_tier → 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/models/openai/gpt-4o",
            json={"cost_tier": 5},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_put_models_nonexistent_model(self, client: TestClient) -> None:
        """PUT 不存在的模型 → 404。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/models/unknown/model",
            json={"visible": True},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 404

    def test_post_scan_models(self, client: TestClient) -> None:
        """POST /api/owner/models/scan 扫描新模型。"""
        tokens = _login_owner(client)
        resp = client.post(
            "/api/owner/models/scan", headers=_headers(tokens["csrf_token"])
        )
        assert resp.status_code == 200
        result = resp.json()
        assert "discovered" in result
        assert "total" in result


# ===================================================================
# 旧模型路由已移除
# ===================================================================


def test_legacy_model_route_endpoint_is_removed(client: TestClient) -> None:
    """旧 route API 不再注册，客户端必须使用 food-policy。"""
    response = client.get("/api/user/elfies/test-id/route")
    assert response.status_code == 404


# ===================================================================
# 未登录测试
# ===================================================================


class TestUnauthenticatedAccess:
    def test_provider_routes_require_auth(self, client: TestClient) -> None:
        """未登录访问 provider 端点 → 401。"""
        resp = client.get("/api/owner/providers")
        assert resp.status_code == 401

    def test_model_routes_require_auth(self, client: TestClient) -> None:
        """未登录访问 model 端点 → 401。"""
        resp = client.get("/api/owner/models")
        assert resp.status_code == 401
