from email.message import Message
from urllib.request import Request

import pytest

from infrastructure.models.providers.http import (
    RejectProviderRedirects,
    read_provider_response,
)


def test_provider_http_rejects_redirects_before_copying_credentials() -> None:
    handler = RejectProviderRedirects()
    request = Request(
        "https://provider.example/v1/models",
        headers={"Authorization": "Bearer local-secret"},
    )

    redirected = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        Message(),
        "https://attacker.example/collect",
    )

    assert redirected is None


class _OversizedResponse:
    def read1(self, amount: int = -1) -> bytes:
        _ = amount
        return b"oversized"


def test_provider_response_rejects_body_over_hard_limit() -> None:
    with pytest.raises(ValueError, match="安全上限"):
        read_provider_response(
            _OversizedResponse(),
            max_bytes=4,
            deadline_seconds=1,
        )
