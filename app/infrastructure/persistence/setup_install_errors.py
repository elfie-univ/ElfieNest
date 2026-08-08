"""Sanitize errors before they are persisted in Setup installation state."""

_SENSITIVE_MARKERS = (
    "password",
    "token",
    "secret",
    "api key",
    "api_key",
    "api-key",
    "authorization",
    "bearer",
)


def sanitize_setup_error(error: str, fallback: str) -> str:
    normalized_error = error.strip()
    lowered = normalized_error.lower()
    if any(marker in lowered for marker in _SENSITIVE_MARKERS):
        return "Setup 安装失败；敏感错误详情已隐藏。"
    return normalized_error[:512] or fallback
