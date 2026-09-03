"""Deterministic loopback model service for installed-release journeys.

The service intentionally speaks only the OpenAI-compatible subset used by the
production Provider adapter.  It is a test-owned remote boundary, not a model
implementation and never listens on a non-loopback address.
"""

from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping, MutableMapping, Sequence
from urllib.parse import urlsplit

MODEL_ID = "elfienest-release-model"
SYNTHETIC_CREDENTIAL = "elfienest-release-synthetic-credential"
STRUCTURED_PROBE_SCHEMA_NAME = "elfienest_probe"
_MAX_REQUEST_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ScriptedModelSnapshot:
    """Redacted request counters suitable for CI evidence."""

    endpoint: str
    port: int
    request_count: int
    failure_count: int
    request_kinds: Mapping[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "port": self.port,
            "request_count": self.request_count,
            "failure_count": self.failure_count,
            "request_kinds": dict(sorted(self.request_kinds.items())),
        }


class ScriptedModelServer:
    """Own one disposable loopback HTTP service for a release test job."""

    def __init__(self, *, credential: str = SYNTHETIC_CREDENTIAL) -> None:
        if not credential or any(char in credential for char in "\r\n"):
            raise ValueError("scripted model credential must be a non-empty safe token")
        self._credential = credential
        self._lock = threading.Lock()
        self._request_count = 0
        self._failure_count = 0
        self._request_kinds: MutableMapping[str, int] = {}
        handler = self._handler_type()
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._httpd.daemon_threads = True
        self._httpd.owner = self  # type: ignore[attr-defined]
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1])

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("scripted model server already started")
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="elfienest-scripted-model",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        thread = self._thread
        if thread is None:
            self._httpd.server_close()
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        thread.join(timeout=5.0)
        if thread.is_alive():
            raise RuntimeError("scripted model server did not stop")
        self._thread = None

    def snapshot(self) -> ScriptedModelSnapshot:
        with self._lock:
            return ScriptedModelSnapshot(
                endpoint=self.endpoint,
                port=self.port,
                request_count=self._request_count,
                failure_count=self._failure_count,
                request_kinds=dict(self._request_kinds),
            )

    def _record(self, kind: str, *, failure: bool = False) -> None:
        with self._lock:
            self._request_count += 1
            self._request_kinds[kind] = self._request_kinds.get(kind, 0) + 1
            if failure:
                self._failure_count += 1

    def _handler_type(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server: ThreadingHTTPServer

            def log_message(self, _format: str, *_args: object) -> None:
                # Prompts, credentials and model responses must never enter CI logs.
                return

            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                path = urlsplit(self.path).path
                if path == "/healthz":
                    self._send_json(200, {"status": "ok"})
                    return
                if path == "/v1/models":
                    if not self._authorized():
                        self._fail(401, "invalid_credential", "models")
                        return
                    owner._record("inventory")
                    self._send_json(200, _model_inventory())
                    return
                self._fail(404, "unknown_endpoint", "unknown_endpoint")

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
                path = urlsplit(self.path).path
                if path != "/v1/chat/completions":
                    self._fail(404, "unknown_endpoint", "unknown_endpoint")
                    return
                if not self._authorized():
                    self._fail(401, "invalid_credential", "chat")
                    return
                try:
                    payload = self._read_json()
                    kind, content, response_message = _completion_for(payload)
                except RequestRejected as error:
                    owner._record(error.kind, failure=True)
                    self._send_json(error.status, {"error": {"message": error.message}})
                    return
                owner._record(kind)
                self._send_json(
                    200,
                    _chat_completion(content, message=response_message),
                )

            def _authorized(self) -> bool:
                return (
                    self.headers.get("Authorization") == f"Bearer {owner._credential}"
                )

            def _read_json(self) -> Mapping[str, Any]:
                raw_length = self.headers.get("Content-Length", "")
                try:
                    length = int(raw_length)
                except ValueError as error:
                    raise RequestRejected(
                        400, "invalid_json", "invalid content length"
                    ) from error
                if length < 0 or length > _MAX_REQUEST_BYTES:
                    raise RequestRejected(413, "request_too_large", "request too large")
                raw = self.rfile.read(length)
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise RequestRejected(
                        400, "invalid_json", "request body is not JSON"
                    ) from error
                if not isinstance(payload, dict):
                    raise RequestRejected(
                        400, "invalid_json", "request body must be an object"
                    )
                return payload

            def _fail(self, status: int, message: str, kind: str) -> None:
                owner._record(kind, failure=True)
                self._send_json(status, {"error": {"message": message}})

            def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
                body = json.dumps(
                    payload, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


class RequestRejected(Exception):
    """A deliberately typed, fail-closed scripted request rejection."""

    def __init__(self, status: int, kind: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.kind = kind
        self.message = message


def _model_inventory() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "object": "model",
                "owned_by": "elfienest-release-test",
                "capabilities": {
                    "text": True,
                    "tools": True,
                    "structured_output": True,
                    "reasoning": True,
                    "vision": True,
                },
                "context_window": 8192,
                "max_output_tokens": 512,
            }
        ],
    }


def _completion_for(
    payload: Mapping[str, Any],
) -> tuple[str, str, Mapping[str, Any] | None]:
    if payload.get("model") != MODEL_ID:
        raise RequestRejected(
            400, "unknown_model", "model is not in the scripted inventory"
        )
    if payload.get("stream") is True:
        raise RequestRejected(
            400,
            "streaming_not_supported",
            "streaming is not part of this deterministic gate",
        )
    messages = payload.get("messages")
    if (
        not isinstance(messages, list)
        or not messages
        or not all(isinstance(item, dict) for item in messages)
    ):
        raise RequestRejected(
            400, "invalid_messages", "messages must be a non-empty object list"
        )
    response_format = payload.get("response_format")
    if response_format is not None and not isinstance(response_format, dict):
        raise RequestRejected(
            400, "unknown_schema", "response_format must be an object"
        )
    is_structured_probe = _is_structured_probe(response_format)
    is_tool_probe = _is_tool_probe(payload.get("tools"))
    is_vision_probe = _is_vision_probe(messages)
    is_reasoning_probe = _is_reasoning_probe(payload)
    if response_format is not None:
        if not is_structured_probe:
            raise RequestRejected(400, "unknown_schema", "unknown response schema")
    tools = payload.get("tools")
    if tools not in (None, [], ()) and not is_tool_probe:
        raise RequestRejected(
            400, "unknown_tool", "tool requests are not in this scripted scenario"
        )
    if is_tool_probe:
        return (
            "tools",
            "",
            {
                "tool_calls": [
                    {
                        "id": "call-elfienest-probe",
                        "type": "function",
                        "function": {"name": "probe_local_noop", "arguments": "{}"},
                    }
                ]
            },
        )
    if is_vision_probe:
        return "vision", "ELFIENEST_VISION_OK", None
    if is_reasoning_probe:
        return "reasoning", "OK", {"reasoning_content": "ELFIENEST_REASONING_TRACE"}
    if is_structured_probe:
        if _is_json_schema_probe(response_format):
            return "structured_output", json.dumps({"probe": "ok"}), None
        return "structured_output", json.dumps({"ok": True}), None
    return (
        "owner_chat",
        "我是测试中的 Elfie。我会认真听你说话，也会把这次对话记在自己的生活里。",
        None,
    )


def _is_structured_probe(response_format: object) -> bool:
    if not isinstance(response_format, Mapping):
        return False
    if response_format.get("type") == "json_object":
        return True
    return _is_json_schema_probe(response_format)


def _is_json_schema_probe(response_format: Mapping[str, Any] | object) -> bool:
    if not isinstance(response_format, Mapping):
        return False
    schema = response_format.get("json_schema")
    return (
        isinstance(schema, Mapping)
        and response_format.get("type") == "json_schema"
        and schema.get("name") == STRUCTURED_PROBE_SCHEMA_NAME
    )


def _is_tool_probe(tools: object) -> bool:
    if not isinstance(tools, list) or len(tools) != 1:
        return False
    tool = tools[0]
    if not isinstance(tool, Mapping) or tool.get("type") != "function":
        return False
    function = tool.get("function")
    return isinstance(function, Mapping) and function.get("name") == "probe_local_noop"


def _is_vision_probe(messages: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        isinstance(message.get("content"), list)
        and any(
            isinstance(part, Mapping) and part.get("type") == "image_url"
            for part in message["content"]
        )
        for message in messages
    )


def _is_reasoning_probe(payload: Mapping[str, Any]) -> bool:
    return payload.get("reasoning_effort") in {"low", "medium", "high"}


def _chat_completion(
    content: str,
    *,
    message: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    assistant_message: dict[str, Any] = {
        "role": "assistant",
        "content": content,
    }
    if message:
        assistant_message.update(message)
    return {
        "id": f"chatcmpl-elfienest-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [
            {
                "index": 0,
                "message": assistant_message,
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _serve_forever(
    port: int,
    ready_file: str | None,
    summary_file: str | None,
) -> int:
    server = ScriptedModelServer()
    if port:
        # The CLI is intentionally strict: callers may request the ephemeral
        # port (0) or a known disposable port, but never a public bind address.
        server.close()
        handler = server._handler_type()
        server._httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        server._httpd.daemon_threads = True
        server._httpd.owner = server  # type: ignore[attr-defined]
    server.start()
    payload = {"pid": __import__("os").getpid(), **server.snapshot().to_dict()}
    if ready_file:
        with open(ready_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.write("\n")
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        stopped.wait()
    finally:
        server.close()
        if summary_file:
            with open(summary_file, "w", encoding="utf-8") as handle:
                json.dump(server.snapshot().to_dict(), handle, ensure_ascii=False)
                handle.write("\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--ready-file")
    parser.add_argument("--summary-file")
    args = parser.parse_args(argv)
    if args.port < 0 or args.port > 65535:
        parser.error("--port must be between 0 and 65535")
    return _serve_forever(args.port, args.ready_file, args.summary_file)


__all__ = [
    "MODEL_ID",
    "SYNTHETIC_CREDENTIAL",
    "ScriptedModelServer",
    "ScriptedModelSnapshot",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
