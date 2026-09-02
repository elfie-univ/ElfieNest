#!/usr/bin/env python3
"""Drive the supported product journey through an installed ElfieNest API.

This harness deliberately talks to an already running installed Controller.  It
never starts ``scripts/serve.py`` and it never writes the data root directly:
Setup, Provider/Food, Adoption and Chat all cross the same HTTP/WebSocket
boundaries as a user session.  The native smoke runner owns install, start,
stop and restart; this module owns the product journey between those phases.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Protocol, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.internal.release.scripted_model_server import (
    MODEL_ID,
    SYNTHETIC_CREDENTIAL,
)

JOURNEY_SCHEMA_VERSION = 1
DEFAULT_OWNER_ACCOUNT = "release_owner"
DEFAULT_OWNER_DISPLAY_NAME = "Release Owner"
DEFAULT_OWNER_PASSWORD = "ElfieNest-Release-2026!"
DEFAULT_TIMEOUT_SECONDS = 30.0
_COOKIE_NAMES = ("session_token", "setup_token")


class JourneyFailure(RuntimeError):
    """A redacted, machine-classifiable product journey failure."""

    def __init__(self, code: str, *, phase: str, detail: str = "") -> None:
        safe_code = re.sub(r"[^a-z0-9_\-]", "_", code.lower()) or "journey_failed"
        safe_detail = re.sub(r"[\r\n]+", " ", detail).strip()
        super().__init__(
            f"release-journey-failed phase={phase} code={safe_code}"
            + (f" detail={safe_detail}" if safe_detail else "")
        )
        self.code = safe_code
        self.phase = phase
        self.detail = safe_detail


@dataclass(frozen=True)
class HttpResult:
    status: int
    payload: Mapping[str, Any]
    headers: Mapping[str, str]


class JourneySession(Protocol):
    """HTTP and WebSocket operations required by the Driver."""

    csrf_token: str

    def get(self, path: str) -> HttpResult: ...

    def post_json(self, path: str, body: Mapping[str, Any]) -> HttpResult: ...

    def put_json(self, path: str, body: Mapping[str, Any]) -> HttpResult: ...

    def login(self, account_id: str, password: str) -> HttpResult: ...

    def chat(
        self, elfie_id: str, text: str, *, timeout_seconds: float
    ) -> HttpResult: ...


class InstalledHttpSession:
    """Small cookie-preserving HTTP/WebSocket session for the installed API."""

    def __init__(
        self, base_url: str, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    ):
        normalized = base_url.rstrip("/")
        parsed = urllib.parse.urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError("installed journey base URL must be loopback HTTP(S)")
        self.base_url = normalized
        self.timeout_seconds = timeout_seconds
        self.csrf_token = ""
        self._cookies: MutableMapping[str, str] = {}

    def get(self, path: str) -> HttpResult:
        return self._request("GET", path)

    def post_json(self, path: str, body: Mapping[str, Any]) -> HttpResult:
        return self._request(
            "POST",
            path,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    def put_json(self, path: str, body: Mapping[str, Any]) -> HttpResult:
        return self._request(
            "PUT",
            path,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    def login(self, account_id: str, password: str) -> HttpResult:
        data = urllib.parse.urlencode(
            {"account_id": account_id, "password": password}
        ).encode("utf-8")
        return self._request(
            "POST",
            "/api/v1/auth/login",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def chat(self, elfie_id: str, text: str, *, timeout_seconds: float) -> HttpResult:
        try:
            from websockets.sync.client import connect
            from websockets.typing import Origin
        except ImportError as error:  # pragma: no cover - dependency is locked
            raise JourneyFailure(
                "websocket_client_missing", phase="chat", detail=type(error).__name__
            ) from error

        ws_url = self.base_url.replace("http://", "ws://", 1).replace(
            "https://", "wss://", 1
        )
        ws_url += "/api/v1/ws/chat"
        headers = {"Cookie": self._cookie_header()}
        try:
            with connect(
                ws_url,
                additional_headers=headers,
                origin=Origin(self.base_url),
                proxy=None,
                open_timeout=timeout_seconds,
                close_timeout=5.0,
                max_size=1024 * 1024,
            ) as socket:
                ready = _decode_ws_event(socket.recv(), phase="chat")
                if ready.get("event") != "ready":
                    raise JourneyFailure("chat_ready_missing", phase="chat")
                socket.send(
                    json.dumps(
                        {
                            "event": "user_message",
                            "elfie_id": elfie_id,
                            "text": text,
                        },
                        ensure_ascii=False,
                    )
                )
                deadline = time.monotonic() + timeout_seconds
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise JourneyFailure("chat_reply_timeout", phase="chat")
                    event = _decode_ws_event(
                        socket.recv(timeout=remaining),
                        phase="chat",
                    )
                    event_name = event.get("event")
                    if event_name == "error":
                        raise JourneyFailure(
                            "chat_error_event",
                            phase="chat",
                            detail="server_error_event",
                        )
                    if event_name == "message":
                        message = event.get("message")
                        if not isinstance(message, dict):
                            raise JourneyFailure("chat_message_invalid", phase="chat")
                        # The product WebSocket publishes the persisted user
                        # message before the asynchronous Elfie reply.  Consume
                        # that normal acknowledgement and wait for the reply
                        # event instead of returning the echo to the journey.
                        if message.get("sender") == "user":
                            continue
                        return HttpResult(200, {"message": message}, {})
        except JourneyFailure:
            raise
        except Exception as error:  # noqa: BLE001 - classify transport failures
            raise JourneyFailure(
                "chat_transport_failed", phase="chat", detail=type(error).__name__
            ) from error

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResult:
        if not path.startswith("/"):
            raise ValueError("journey path must start with '/'")
        request_headers = dict(headers or {})
        cookie = self._cookie_header()
        if cookie:
            request_headers["Cookie"] = cookie
        if self.csrf_token:
            request_headers.setdefault("X-CSRF-Token", self.csrf_token)
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                return self._result(response.status, response.headers, response.read())
        except urllib.error.HTTPError as error:
            return self._result(error.code, error.headers, error.read())
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise JourneyFailure(
                "http_transport_failed", phase="http", detail=type(error).__name__
            ) from error

    def _result(self, status: int, headers: Any, raw: bytes) -> HttpResult:
        self._capture_cookies(headers)
        response_headers = {
            str(key).lower(): str(value) for key, value in headers.items()
        }
        header_csrf = response_headers.get("x-csrf-token", "")
        payload: Mapping[str, Any]
        try:
            decoded = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded = {}
        payload = decoded if isinstance(decoded, dict) else {}
        body_csrf = payload.get("csrf_token")
        if isinstance(header_csrf, str) and header_csrf:
            self.csrf_token = header_csrf
        elif isinstance(body_csrf, str) and body_csrf:
            self.csrf_token = body_csrf
        return HttpResult(int(status), payload, response_headers)

    def _capture_cookies(self, headers: Any) -> None:
        values = headers.get_all("Set-Cookie") or []
        for raw in values:
            cookie = SimpleCookie()
            try:
                cookie.load(raw)
            except (TypeError, ValueError):
                continue
            for name in _COOKIE_NAMES:
                morsel = cookie.get(name)
                if morsel is not None:
                    self._cookies[name] = morsel.value

    def _cookie_header(self) -> str:
        return "; ".join(
            f"{name}={value}" for name, value in self._cookies.items() if value
        )


@dataclass(frozen=True)
class InstalledJourneyConfig:
    """Non-secret inputs for one disposable installed journey."""

    base_url: str
    data_home: Path
    model_endpoint: str
    model_credential: str = SYNTHETIC_CREDENTIAL
    model_id: str = MODEL_ID
    owner_account_id: str = DEFAULT_OWNER_ACCOUNT
    owner_display_name: str = DEFAULT_OWNER_DISPLAY_NAME
    owner_password: str = DEFAULT_OWNER_PASSWORD
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    expected_source_root: Path | None = None


@dataclass
class JourneyEvidence:
    """Small redacted evidence summary written by the Driver."""

    mode: str
    result: str = "failed"
    phases: list[dict[str, Any]] = field(default_factory=list)
    details: MutableMapping[str, Any] = field(default_factory=dict)
    failure: MutableMapping[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": JOURNEY_SCHEMA_VERSION,
            "mode": self.mode,
            "result": self.result,
            "phases": list(self.phases),
            "details": dict(self.details),
        }
        if self.failure is not None:
            payload["failure"] = dict(self.failure)
        return payload


class InstalledProductJourney:
    """Run one initial or resumed product journey against an installed app."""

    def __init__(
        self,
        config: InstalledJourneyConfig,
        *,
        session_factory: Callable[[str, float], JourneySession] | None = None,
        status_reader: Callable[[], Mapping[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self._session_factory = session_factory or (
            lambda base_url, timeout: InstalledHttpSession(
                base_url, timeout_seconds=timeout
            )
        )
        self._status_reader = status_reader

    def run(self, *, mode: str = "initial") -> dict[str, Any]:
        if mode not in {"initial", "resume"}:
            raise ValueError("journey mode must be initial or resume")
        evidence = JourneyEvidence(mode=mode)
        session = self._session_factory(
            self.config.base_url,
            self.config.timeout_seconds,
        )
        try:
            self._assert_context()
            self._setup(session, evidence, expect_setup=mode == "initial")
            self._login(session, evidence)
            provider = self._configure_provider(session, evidence, mode=mode)
            self._configure_food(session, evidence, provider)
            self._assert_model_projection(session, evidence)
            elfie_id = self._adopt_or_resume(session, evidence, mode=mode)
            self._chat_and_verify_history(session, evidence, elfie_id, mode=mode)
            self._record_runtime_status(evidence, "after_journey")
            evidence.result = "passed"
            return evidence.to_dict()
        except JourneyFailure as error:
            evidence.failure = {"phase": error.phase, "code": error.code}
            evidence.result = "failed"
            raise
        finally:
            _assert_evidence_redacted(evidence.to_dict(), self.config)

    def _assert_context(self) -> None:
        if not self.config.data_home.is_absolute():
            raise JourneyFailure("data_home_not_absolute", phase="context")
        if not self.config.data_home.exists():
            raise JourneyFailure("data_home_missing", phase="context")
        if self.config.expected_source_root is not None:
            try:
                self.config.data_home.resolve().relative_to(
                    self.config.expected_source_root.resolve()
                )
            except ValueError:
                pass
            else:
                raise JourneyFailure("data_home_inside_source", phase="context")

    def _setup(
        self,
        session: JourneySession,
        evidence: JourneyEvidence,
        *,
        expect_setup: bool,
    ) -> Mapping[str, Any]:
        result = session.get("/api/v1/setup/status")
        _expect(result, 200, phase="setup", code="setup_status_failed")
        needs_setup = result.payload.get("need_setup") is True
        _phase(evidence, "setup_status", needs_setup=needs_setup)
        if needs_setup != expect_setup:
            code = "setup_not_first_run" if expect_setup else "setup_regressed"
            raise JourneyFailure(code, phase="setup")
        if not needs_setup:
            if result.payload.get("complete") is not True:
                raise JourneyFailure("setup_incomplete", phase="setup")
            _phase(evidence, "setup", completed=True, resumed=True)
            return result.payload

        csrf = _csrf_from(result)
        if csrf:
            session.csrf_token = csrf
        owner_body = {
            "account_id": self.config.owner_account_id,
            "display_name": self.config.owner_display_name,
            "password": self.config.owner_password,
            "confirm_password": self.config.owner_password,
        }
        _expect(
            session.put_json("/api/v1/setup/draft/owner", owner_body),
            200,
            phase="setup",
            code="setup_owner_failed",
        )
        _expect(
            session.put_json(
                "/api/v1/setup/draft/offline",
                {"use_local_ollama": False, "model_id": None},
            ),
            200,
            phase="setup",
            code="setup_offline_failed",
        )
        _expect(
            session.put_json("/api/v1/setup/draft/nest", {"bed_count": 4}),
            200,
            phase="setup",
            code="setup_nest_failed",
        )
        installation = session.post_json(
            "/api/v1/setup/installation",
            {"confirmed": True},
        )
        _expect(
            installation,
            {200, 202},
            phase="setup",
            code="setup_installation_failed",
        )
        deadline = time.monotonic() + self.config.timeout_seconds
        latest = installation.payload
        while latest.get("complete") is not True:
            if time.monotonic() >= deadline:
                raise JourneyFailure("setup_installation_timeout", phase="setup")
            time.sleep(0.25)
            polled = session.get("/api/v1/setup/status")
            _expect(polled, 200, phase="setup", code="setup_poll_failed")
            latest = polled.payload
            if latest.get("last_error"):
                raise JourneyFailure("setup_installation_error", phase="setup")
        if latest.get("need_setup") is not False:
            raise JourneyFailure("setup_still_required", phase="setup")
        _phase(evidence, "setup", completed=True, resumed=False)
        return latest

    def _login(self, session: JourneySession, evidence: JourneyEvidence) -> None:
        result = session.login(
            self.config.owner_account_id,
            self.config.owner_password,
        )
        _expect(result, 200, phase="auth", code="owner_login_failed")
        csrf = _csrf_from(result)
        if csrf:
            session.csrf_token = csrf
        user = result.payload.get("user")
        if (
            not isinstance(user, dict)
            or user.get("account_id") != self.config.owner_account_id
        ):
            raise JourneyFailure("owner_identity_mismatch", phase="auth")
        _phase(evidence, "owner_login", role=str(user.get("role") or "unknown"))

    def _configure_provider(
        self,
        session: JourneySession,
        evidence: JourneyEvidence,
        *,
        mode: str,
    ) -> dict[str, Any]:
        listed = session.get("/api/v1/admin/model-providers/connections")
        _expect(listed, 200, phase="provider", code="provider_list_failed")
        items = listed.payload.get("items")
        if not isinstance(items, list):
            raise JourneyFailure("provider_inventory_invalid", phase="provider")
        provider: Mapping[str, Any] | None = next(
            (
                item
                for item in items
                if isinstance(item, dict)
                and item.get("catalog_id") == "custom_openai"
                and item.get("api_base") == self.config.model_endpoint
                and _contains_model(item, self.config.model_id)
            ),
            None,
        )
        created = provider is None
        if provider is None:
            response = session.post_json(
                "/api/v1/admin/model-providers/connections",
                {
                    "catalog_id": "custom_openai",
                    "alias": "ElfieNest release loopback",
                    "api_base": self.config.model_endpoint,
                    "api_key": self.config.model_credential,
                    "api_mode": "chat_completions",
                    "auth_type": "bearer",
                    "models": [
                        {
                            "id": self.config.model_id,
                            "display_name": "ElfieNest release model",
                            "context_window_tokens": 8192,
                            "max_output_tokens": 512,
                            "supports_tools": True,
                            "supports_vision": True,
                            "supports_reasoning": True,
                            "supports_structured_output": True,
                            "request_profile_id": "openai_chat_v1",
                            "request_profile_version": 1,
                        }
                    ],
                    # Match the real Owner UI: saving a custom connection is
                    # cheap, then initial model setup refreshes inventory and
                    # the Owner explicitly runs the cost-bearing validation.
                    "verify": False,
                    "refresh_models": False,
                },
            )
            _expect(response, 201, phase="provider", code="provider_create_failed")
            provider_payload = response.payload
            if not isinstance(provider_payload, dict):
                raise JourneyFailure("provider_response_invalid", phase="provider")
            provider = provider_payload
        connection_id = provider.get("connection_id")
        if not isinstance(connection_id, str) or not connection_id:
            raise JourneyFailure("provider_connection_id_missing", phase="provider")
        if provider.get("enabled") is not True or provider.get("archived") is True:
            raise JourneyFailure("provider_not_enabled", phase="provider")
        if (
            provider.get("has_credential") is not True
            and provider.get("has_api_key") is not True
        ):
            raise JourneyFailure("provider_credential_not_persisted", phase="provider")
        model = _model_from_connection(provider, self.config.model_id)
        if model is None:
            raise JourneyFailure("provider_model_missing", phase="provider")
        verification_payload: Mapping[str, Any] | None = None
        if mode == "initial":
            if created:
                refresh = session.post_json(
                    f"/api/v1/admin/model-providers/connections/"
                    f"{urllib.parse.quote(connection_id, safe='')}/models/refresh",
                    {},
                )
                _expect(
                    refresh,
                    200,
                    phase="provider",
                    code="provider_model_refresh_failed",
                )
            verification = session.post_json(
                f"/api/v1/admin/model-providers/connections/"
                f"{urllib.parse.quote(connection_id, safe='')}/verify?force_full=true",
                {},
            )
            _expect(
                verification,
                200,
                phase="provider",
                code="provider_verification_failed",
            )
            verification_payload = verification.payload.get("verification")
            if (
                not isinstance(verification_payload, dict)
                or verification_payload.get("status") != "passed"
            ):
                raise JourneyFailure(
                    "provider_verification_not_passed", phase="provider"
                )
            probe_path = (
                f"/api/v1/admin/model-providers/connections/"
                f"{urllib.parse.quote(connection_id, safe='')}/models/"
                f"{urllib.parse.quote(self.config.model_id, safe='')}/capability-probes"
            )
            probe = session.post_json(
                probe_path,
                {"capabilities": ["tools", "vision", "reasoning", "structured_output"]},
            )
            _expect(
                probe, 200, phase="provider", code="provider_capability_probe_failed"
            )
            results = probe.payload.get("results")
            if not isinstance(results, list) or not results:
                raise JourneyFailure(
                    "provider_capability_results_missing", phase="provider"
                )
            for item in results:
                if not isinstance(item, dict) or item.get("state") != "supported":
                    raise JourneyFailure(
                        "provider_capability_unsupported", phase="provider"
                    )
        evidence.details["provider"] = {
            "connection_id": connection_id,
            "catalog_id": provider.get("catalog_id"),
            "model_id": self.config.model_id,
            "enabled": provider.get("enabled") is True,
            "has_credential": provider.get("has_credential") is True
            or provider.get("has_api_key") is True,
            "verification_status": (
                verification_payload.get("status")
                if isinstance(verification_payload, dict)
                else _nested(provider, "verification", "status")
            ),
            "capability_states": _capability_states(model),
        }
        _phase(evidence, "provider", connection_id=connection_id)
        return {"connection_id": connection_id, "model": model}

    def _configure_food(
        self,
        session: JourneySession,
        evidence: JourneyEvidence,
        provider: Mapping[str, Any],
    ) -> None:
        listed = session.get("/api/v1/admin/food-packages")
        _expect(listed, 200, phase="food", code="food_list_failed")
        packages = listed.payload.get("packages")
        if not isinstance(packages, list):
            raise JourneyFailure("food_catalog_invalid", phase="food")
        connection_id = str(provider["connection_id"])
        reference = f"{connection_id}/{self.config.model_id}"
        configured: dict[str, Mapping[str, Any]] = {}
        for system_role, expected_key in (
            ("common", "food_common"),
            ("emergency", "food_emergency"),
        ):
            package = next(
                (
                    item
                    for item in packages
                    if isinstance(item, dict)
                    and item.get("key") == expected_key
                    and item.get("system_role") == system_role
                ),
                None,
            )
            if package is None:
                raise JourneyFailure("food_system_package_missing", phase="food")
            if not _food_usable(package, reference):
                preview = session.post_json(
                    f"/api/v1/admin/food-packages/{urllib.parse.quote(expected_key, safe='')}/generation-preview",
                    {
                        "connection_ids": [connection_id],
                        "local_first": False,
                        "allow_remote": True,
                        "visibility_mode": "global",
                        "visible_user_ids": [],
                    },
                )
                _expect(preview, 200, phase="food", code="food_preview_failed")
                candidate = preview.payload.get("candidate")
                roles = candidate.get("roles") if isinstance(candidate, dict) else None
                if not isinstance(roles, dict) or not _role_model(roles, "primary"):
                    raise JourneyFailure("food_preview_unconfigured", phase="food")
                update = session.put_json(
                    f"/api/v1/admin/food-packages/{urllib.parse.quote(expected_key, safe='')}",
                    {
                        "display_name": str(
                            package.get("display_name") or expected_key
                        ),
                        "enabled": True,
                        "roles": roles,
                        "visibility_mode": "global",
                        "visible_user_ids": [],
                        "required_roles": list(package.get("required_roles") or []),
                    },
                )
                _expect(update, 200, phase="food", code="food_update_failed")
                package = update.payload.get("food")
                if not isinstance(package, dict):
                    raise JourneyFailure("food_update_response_invalid", phase="food")
            if not _food_usable(package, reference):
                raise JourneyFailure("food_not_executable", phase="food")
            configured[system_role] = package
        evidence.details["food"] = {
            role: {
                "key": package.get("key"),
                "enabled": package.get("enabled") is True,
                "health": package.get("health"),
                "primary_model_configured": bool(
                    _role_model(package.get("roles"), "primary")
                ),
            }
            for role, package in configured.items()
        }
        _phase(
            evidence,
            "food",
            common_health=configured["common"].get("health"),
            emergency_health=configured["emergency"].get("health"),
        )

    def _assert_model_projection(
        self,
        session: JourneySession,
        evidence: JourneyEvidence,
    ) -> None:
        deadline = time.monotonic() + self.config.timeout_seconds
        latest: Mapping[str, Any] = {}
        while time.monotonic() < deadline:
            status = session.get("/api/v1/admin/runtime/status")
            if status.status == 200:
                lifecycle = status.payload.get("lifecycle")
                if isinstance(lifecycle, dict):
                    latest = lifecycle
                    if lifecycle.get("model_state") in {"ready", "degraded"}:
                        if lifecycle.get("model_common_state") in {
                            "ready",
                            "degraded",
                        } and lifecycle.get("model_emergency_state") in {
                            "ready",
                            "degraded",
                        }:
                            evidence.details["model_projection"] = {
                                "state": lifecycle.get("model_state"),
                                "common_state": lifecycle.get("model_common_state"),
                                "emergency_state": lifecycle.get(
                                    "model_emergency_state"
                                ),
                            }
                            _phase(
                                evidence,
                                "model_projection",
                                state=lifecycle.get("model_state"),
                            )
                            return
            time.sleep(0.25)
        raise JourneyFailure(
            "model_projection_not_ready",
            phase="model_projection",
            detail=str(latest.get("model_state") or "unknown"),
        )

    def _adopt_or_resume(
        self,
        session: JourneySession,
        evidence: JourneyEvidence,
        *,
        mode: str,
    ) -> str:
        if mode == "resume":
            elfie_id = self._owned_elfie_id(session)
            evidence.details["adoption"] = {"resumed": True, "elfie_id": elfie_id}
            _phase(evidence, "adoption", resumed=True, elfie_id=elfie_id)
            return elfie_id
        options = session.get("/api/v1/me/adoption")
        _expect(options, 200, phase="adoption", code="adoption_options_failed")
        species = options.payload.get("species")
        species_ids = [
            item.get("species_id")
            for item in (species if isinstance(species, list) else [])
            if isinstance(item, dict) and isinstance(item.get("species_id"), str)
        ]
        if not species_ids:
            raise JourneyFailure("adoption_species_missing", phase="adoption")
        species_id = next(
            (candidate for candidate in ("fox", "dog") if candidate in species_ids),
            species_ids[0],
        )
        candidate_set = session.post_json(
            "/api/v1/me/adoption/candidate-sets",
            {
                "species_id": species_id,
                "life_stage": "young_adult",
                "gender": "any",
                "appearance": {
                    "stature": "standard",
                    "build": "standard",
                    "face": "soft",
                    "signature": "warm",
                    "priority": "face",
                },
                "answers": ["quiet", "research", "plan", "discuss", "steady"],
            },
        )
        _expect(candidate_set, 200, phase="adoption", code="candidate_set_failed")
        candidate_set_id = candidate_set.payload.get("candidate_set_id")
        candidates = candidate_set.payload.get("candidates")
        if (
            not isinstance(candidate_set_id, str)
            or not isinstance(candidates, list)
            or not candidates
        ):
            raise JourneyFailure("candidate_set_invalid", phase="adoption")
        candidate_ids: list[str] = []
        for item in candidates[:2]:
            if not isinstance(item, dict):
                continue
            candidate_id = item.get("candidate_id")
            if isinstance(candidate_id, str):
                candidate_ids.append(candidate_id)
        if not candidate_ids:
            raise JourneyFailure("candidate_ids_missing", phase="adoption")
        replies = session.post_json(
            f"/api/v1/me/adoption/candidate-sets/{urllib.parse.quote(candidate_set_id, safe='')}/replies",
            {
                "candidate_ids": candidate_ids,
                "invitation_message": "我想和你慢慢认识。",
            },
        )
        _expect(replies, 200, phase="adoption", code="candidate_reply_failed")
        reply_items = replies.payload.get("replies")
        accepted = next(
            (
                item
                for item in (reply_items if isinstance(reply_items, list) else [])
                if isinstance(item, dict)
                and item.get("status") == "accepted"
                and _valid_candidate_reply(item, expected_candidate_ids=candidate_ids)
            ),
            None,
        )
        if accepted is None:
            raise JourneyFailure("candidate_not_accepted", phase="adoption")
        candidate_id = accepted.get("candidate_id")
        if not isinstance(candidate_id, str):
            raise JourneyFailure("accepted_candidate_id_missing", phase="adoption")
        adopted = session.post_json(
            "/api/v1/me/adoption",
            {
                "candidate_set_id": candidate_set_id,
                "candidate_id": candidate_id,
                "name": "露米",
                "full_body_image_url": "",
                "headshot_image_url": "",
            },
        )
        _expect(adopted, 201, phase="adoption", code="adoption_commit_failed")
        adopted_elfie_id = adopted.payload.get("elfie_id")
        if not isinstance(adopted_elfie_id, str) or not adopted_elfie_id:
            raise JourneyFailure("adopted_elfie_id_missing", phase="adoption")
        elfie_id = adopted_elfie_id
        if self._owned_elfie_id(session, expected=elfie_id) != elfie_id:
            raise JourneyFailure("adopted_elfie_not_visible", phase="adoption")
        evidence.details["adoption"] = {
            "resumed": False,
            "elfie_id": elfie_id,
            "candidate_reply_valid": True,
        }
        _phase(
            evidence,
            "adoption",
            resumed=False,
            elfie_id=elfie_id,
            candidate_reply_valid=True,
        )
        return elfie_id

    def _owned_elfie_id(
        self, session: JourneySession, *, expected: str | None = None
    ) -> str:
        listed = session.get("/api/v1/elfies?relationship=owned")
        _expect(listed, 200, phase="adoption", code="elfie_list_failed")
        items = listed.payload.get("items")
        if not isinstance(items, list):
            raise JourneyFailure("elfie_list_invalid", phase="adoption")
        for item in items:
            profile = item.get("profile") if isinstance(item, dict) else None
            elfie_id = profile.get("elfie_id") if isinstance(profile, dict) else None
            if isinstance(elfie_id, str) and (expected is None or elfie_id == expected):
                return elfie_id
        raise JourneyFailure("owned_elfie_missing", phase="adoption")

    def _chat_and_verify_history(
        self,
        session: JourneySession,
        evidence: JourneyEvidence,
        elfie_id: str,
        *,
        mode: str,
    ) -> None:
        reply = session.chat(
            elfie_id,
            "你好，这是安装版发布验收中的一次确定性消息。",
            timeout_seconds=self.config.timeout_seconds,
        )
        message = reply.payload.get("message")
        if (
            not isinstance(message, dict)
            or message.get("sender") != "elfie"
            or not str(message.get("text") or "").strip()
        ):
            raise JourneyFailure("chat_reply_invalid", phase="chat")
        history = session.get(
            f"/api/v1/me/conversations/{urllib.parse.quote(elfie_id, safe='')}/messages"
        )
        _expect(history, 200, phase="chat", code="chat_history_failed")
        items = history.payload.get("items")
        if not isinstance(items, list):
            raise JourneyFailure("chat_history_invalid", phase="chat")
        senders = {item.get("sender") for item in items if isinstance(item, dict)}
        if not {"user", "elfie"}.issubset(senders):
            raise JourneyFailure("chat_history_not_persisted", phase="chat")
        evidence.details["chat"] = {
            "elfie_id": elfie_id,
            "reply_non_empty": True,
            "history_message_count": len(items),
            "resumed": mode == "resume",
        }
        _phase(
            evidence,
            "chat",
            reply_non_empty=True,
            history_persisted=True,
            resumed=mode == "resume",
        )

    def _record_runtime_status(self, evidence: JourneyEvidence, label: str) -> None:
        if self._status_reader is None:
            return
        try:
            payload = self._status_reader()
        except Exception as error:  # noqa: BLE001 - evidence should not hide failure
            raise JourneyFailure(
                "runtime_status_read_failed",
                phase="runtime",
                detail=type(error).__name__,
            ) from error
        evidence.details.setdefault("runtime", {})[label] = _lifecycle_summary(payload)


def run_installed_product_journey(
    config: InstalledJourneyConfig,
    *,
    mode: str = "initial",
    evidence_output: Path | None = None,
    status_reader: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run a journey and optionally write its redacted evidence."""
    driver = InstalledProductJourney(config, status_reader=status_reader)
    try:
        evidence = driver.run(mode=mode)
    except JourneyFailure as error:
        evidence = {
            "schema_version": JOURNEY_SCHEMA_VERSION,
            "mode": mode,
            "result": "failed",
            "failure": {"phase": error.phase, "code": error.code},
        }
        if evidence_output is not None:
            evidence_output.parent.mkdir(parents=True, exist_ok=True)
            evidence_output.write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        raise
    if evidence_output is not None:
        evidence_output.parent.mkdir(parents=True, exist_ok=True)
        evidence_output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return evidence


def _expect(
    result: HttpResult,
    expected: int | set[int],
    *,
    phase: str,
    code: str,
) -> None:
    expected_values = {expected} if isinstance(expected, int) else expected
    if result.status not in expected_values:
        error = result.payload.get("error")
        error_code = error.get("code") if isinstance(error, dict) else None
        error_message = error.get("message") if isinstance(error, dict) else None
        if isinstance(error_message, str):
            error_message = " ".join(error_message.split())[:160]
        detail = f"status={result.status} api_code={error_code or 'unknown'}"
        if error_message:
            detail += f" api_message={error_message}"
        raise JourneyFailure(
            code,
            phase=phase,
            detail=detail,
        )


def _csrf_from(result: HttpResult) -> str:
    body = result.payload.get("csrf_token")
    return body if isinstance(body, str) else result.headers.get("x-csrf-token", "")


def _phase(evidence: JourneyEvidence, name: str, **details: Any) -> None:
    evidence.phases.append({"name": name, "result": "passed", **details})


def _contains_model(connection: Mapping[str, Any], model_id: str) -> bool:
    return _model_from_connection(connection, model_id) is not None


def _model_from_connection(
    connection: Mapping[str, Any],
    model_id: str,
) -> Mapping[str, Any] | None:
    models = connection.get("models")
    if not isinstance(models, list):
        return None
    return next(
        (
            item
            for item in models
            if isinstance(item, dict) and item.get("id") == model_id
        ),
        None,
    )


def _capability_states(model: Mapping[str, Any]) -> dict[str, Any]:
    raw = model.get("capability_evidence")
    return dict(raw) if isinstance(raw, dict) else {}


def _nested(payload: Mapping[str, Any], outer: str, inner: str) -> Any:
    value = payload.get(outer)
    return value.get(inner) if isinstance(value, dict) else None


def _role_model(roles: object, role: str) -> str | None:
    if not isinstance(roles, dict):
        return None
    assignment = roles.get(role)
    model = assignment.get("model") if isinstance(assignment, dict) else None
    return model if isinstance(model, str) and model else None


def _food_usable(package: Mapping[str, Any], reference: str) -> bool:
    roles = package.get("roles")
    return bool(
        package.get("enabled") is True
        and package.get("archived") is False
        and package.get("health") in {"healthy", "degraded"}
        and _role_model(roles, "primary") == reference
    )


def _valid_candidate_reply(
    reply: Mapping[str, Any], *, expected_candidate_ids: Sequence[str]
) -> bool:
    candidate_id = reply.get("candidate_id")
    species_id = reply.get("species_id")
    life_stage = reply.get("life_stage")
    age_years = reply.get("age_years")
    gender = reply.get("gender")
    full_body_url = reply.get("full_body_image_url")
    headshot_url = reply.get("headshot_image_url")
    appearance_tags = reply.get("appearance_tags")
    personality_tags = reply.get("personality_tags")
    runtime_appearance = reply.get("runtime_appearance")
    message = reply.get("message")
    return bool(
        isinstance(candidate_id, str)
        and candidate_id in expected_candidate_ids
        and isinstance(species_id, str)
        and bool(species_id.strip())
        and life_stage in {"youth", "young_adult", "mature", "elder"}
        and isinstance(age_years, int)
        and not isinstance(age_years, bool)
        and 1 <= age_years <= 20
        and gender in {"male", "female"}
        and isinstance(full_body_url, str)
        and isinstance(headshot_url, str)
        and isinstance(appearance_tags, (list, tuple))
        and isinstance(personality_tags, (list, tuple))
        and isinstance(runtime_appearance, dict)
        and isinstance(message, str)
        and bool(message.strip())
    )


def _decode_ws_event(raw: object, *, phase: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise JourneyFailure("chat_event_not_text", phase=phase)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise JourneyFailure("chat_event_invalid_json", phase=phase) from error
    if not isinstance(payload, dict):
        raise JourneyFailure("chat_event_invalid", phase=phase)
    return payload


def _lifecycle_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only non-sensitive state/generation/component evidence."""
    components = payload.get("components")
    component_summary = []
    if isinstance(components, list):
        for item in components:
            if not isinstance(item, dict):
                continue
            component_summary.append(
                {
                    "name": item.get("name") or item.get("component"),
                    "state": item.get("state"),
                    "pid": item.get("pid"),
                }
            )
    return {
        "state": payload.get("state") or payload.get("tier"),
        "generation": payload.get("generation"),
        "model_state": payload.get("model_state"),
        "model_common_state": payload.get("model_common_state"),
        "model_emergency_state": payload.get("model_emergency_state"),
        "components": component_summary,
    }


def _assert_evidence_redacted(
    payload: Mapping[str, Any], config: InstalledJourneyConfig
) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    forbidden = (
        config.model_credential,
        config.owner_password,
        "Authorization",
        "session_token",
        "setup_token",
    )
    if any(value and value in serialized for value in forbidden):
        raise AssertionError("installed journey evidence contains a sensitive sentinel")


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--data-home", type=Path, required=True)
    parser.add_argument("--model-endpoint", required=True)
    parser.add_argument("--model-credential", default=SYNTHETIC_CREDENTIAL)
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--mode", choices=("initial", "resume"), default="initial")
    parser.add_argument("--evidence-output", type=Path, required=True)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    config = InstalledJourneyConfig(
        base_url=args.base_url,
        data_home=args.data_home,
        model_endpoint=args.model_endpoint,
        model_credential=args.model_credential,
        model_id=args.model_id,
    )
    try:
        run_installed_product_journey(
            config,
            mode=args.mode,
            evidence_output=args.evidence_output,
        )
    except JourneyFailure as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"release-journey-passed mode={args.mode} evidence={args.evidence_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "DEFAULT_OWNER_PASSWORD",
    "InstalledHttpSession",
    "InstalledJourneyConfig",
    "InstalledProductJourney",
    "JourneyEvidence",
    "JourneyFailure",
    "JOURNEY_SCHEMA_VERSION",
    "run_installed_product_journey",
)
