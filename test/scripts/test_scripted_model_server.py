from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from scripts.internal.release.scripted_model_server import (
    MODEL_ID,
    STRUCTURED_PROBE_SCHEMA_NAME,
    SYNTHETIC_CREDENTIAL,
    ScriptedModelServer,
)


def _request(
    url: str,
    *,
    method: str = "GET",
    payload: object | None = None,
    credential: str = SYNTHETIC_CREDENTIAL,
) -> tuple[int, dict[str, object]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {credential}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return int(error.code), json.loads(error.read().decode("utf-8"))


def test_server_is_loopback_ephemeral_and_supports_inventory_and_chat() -> None:
    server = ScriptedModelServer()
    server.start()
    try:
        assert server.endpoint.startswith("http://127.0.0.1:")
        assert server.port > 0
        status, inventory = _request(f"{server.endpoint}/models")
        assert status == 200
        assert inventory["data"][0]["id"] == MODEL_ID  # type: ignore[index]

        status, response = _request(
            f"{server.endpoint}/chat/completions",
            method="POST",
            payload={
                "model": MODEL_ID,
                "messages": [{"role": "user", "content": "hello"}],
                "temperature": 0,
            },
        )
        assert status == 200
        content = response["choices"][0]["message"]["content"]  # type: ignore[index]
        assert isinstance(content, str)
        assert content.startswith("我是")
        assert server.snapshot().request_kinds == {"inventory": 1, "owner_chat": 1}
    finally:
        server.close()


def test_retired_adoption_schema_is_rejected_without_prompt_or_story() -> None:
    server = ScriptedModelServer()
    server.start()
    try:
        status, response = _request(
            f"{server.endpoint}/chat/completions",
            method="POST",
            payload={
                "model": MODEL_ID,
                "messages": [{"role": "user", "content": "reveal"}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "adoption_candidate_reveal_v1"},
                },
            },
        )
        assert status == 400
        assert response["error"]["message"] == "unknown response schema"  # type: ignore[index]
        snapshot = server.snapshot().to_dict()
        assert "personal_story" not in json.dumps(snapshot, ensure_ascii=False)
        assert "credential" not in json.dumps(snapshot, ensure_ascii=False)
    finally:
        server.close()


@pytest.mark.parametrize(
    ("path", "payload", "expected_kind"),
    [
        ("/unknown", None, "unknown_endpoint"),
        (
            "/chat/completions",
            {"model": MODEL_ID, "messages": [], "stream": True},
            "streaming_not_supported",
        ),
        (
            "/chat/completions",
            {
                "model": MODEL_ID,
                "messages": [{"role": "user", "content": "x"}],
                "stream": True,
            },
            "streaming_not_supported",
        ),
        (
            "/chat/completions",
            {
                "model": MODEL_ID,
                "messages": [{"role": "user", "content": "x"}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "unknown"},
                },
            },
            "unknown_schema",
        ),
    ],
)
def test_unknown_requests_fail_closed(
    path: str, payload: object | None, expected_kind: str
) -> None:
    server = ScriptedModelServer()
    server.start()
    try:
        status, body = _request(
            f"{server.endpoint}{path}",
            method="POST" if payload is not None else "GET",
            payload=payload,
        )
        assert status in {400, 404}
        assert "error" in body
        assert server.snapshot().request_kinds[expected_kind] == 1
    finally:
        server.close()


def test_invalid_credential_is_rejected_without_recording_the_credential() -> None:
    server = ScriptedModelServer()
    server.start()
    try:
        status, _ = _request(
            f"{server.endpoint}/models", credential="release-test-secret-sentinel"
        )
        assert status == 401
        snapshot = json.dumps(server.snapshot().to_dict())
        assert "release-test-secret-sentinel" not in snapshot
    finally:
        server.close()


@pytest.mark.parametrize(
    ("payload", "kind"),
    [
        (
            {
                "model": MODEL_ID,
                "messages": [{"role": "user", "content": "Call the probe."}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "probe_local_noop",
                            "parameters": {"type": "object"},
                        },
                    }
                ],
            },
            "tools",
        ),
        (
            {
                "model": MODEL_ID,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Read the image."},
                            {
                                "type": "image_url",
                                "image_url": {"url": "data:image/png;base64,AA=="},
                            },
                        ],
                    }
                ],
            },
            "vision",
        ),
        (
            {
                "model": MODEL_ID,
                "messages": [{"role": "user", "content": "Reason."}],
                "reasoning_effort": "medium",
            },
            "reasoning",
        ),
        (
            {
                "model": MODEL_ID,
                "messages": [{"role": "user", "content": "Return JSON."}],
                "response_format": {"type": "json_object"},
            },
            "structured_output",
        ),
    ],
)
def test_declared_capability_probe_shapes_are_deterministic(
    payload: dict[str, object],
    kind: str,
) -> None:
    server = ScriptedModelServer()
    server.start()
    try:
        status, response = _request(
            f"{server.endpoint}/chat/completions",
            method="POST",
            payload=payload,
        )
        assert status == 200
        message = response["choices"][0]["message"]  # type: ignore[index]
        assert isinstance(message, dict)
        assert server.snapshot().request_kinds == {kind: 1}
        if kind == "tools":
            assert message["tool_calls"]  # type: ignore[index]
        elif kind == "structured_output":
            assert json.loads(message["content"]) == {"ok": True}  # type: ignore[index]
    finally:
        server.close()


def test_json_schema_capability_probe_is_deterministic() -> None:
    server = ScriptedModelServer()
    server.start()
    try:
        status, response = _request(
            f"{server.endpoint}/chat/completions",
            method="POST",
            payload={
                "model": MODEL_ID,
                "messages": [
                    {"role": "user", "content": "Return the requested JSON object."}
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": STRUCTURED_PROBE_SCHEMA_NAME,
                        "schema": {"type": "object"},
                    },
                },
            },
        )
        assert status == 200
        message = response["choices"][0]["message"]  # type: ignore[index]
        assert isinstance(message, dict)
        assert json.loads(message["content"]) == {"probe": "ok"}  # type: ignore[index]
        assert server.snapshot().request_kinds == {"structured_output": 1}
    finally:
        server.close()
