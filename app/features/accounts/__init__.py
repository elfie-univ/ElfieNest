"""Stable public facade for Accounts."""

from .errors import AccountForbidden, AuthenticationFailed, LoginRateLimited
from .models import AccountPrincipal, AuthenticatedSession, LoginCommand, SecurityPolicy
from .password_policy import PasswordPolicyError, validate_password_strength
from .passwords import hash_password, verify_password
from .ports import AccountCredentials, AccountSessionPort, SecurityPolicyPort
from .roles import (
    MAX_ACCOUNTS,
    MAX_ADMINS,
    AccountRole,
    AccountRoleError,
    can_manage_role,
    is_manager,
    parse_account_role,
    role_rank,
)
from .service import AccountsService, RateLimiter

__all__ = (
    "AccountCredentials",
    "AccountForbidden",
    "AccountPrincipal",
    "AccountRole",
    "AccountRoleError",
    "AccountSessionPort",
    "AccountsService",
    "AuthenticatedSession",
    "AuthenticationFailed",
    "LoginCommand",
    "LoginRateLimited",
    "MAX_ACCOUNTS",
    "MAX_ADMINS",
    "PasswordPolicyError",
    "RateLimiter",
    "SecurityPolicy",
    "SecurityPolicyPort",
    "can_manage_role",
    "hash_password",
    "is_manager",
    "parse_account_role",
    "role_rank",
    "validate_password_strength",
    "verify_password",
)
