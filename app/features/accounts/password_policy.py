"""Shared password-strength boundary for account entry points."""

from __future__ import annotations

MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128


class PasswordPolicyError(ValueError):
    """A password is outside the effective trimmed-length policy."""

    def __init__(self, length: int) -> None:
        self.length = length
        super().__init__(
            f"密码去除首尾空格后必须为 {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} 个字符"
        )


def validate_password_strength(password: str) -> str:
    """Validate effective password length while preserving the entered secret."""
    effective_length = len(password.strip())
    if not MIN_PASSWORD_LENGTH <= effective_length <= MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(effective_length)
    return password
