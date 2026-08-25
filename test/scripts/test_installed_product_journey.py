from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from scripts.internal.release.installed_product_journey import (
    HttpResult,
    InstalledJourneyConfig,
    InstalledProductJourney,
    JourneyFailure,
)
from scripts.internal.release.scripted_model_server import (
    MODEL_ID,
    SYNTHETIC_CREDENTIAL,
)


class FakeSession:
    """Deterministic API boundary; no source server or data store is used."""

    def __init__(
        self, *, resumed: bool = False, existing_provider: bool = False
    ) -> None:
        self.csrf_token = "csrf-test"
        self.resumed = resumed
        self.existing_provider = existing_provider
        self.setup_installed = resumed
        self.calls: list[tuple[str, str, Mapping[str, Any] | None]] = []
        self._elfie_id = "elfie-release-1"
        self._connection_id = "connection-release-1"

    def get(self, path: str) -> HttpResult:
        self.calls.append(("GET", path, None))
        if path == "/api/v1/setup/status":
            if self.setup_installed:
                return self._result(200, {"need_setup": False, "complete": True})
            return self._result(
                200, {"need_setup": True, "complete": False, "csrf_token": "csrf-test"}
            )
        if path == "/api/v1/admin/model-providers/connections":
            return self._result(
                200, {"items": [self._provider()] if self.existing_provider else []}
            )
        if path == "/api/v1/admin/food-packages":
            return self._result(
                200, {"packages": [self._food("common"), self._food("emergency")]}
            )
        if path == "/api/v1/admin/runtime/status":
            return self._result(
                200,
                {
                    "lifecycle": {
                        "model_state": "ready",
                        "model_common_state": "ready",
                        "model_emergency_state": "ready",
                        "generation": 3,
                        "components": [],
                    }
                },
            )
        if path == "/api/v1/elfies?relationship=owned":
            return self._result(
                200, {"items": [{"profile": {"elfie_id": self._elfie_id}}]}
            )
        if path.startswith("/api/v1/me/conversations/") and path.endswith("/messages"):
            return self._result(
                200,
                {"items": [{"sender": "user"}, {"sender": "elfie"}]},
            )
        raise AssertionError(f"unexpected GET {path}")

    def post_json(self, path: str, body: Mapping[str, Any]) -> HttpResult:
        self.calls.append(("POST", path, body))
        if path == "/api/v1/setup/installation":
            self.setup_installed = True
            return self._result(202, {"complete": False})
        if path == "/api/v1/auth/login":
            raise AssertionError("login must use login(), not post_json()")
        if path == "/api/v1/admin/model-providers/connections":
            return self._result(201, self._provider())
        if path.endswith("/capability-probes"):
            return self._result(
                200,
                {
                    "results": [
                        {"capability": name, "state": "supported"}
                        for name in body["capabilities"]
                    ]
                },
            )
        if path.endswith("/generation-preview"):
            return self._result(200, {"candidate": {"roles": self._roles()}})
        if path == "/api/v1/me/adoption/candidate-sets":
            return self._result(
                200,
                {
                    "candidate_set_id": "candidate-set-1",
                    "candidates": [{"candidate_id": "candidate-1"}],
                },
            )
        if path.endswith("/replies"):
            return self._result(
                200,
                {
                    "replies": [
                        {
                            "candidate_id": "candidate-1",
                            "status": "accepted",
                            "reveal": {
                                "original_name": "Lumi",
                                "suggested_name": "露米",
                                "personal_story": "我是露米，喜欢慢慢听你说话，也愿意陪你一起把每个小问题想清楚。",
                            },
                        }
                    ]
                },
            )
        if path == "/api/v1/me/adoption":
            return self._result(201, {"elfie_id": self._elfie_id})
        raise AssertionError(f"unexpected POST {path}")

    def put_json(self, path: str, body: Mapping[str, Any]) -> HttpResult:
        self.calls.append(("PUT", path, body))
        if path.startswith("/api/v1/setup/draft/"):
            return self._result(200, {})
        if path.startswith("/api/v1/admin/food-packages/"):
            key = "food_common" if path.endswith("food_common") else "food_emergency"
            role = "common" if key == "food_common" else "emergency"
            return self._result(200, {"food": self._food(role, enabled=True)})
        raise AssertionError(f"unexpected PUT {path}")

    def login(self, account_id: str, password: str) -> HttpResult:
        self.calls.append(
            (
                "LOGIN",
                "/api/v1/auth/login",
                {"account_id": account_id, "password": password},
            )
        )
        return self._result(200, {"user": {"account_id": account_id, "role": "owner"}})

    def chat(self, elfie_id: str, text: str, *, timeout_seconds: float) -> HttpResult:
        _ = timeout_seconds
        self.calls.append(("CHAT", elfie_id, {"text": text}))
        return self._result(
            200, {"message": {"sender": "elfie", "text": "我在这里，收到你的消息了。"}}
        )

    def _result(self, status: int, payload: Mapping[str, Any]) -> HttpResult:
        return HttpResult(status, payload, {})

    def _provider(self) -> dict[str, Any]:
        return {
            "connection_id": self._connection_id,
            "catalog_id": "custom_openai",
            "api_base": "http://127.0.0.1:43123/v1",
            "enabled": True,
            "archived": False,
            "has_credential": True,
            "has_api_key": True,
            "verification": {"status": "passed"},
            "models": [
                {
                    "id": MODEL_ID,
                    "capability_evidence": {
                        "tools": "verified",
                        "vision": "verified",
                        "reasoning": "verified",
                        "structured_output": "verified",
                    },
                }
            ],
        }

    def _roles(self) -> dict[str, Any]:
        return {"primary": {"model": f"{self._connection_id}/{MODEL_ID}"}}

    def _food(self, role: str, *, enabled: bool = False) -> dict[str, Any]:
        key = "food_common" if role == "common" else "food_emergency"
        return {
            "key": key,
            "system_role": role,
            "display_name": key,
            "enabled": enabled,
            "archived": False,
            "health": "healthy" if enabled else "unconfigured",
            "roles": self._roles() if enabled else {},
            "required_roles": [],
        }


def _config(tmp_path: Path, *, mode: str = "initial") -> InstalledJourneyConfig:
    _ = mode
    data_home = tmp_path / "elfie-home"
    data_home.mkdir()
    return InstalledJourneyConfig(
        base_url="http://127.0.0.1:43122",
        data_home=data_home,
        model_endpoint="http://127.0.0.1:43123/v1",
        expected_source_root=tmp_path / "source",
        timeout_seconds=0.5,
    )


def test_initial_journey_runs_setup_provider_adoption_chat_and_redacts_evidence(
    tmp_path: Path,
) -> None:
    session = FakeSession()
    evidence = InstalledProductJourney(
        _config(tmp_path),
        session_factory=lambda _base_url, _timeout: session,
        status_reader=lambda: {"state": "ready", "generation": 3, "components": []},
    ).run(mode="initial")

    assert evidence["result"] == "passed"
    assert [phase["name"] for phase in evidence["phases"]] == [
        "setup_status",
        "setup",
        "owner_login",
        "provider",
        "food",
        "model_projection",
        "adoption",
        "chat",
    ]
    serialized = json.dumps(evidence, ensure_ascii=False)
    assert SYNTHETIC_CREDENTIAL not in serialized
    assert "ElfieNest-Release-2026!" not in serialized
    assert "安装版发布验收中的一次确定性消息" not in serialized
    assert any(
        method == "POST" and path.endswith("/capability-probes")
        for method, path, _ in session.calls
    )


def test_resume_journey_skips_first_run_setup_and_repeats_chat(tmp_path: Path) -> None:
    session = FakeSession(resumed=True, existing_provider=True)
    evidence = InstalledProductJourney(
        _config(tmp_path),
        session_factory=lambda _base_url, _timeout: session,
    ).run(mode="resume")

    assert evidence["result"] == "passed"
    assert evidence["details"]["adoption"]["resumed"] is True
    assert not any(
        path.startswith("/api/v1/setup/draft/") for _, path, _ in session.calls
    )
    assert not any(path.endswith("/capability-probes") for _, path, _ in session.calls)
    assert any(method == "CHAT" for method, _, _ in session.calls)


def test_journey_fails_closed_when_model_projection_never_becomes_ready(
    tmp_path: Path,
) -> None:
    session = FakeSession(resumed=True, existing_provider=True)

    original_get = session.get

    def not_ready(path: str) -> HttpResult:
        if path == "/api/v1/admin/runtime/status":
            return HttpResult(200, {"lifecycle": {"model_state": "offline"}}, {})
        return original_get(path)

    session.get = not_ready  # type: ignore[method-assign]
    with pytest.raises(JourneyFailure, match="model_projection_not_ready"):
        InstalledProductJourney(
            _config(tmp_path),
            session_factory=lambda _base_url, _timeout: session,
        ).run(mode="resume")
