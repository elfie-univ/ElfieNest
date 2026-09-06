from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

import pytest

from scripts.internal.release.installed_product_journey import (
    HttpResult,
    InstalledHttpSession,
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
        self,
        *,
        resumed: bool = False,
        existing_provider: bool = False,
        verification_status: str = "passed",
        species_ids: tuple[str, ...] = ("fox",),
    ) -> None:
        self.csrf_token = "csrf-test"
        self.resumed = resumed
        self.existing_provider = existing_provider
        self.verification_status = verification_status
        self.species_ids = species_ids
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
        if path == "/api/v1/me/adoption":
            return self._result(
                200, {"species": [{"species_id": item} for item in self.species_ids]}
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
        if path.endswith("/models/refresh"):
            return self._result(
                200,
                {
                    "status": "updated",
                    "checked_at": "2026-08-26T00:00:00Z",
                    "message": None,
                    "models": self._provider()["models"],
                },
            )
        if path.endswith("/verify?force_full=true"):
            return self._result(
                200,
                {
                    "connection_id": self._connection_id,
                    "verification": {"status": self.verification_status},
                },
            )
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
                            "species_id": "fox",
                            "life_stage": "young_adult",
                            "age_years": 4,
                            "gender": "female",
                            "full_body_image_url": "",
                            "headshot_image_url": "",
                            "appearance_tags": ["standard"],
                            "personality_tags": ["steady"],
                            "runtime_appearance": {},
                            "message": "我读完你的同行意向了，愿意继续认识你。",
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


def test_http_chat_skips_user_echo_before_elfie_reply() -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.events = iter(
                (
                    json.dumps({"event": "ready"}),
                    json.dumps(
                        {
                            "event": "message",
                            "message": {
                                "sender": "user",
                                "text": "你好",
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "event": "message",
                            "message": {
                                "sender": "elfie",
                                "text": "我在这里",
                            },
                        }
                    ),
                )
            )

        def __enter__(self) -> FakeSocket:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def send(self, payload: str) -> None:
            self.sent.append(payload)

        def recv(self, timeout: float | None = None) -> str:
            _ = timeout
            return next(self.events)

    socket = FakeSocket()
    session = InstalledHttpSession("http://127.0.0.1:43122")
    session._cookies["session_token"] = "test-session"
    with patch("websockets.sync.client.connect", return_value=socket):
        result = session.chat("elfie-1", "你好", timeout_seconds=1.0)

    assert result.payload["message"] == {"sender": "elfie", "text": "我在这里"}
    assert len(socket.sent) == 1


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
    assert any(
        method == "PUT"
        and path == "/api/v1/setup/draft/remote"
        and body == {"configured": False, "connection_id": None}
        for method, path, body in session.calls
    )
    create_call = next(
        body
        for method, path, body in session.calls
        if method == "POST" and path == "/api/v1/admin/model-providers/connections"
    )
    assert create_call is not None
    assert create_call["verify"] is False
    assert create_call["refresh_models"] is False
    assert any(
        method == "POST" and path.endswith("/models/refresh")
        for method, path, _ in session.calls
    )
    assert any(
        method == "POST" and path.endswith("/verify?force_full=true")
        for method, path, _ in session.calls
    )
    candidate_call = next(
        body
        for method, path, body in session.calls
        if method == "POST" and path == "/api/v1/me/adoption/candidate-sets"
    )
    assert candidate_call["species_id"] == "fox"
    assert "adoption_session_id" not in candidate_call


def test_initial_journey_uses_packaged_species_when_fox_is_unavailable(
    tmp_path: Path,
) -> None:
    session = FakeSession(species_ids=("dog",))
    InstalledProductJourney(
        _config(tmp_path),
        session_factory=lambda _base_url, _timeout: session,
        status_reader=lambda: {"state": "ready", "generation": 3, "components": []},
    ).run(mode="initial")

    candidate_call = next(
        body
        for method, path, body in session.calls
        if method == "POST" and path == "/api/v1/me/adoption/candidate-sets"
    )
    assert candidate_call["species_id"] == "dog"


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


def test_initial_journey_fails_closed_when_provider_verification_is_not_passed(
    tmp_path: Path,
) -> None:
    session = FakeSession(verification_status="failed")

    with pytest.raises(JourneyFailure, match="provider_verification_not_passed"):
        InstalledProductJourney(
            _config(tmp_path),
            session_factory=lambda _base_url, _timeout: session,
        ).run(mode="initial")


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
