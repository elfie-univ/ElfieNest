"""Check host capabilities required by the repository-wide test gate."""

from __future__ import annotations

import argparse
import errno
import json
import socket
import sys
from dataclasses import dataclass
from typing import Callable, Dict, Literal, Optional, Protocol, Sequence, Tuple

LOOPBACK_BIND_ADDRESS: Tuple[str, int] = ("127.0.0.1", 0)
_PERMISSION_ERRNOS = frozenset({errno.EACCES, errno.EPERM})
_Status = Literal["allowed", "blocked", "error"]


class _SocketLike(Protocol):
    def bind(self, address: Tuple[str, int]) -> None: ...

    def close(self) -> None: ...


SocketFactory = Callable[..., _SocketLike]


@dataclass(frozen=True)
class QualityEnvironmentResult:
    """Outcome of the capability probe used before the full test gate."""

    status: _Status
    reason: str
    error_number: Optional[int] = None
    detail: str = ""

    @property
    def exit_code(self) -> int:
        """Return a stable shell code: 0 allowed, 2 blocked, 1 unexpected."""
        return {"allowed": 0, "blocked": 2, "error": 1}[self.status]

    def as_dict(self) -> Dict[str, object]:
        return {
            "capability": "localhost_bind",
            "status": self.status,
            "reason": self.reason,
            "errno": self.error_number,
            "detail": self.detail,
        }


def probe_loopback_bind(
    socket_factory: SocketFactory = socket.socket,
) -> QualityEnvironmentResult:
    """Probe the same loopback bind capability used by the gateway tests.

    A permission denial is an environment state, not a test result. It gets a
    distinct exit code so callers can request a host/elevated run before
    starting the expensive full suite. Other socket errors remain failures.
    """

    sock: Optional[_SocketLike] = None
    try:
        sock = socket_factory(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(LOOPBACK_BIND_ADDRESS)
    except OSError as error:
        error_number = getattr(error, "errno", None)
        if isinstance(error, PermissionError) or error_number in _PERMISSION_ERRNOS:
            return QualityEnvironmentResult(
                status="blocked",
                reason="permission_denied",
                error_number=error_number,
                detail=str(error),
            )
        return QualityEnvironmentResult(
            status="error",
            reason="socket_probe_failed",
            error_number=error_number,
            detail=str(error),
        )
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    return QualityEnvironmentResult(status="allowed", reason="ok")


def _format_result(result: QualityEnvironmentResult) -> str:
    if result.status == "allowed":
        return "quality environment: localhost_bind=allowed"
    if result.status == "blocked":
        return (
            "quality environment: localhost_bind=blocked "
            f"reason={result.reason} errno={result.error_number}\n"
            "Do not start the full pytest gate in this environment. "
            "Run the same full command once in a host/elevated environment "
            "that permits binding 127.0.0.1:0."
        )
    return (
        "quality environment: localhost_bind=error "
        f"reason={result.reason} errno={result.error_number} "
        f"detail={result.detail}"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Probe loopback binding before running the repository-wide pytest gate."
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable result instead of guidance text",
    )
    arguments = parser.parse_args(argv)
    result = probe_loopback_bind()
    if arguments.json:
        print(json.dumps(result.as_dict(), sort_keys=True))
    else:
        print(_format_result(result))
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
