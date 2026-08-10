"""Secret-safe normalization for Provider technology failures."""

from __future__ import annotations

import re
from collections.abc import Iterable

_URL_CREDENTIALS = re.compile(r"(https?://)[^/@\s]+@", re.IGNORECASE)


def sanitize_error(error: str | None, *, secrets: Iterable[str]) -> str | None:
    if not error:
        return None
    result = _URL_CREDENTIALS.sub(r"\1[redacted]@", str(error))
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[redacted]")
    return " ".join(result.split())[:240]
