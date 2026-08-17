"""Authentication, session and role use-cases for Accounts."""

from __future__ import annotations

import secrets
import string
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Final, Optional

from .errors import (
    AccountConflict,
    AccountForbidden,
    AccountNotFound,
    AccountsUnavailable,
    AccountValidationFailed,
    AuthenticationFailed,
    AvatarContentInvalid,
    AvatarMediaTypeUnsupported,
    AvatarNotFound,
    AvatarTooLarge,
    CurrentPasswordIncorrect,
    LoginRateLimited,
    ManagedAccountCapacityReached,
    ManagedAccountHasElfies,
    PasswordReuseRejected,
    RegistrationUnavailable,
)
from .models import (
    AccountHeartbeatResult,
    AccountPrincipal,
    AccountProfileResult,
    AuthenticatedSession,
    AvatarResult,
    ChangePasswordCommand,
    CreateFirstOwnerCommand,
    CreateManagedAccountCommand,
    DeleteManagedAccountCommand,
    GetAvatarQuery,
    GetCurrentAccountQuery,
    GetManagedAvatarQuery,
    GetOwnerAccountQuery,
    HasOwnerQuery,
    ListManagedAccountsQuery,
    LoginCommand,
    ManagedAccountResult,
    ManagedAccountsResult,
    OwnerAccountResult,
    RecordAccountHeartbeatCommand,
    RecoverOwnerAccountCommand,
    RegisterAccountCommand,
    ResetManagedAccountPasswordCommand,
    SecurityPolicy,
    SeedInitialOwnerCommand,
    SeedInitialOwnerResult,
    TemporaryPasswordResult,
    UpdateAccountProfileCommand,
    UpdateLandingPageCommand,
    UpdateManagedAccountQuotaCommand,
    UpdateThemeCommand,
    UploadAvatarCommand,
)
from .password_policy import PasswordPolicyError, validate_password_strength
from .passwords import hash_password, verify_password
from .port_models import (
    AccountProfileRecord,
    AccountProfileWrite,
    ManagedAccountRecord,
    OwnerAccountRecord,
)
from .ports import (
    AccountAvatarPort,
    AccountCredentials,
    AccountManagementPort,
    AccountPersistenceCapacityError,
    AccountPersistenceConflict,
    AccountPersistenceError,
    AccountPersistenceTargetError,
    AccountQuotaPolicyError,
    AccountQuotaPolicyPort,
    AccountSessionPort,
    InitialOwnerSeedPort,
    SecurityPolicyPort,
)
from .roles import can_manage_role, is_manager, parse_account_role

_MAX_AVATAR_BYTES: Final = 2 * 1024 * 1024
_AVATAR_EXTENSIONS: Final[dict[str, str]] = {
    "image/jpeg": "jpeg",
    "image/png": "png",
    "image/webp": "webp",
}
_TEMPORARY_PASSWORD_LENGTH: Final = 12
_TEMPORARY_PASSWORD_ALPHABET: Final = string.ascii_letters + string.digits
_MIN_ACCOUNT_ID_LENGTH: Final = 3
_MAX_ACCOUNT_ID_LENGTH: Final = 32
_MAX_DISPLAY_NAME_LENGTH: Final = 64
_MAX_ELFIE_QUOTA: Final = 32


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._records: dict[str, list[float]] = {}

    def _key(self, client_key: str, account_id: str) -> str:
        return f"{client_key}:{account_id}"

    def is_limited(self, client_key: str, account_id: str) -> bool:
        key = self._key(client_key, account_id)
        cutoff = time.time() - self._window_seconds
        timestamps = [value for value in self._records.get(key, []) if value > cutoff]
        self._records[key] = timestamps
        return len(timestamps) >= self._max_attempts

    def record_failure(self, client_key: str, account_id: str) -> None:
        self._records.setdefault(self._key(client_key, account_id), []).append(
            time.time()
        )

    def clear(self, client_key: str, account_id: str) -> None:
        self._records.pop(self._key(client_key, account_id), None)


class AccountsService:
    """Public facade for the existing authentication/session capability."""

    def __init__(
        self,
        sessions: Optional[AccountSessionPort] = None,
        security_policy: Optional[SecurityPolicyPort] = None,
        *,
        management: Optional[AccountManagementPort] = None,
        avatars: Optional[AccountAvatarPort] = None,
        quota_policy: Optional[AccountQuotaPolicyPort] = None,
        initial_owner_seed: Optional[InitialOwnerSeedPort] = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._sessions = sessions
        self._security_policy = security_policy
        self._management = management
        self._avatars = avatars
        self._quota_policy = quota_policy
        self._initial_owner_seed = initial_owner_seed
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._rate_limiters: dict[tuple[int, int], RateLimiter] = {}

    def login(self, command: LoginCommand) -> AuthenticatedSession:
        policy = self._require_security_policy().load()
        limiter = self._rate_limiter(
            policy.max_login_attempts, policy.login_window_seconds
        )
        if limiter.is_limited(command.client_key, command.account_id):
            raise LoginRateLimited

        sessions = self._require_sessions()
        credentials = sessions.find_credentials(command.account_id)
        if credentials is None or not verify_password(
            command.password, credentials.password_hash
        ):
            limiter.record_failure(command.client_key, command.account_id)
            raise AuthenticationFailed

        limiter.clear(command.client_key, command.account_id)
        return self._authenticated_session(credentials, policy)

    def register(self, command: RegisterAccountCommand) -> AuthenticatedSession:
        policy = self._require_security_policy().load()
        if not self.has_owner(HasOwnerQuery()):
            raise RegistrationUnavailable("系统尚未完成首启设置")

        account_id = command.account_id.strip()
        display_name = self._normalize_display_name(command.display_name)
        self._validate_identity(account_id, display_name)
        if display_name is None:
            raise AccountValidationFailed("显示名称不能为空")
        try:
            validate_password_strength(command.password)
        except PasswordPolicyError as error:
            raise AccountValidationFailed(str(error)) from error

        try:
            self._require_management().create_user_account(
                account_id=account_id,
                display_name=display_name,
                password_hash=hash_password(command.password),
            )
            credentials = self._require_sessions().find_credentials(account_id)
        except AccountPersistenceConflict as error:
            raise AccountConflict("登录账号已存在") from error
        except AccountPersistenceCapacityError as error:
            raise ManagedAccountCapacityReached("账号人数已满") from error
        except AccountPersistenceError as error:
            raise AccountsUnavailable("账户暂时无法创建") from error
        if credentials is None:
            raise AccountsUnavailable("注册账户暂时无法读取")
        return self._authenticated_session(credentials, policy)

    def find_principal(self, user_id: int) -> AccountPrincipal | None:
        """Resolve a current least-surprise principal for trusted App workflows."""
        try:
            record = self._require_management().find_profile(user_id)
        except AccountPersistenceError:
            return None
        if record is None:
            return None
        return AccountPrincipal(
            user_id=record.user_id,
            account_id=record.account_id,
            role=record.role,
            default_landing_page=record.default_landing_page,
        )

    def authenticate_session(self, token: str) -> AccountPrincipal | None:
        return self._require_sessions().find_session(token, self._now())

    def create_session(self, user_id: int) -> str:
        policy = self._require_security_policy().load()
        return self._require_sessions().issue_session(
            user_id, self._now() + timedelta(seconds=policy.session_ttl_seconds)
        )

    def logout(self, token: str) -> None:
        self._require_sessions().revoke_session(token, self._now())

    def session_ttl_seconds(self) -> int:
        return self._require_security_policy().load().session_ttl_seconds

    def require_owner(self, principal: AccountPrincipal) -> AccountPrincipal:
        if principal.role != "owner":
            raise AccountForbidden("需要 Owner 权限")
        return principal

    def require_manager(self, principal: AccountPrincipal) -> AccountPrincipal:
        if not is_manager(principal.role):
            raise AccountForbidden("需要 Owner 或 Admin 权限")
        return principal

    def invalidate_security_cache(self) -> None:
        self._rate_limiters.clear()

    def has_owner(self, query: HasOwnerQuery) -> bool:
        _ = query
        try:
            return self._require_management().find_owner_account() is not None
        except AccountPersistenceError as error:
            raise AccountsUnavailable("Owner 状态暂时不可用") from error

    def seed_initial_owner(
        self, command: SeedInitialOwnerCommand
    ) -> SeedInitialOwnerResult:
        _ = command
        if self._initial_owner_seed is None:
            raise AccountsUnavailable("Owner 初始化暂时不可用")
        try:
            return SeedInitialOwnerResult(
                created=self._initial_owner_seed.seed_initial_owner()
            )
        except AccountPersistenceError as error:
            raise AccountsUnavailable("Owner 初始化暂时不可用") from error

    def create_first_owner(
        self, command: CreateFirstOwnerCommand
    ) -> OwnerAccountResult:
        account_id = command.account_id.strip()
        self._validate_identity(account_id, command.display_name)
        if not command.password_hash:
            raise AccountValidationFailed("Owner 密码摘要不能为空")
        try:
            record = self._require_management().create_first_owner(
                account_id=account_id,
                display_name=self._normalize_display_name(command.display_name),
                password_hash=command.password_hash,
            )
        except AccountPersistenceConflict as error:
            raise AccountConflict("系统已有用户，无法执行首启设置") from error
        except AccountPersistenceError as error:
            raise AccountsUnavailable("Owner 账号暂时无法创建") from error
        return self._owner_result(record)

    def get_current_account(
        self,
        principal: AccountPrincipal,
        query: GetCurrentAccountQuery,
    ) -> AccountProfileResult:
        _ = query
        return self._profile_result(self._load_profile(principal.user_id))

    def record_heartbeat(
        self,
        principal: AccountPrincipal,
        command: RecordAccountHeartbeatCommand,
    ) -> AccountHeartbeatResult:
        _ = command
        last_seen_at = (
            self._now().astimezone(timezone.utc).isoformat(timespec="microseconds")
        )
        try:
            updated = self._require_management().record_heartbeat(
                principal.user_id, last_seen_at
            )
        except AccountPersistenceError as error:
            raise AccountsUnavailable("在线状态暂时无法更新") from error
        if not updated:
            raise AccountNotFound("账户不存在")
        return AccountHeartbeatResult(last_seen_at=last_seen_at)

    def update_profile(
        self,
        principal: AccountPrincipal,
        command: UpdateAccountProfileCommand,
    ) -> AccountProfileResult:
        if not command.fields:
            raise AccountValidationFailed("没有提供要更新的字段")
        current = self._load_profile(principal.user_id)
        if "account_id" in command.fields and command.account_id is None:
            raise AccountValidationFailed("登录账号不能为空")
        if "gender" in command.fields and command.gender is None:
            raise AccountValidationFailed("性别只能是男或女")
        if "avatar_color" in command.fields and command.avatar_color is None:
            raise AccountValidationFailed("头像颜色不能为空")
        if "avatar_kind" in command.fields and command.avatar_kind is None:
            raise AccountValidationFailed("头像类型不能为空")

        account_id = (
            command.account_id
            if "account_id" in command.fields and command.account_id is not None
            else current.account_id
        )
        display_name = (
            command.display_name
            if "display_name" in command.fields
            else current.display_name
        )
        gender = (
            command.gender
            if "gender" in command.fields and command.gender is not None
            else current.gender
        )
        birth_date = (
            command.birth_date if "birth_date" in command.fields else current.birth_date
        )
        avatar_color = (
            command.avatar_color
            if "avatar_color" in command.fields and command.avatar_color is not None
            else current.avatar_color
        )
        avatar_kind = (
            command.avatar_kind
            if "avatar_kind" in command.fields and command.avatar_kind is not None
            else current.avatar_kind
        )
        self._validate_identity(account_id, display_name)
        if not 0 <= avatar_color <= 7:
            raise AccountValidationFailed("头像颜色必须在 0 到 7 之间")
        try:
            updated = self._require_management().update_profile(
                principal.user_id,
                AccountProfileWrite(
                    account_id=account_id,
                    display_name=self._normalize_display_name(display_name),
                    gender=gender,
                    birth_date=birth_date,
                    avatar_color=avatar_color,
                    avatar_kind=avatar_kind,
                ),
            )
        except AccountPersistenceConflict as error:
            raise AccountConflict("登录账号已存在") from error
        except AccountPersistenceError as error:
            raise AccountsUnavailable("账户资料暂时不可用") from error
        if updated is None:
            raise AccountNotFound("账户不存在")
        return self._profile_result(updated)

    def change_password(
        self,
        principal: AccountPrincipal,
        command: ChangePasswordCommand,
    ) -> None:
        current = self._load_profile(principal.user_id)
        if not verify_password(command.old_password, current.password_hash):
            raise CurrentPasswordIncorrect("旧密码错误")
        if command.old_password == command.new_password:
            raise PasswordReuseRejected("新密码不能与旧密码相同")
        try:
            validate_password_strength(command.new_password)
        except PasswordPolicyError as error:
            raise AccountValidationFailed(str(error)) from error
        try:
            self._require_management().change_password(
                principal.user_id,
                hash_password(command.new_password),
                command.current_session_token,
            )
        except AccountPersistenceError as error:
            raise AccountsUnavailable("密码暂时无法更新") from error

    def update_theme(
        self,
        principal: AccountPrincipal,
        command: UpdateThemeCommand,
    ) -> None:
        try:
            self._require_management().update_theme(
                principal.user_id, command.theme_key
            )
        except AccountPersistenceError as error:
            raise AccountsUnavailable("主题暂时无法更新") from error

    def update_default_landing_page(
        self,
        principal: AccountPrincipal,
        command: UpdateLandingPageCommand,
    ) -> None:
        self.require_manager(principal)
        try:
            self._require_management().update_default_landing_page(
                principal.user_id, command.default_landing_page
            )
        except AccountPersistenceError as error:
            raise AccountsUnavailable("默认页面暂时无法更新") from error

    def upload_avatar(
        self,
        principal: AccountPrincipal,
        command: UploadAvatarCommand,
    ) -> None:
        self._validate_avatar(command.content_type, command.content)
        avatar_store = self._require_avatars()
        try:
            stored = avatar_store.store(
                principal.user_id, command.content_type, command.content
            )
            self._require_management().update_avatar_path(
                principal.user_id, stored.relative_path
            )
        except AccountPersistenceError as error:
            raise AccountsUnavailable("头像暂时无法保存") from error

    def get_avatar(
        self,
        principal: AccountPrincipal,
        query: GetAvatarQuery,
    ) -> AvatarResult:
        _ = query
        return self._avatar_result(principal.user_id)

    def get_managed_avatar(
        self,
        principal: AccountPrincipal,
        query: GetManagedAvatarQuery,
    ) -> AvatarResult:
        self.require_manager(principal)
        target = self._load_managed_account(query.user_id)
        return self._avatar_result(target.user_id)

    def list_managed_accounts(
        self,
        principal: AccountPrincipal,
        query: ListManagedAccountsQuery,
    ) -> ManagedAccountsResult:
        _ = query
        self.require_manager(principal)
        try:
            records = self._require_management().list_managed_accounts().items
            default_limit = self._require_quota_policy().default_elfie_limit()
        except (AccountPersistenceError, AccountQuotaPolicyError) as error:
            raise AccountsUnavailable("账户列表暂时不可用") from error
        return ManagedAccountsResult(
            items=tuple(
                self._managed_result(record, default_limit) for record in records
            )
        )

    def create_managed_account(
        self,
        principal: AccountPrincipal,
        command: CreateManagedAccountCommand,
    ) -> ManagedAccountResult:
        self.require_manager(principal)
        if command.role == "admin" and principal.role != "owner":
            raise AccountForbidden("只有 Owner 可以新增 Admin")
        self._validate_identity(command.account_id, command.display_name)
        try:
            validate_password_strength(command.password)
        except PasswordPolicyError as error:
            raise AccountValidationFailed(str(error)) from error
        try:
            user_id = self._require_management().create_managed_account(
                account_id=command.account_id.strip(),
                display_name=self._normalize_display_name(command.display_name),
                password_hash=hash_password(command.password),
                role=command.role,
            )
            record = self._load_managed_account(user_id)
            default_limit = self._require_quota_policy().default_elfie_limit()
        except AccountPersistenceConflict as error:
            raise AccountConflict("登录账号已存在") from error
        except AccountPersistenceCapacityError as error:
            raise ManagedAccountCapacityReached("账号人数或 Admin 名额已满") from error
        except (AccountPersistenceError, AccountQuotaPolicyError) as error:
            raise AccountsUnavailable("账户暂时无法创建") from error
        return self._managed_result(record, default_limit)

    def update_managed_quota(
        self,
        principal: AccountPrincipal,
        command: UpdateManagedAccountQuotaCommand,
    ) -> ManagedAccountResult:
        target = self._require_managed_target(principal, command.user_id)
        quota = command.elfie_quota_override
        if quota is not None and not 1 <= quota <= _MAX_ELFIE_QUOTA:
            raise AccountValidationFailed("精灵额度必须在 1 到 32 之间")
        try:
            updated = self._require_management().update_managed_quota(
                target.user_id, quota
            )
            if not updated:
                raise AccountPersistenceTargetError
            record = self._load_managed_account(target.user_id)
            default_limit = self._require_quota_policy().default_elfie_limit()
        except AccountPersistenceTargetError as error:
            raise AccountForbidden("目标账号已无法管理") from error
        except (AccountPersistenceError, AccountQuotaPolicyError) as error:
            raise AccountsUnavailable("账户额度暂时无法更新") from error
        return self._managed_result(record, default_limit)

    def delete_managed_account(
        self,
        principal: AccountPrincipal,
        command: DeleteManagedAccountCommand,
    ) -> None:
        target = self._require_managed_target(principal, command.user_id)
        if target.elfie_count > 0:
            raise ManagedAccountHasElfies("该用户仍有名下精灵")
        try:
            if not self._require_management().delete_managed_account(target.user_id):
                raise ManagedAccountHasElfies("该用户仍有名下精灵")
        except AccountPersistenceError as error:
            raise AccountsUnavailable("账户暂时无法删除") from error

    def reset_managed_password(
        self,
        principal: AccountPrincipal,
        command: ResetManagedAccountPasswordCommand,
    ) -> TemporaryPasswordResult:
        target = self._require_managed_target(principal, command.user_id)
        temporary_password = "".join(
            secrets.choice(_TEMPORARY_PASSWORD_ALPHABET)
            for _ in range(_TEMPORARY_PASSWORD_LENGTH)
        )
        try:
            self._require_management().reset_managed_password(
                target.user_id, hash_password(temporary_password)
            )
        except AccountPersistenceTargetError as error:
            raise AccountForbidden("目标账号已无法管理") from error
        except AccountPersistenceError as error:
            raise AccountsUnavailable("账户密码暂时无法重置") from error
        return TemporaryPasswordResult(temporary_password=temporary_password)

    def get_owner_account(self, query: GetOwnerAccountQuery) -> OwnerAccountResult:
        _ = query
        try:
            record = self._require_management().find_owner_account()
        except AccountPersistenceError as error:
            raise AccountsUnavailable("Owner 账户暂时不可用") from error
        if record is None:
            raise AccountNotFound("No Owner account in database")
        return OwnerAccountResult(
            user_id=record.user_id,
            account_id=record.account_id,
            display_name=record.display_name,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def recover_owner_account(
        self, command: RecoverOwnerAccountCommand
    ) -> OwnerAccountResult:
        self._validate_identity(command.account_id, None)
        try:
            validate_password_strength(command.new_password)
        except PasswordPolicyError as error:
            raise AccountValidationFailed(str(error)) from error
        current = self.get_owner_account(GetOwnerAccountQuery())
        try:
            record = self._require_management().recover_owner_account(
                current.user_id,
                command.account_id.strip(),
                hash_password(command.new_password),
            )
        except AccountPersistenceConflict as error:
            raise AccountConflict("登录账号已存在") from error
        except AccountPersistenceError as error:
            raise AccountsUnavailable("Owner 账户暂时无法恢复") from error
        if record is None:
            raise AccountNotFound("No Owner account in database")
        return OwnerAccountResult(
            user_id=record.user_id,
            account_id=record.account_id,
            display_name=record.display_name,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _authenticated_session(
        self, credentials: AccountCredentials, policy: SecurityPolicy
    ) -> AuthenticatedSession:
        principal = AccountPrincipal(
            user_id=credentials.user_id,
            account_id=credentials.account_id,
            role=parse_account_role(credentials.role),
            default_landing_page=credentials.default_landing_page,
        )
        token = self._require_sessions().issue_session(
            principal.user_id,
            self._now() + timedelta(seconds=policy.session_ttl_seconds),
        )
        return AuthenticatedSession(
            principal=principal,
            display_name=credentials.display_name,
            session_token=token,
            ttl_seconds=policy.session_ttl_seconds,
        )

    def _rate_limiter(self, max_attempts: int, window_seconds: int) -> RateLimiter:
        key = (max_attempts, window_seconds)
        limiter = self._rate_limiters.get(key)
        if limiter is None:
            limiter = RateLimiter(max_attempts, window_seconds)
            self._rate_limiters[key] = limiter
        return limiter

    def _load_profile(self, user_id: int) -> AccountProfileRecord:
        try:
            record = self._require_management().find_profile(user_id)
        except AccountPersistenceError as error:
            raise AccountsUnavailable("账户资料暂时不可用") from error
        if record is None:
            raise AccountNotFound("账户不存在")
        return record

    def _load_managed_account(self, user_id: int) -> ManagedAccountRecord:
        try:
            record = self._require_management().get_managed_account(user_id)
        except AccountPersistenceError as error:
            raise AccountsUnavailable("账户资料暂时不可用") from error
        if record is None:
            raise AccountNotFound("用户不存在")
        return record

    def _require_managed_target(
        self, principal: AccountPrincipal, user_id: int
    ) -> ManagedAccountRecord:
        self.require_manager(principal)
        target = self._load_managed_account(user_id)
        if not can_manage_role(principal.role, target.role):
            raise AccountForbidden("只能管理低于当前角色的账号")
        return target

    def _avatar_result(self, user_id: int) -> AvatarResult:
        profile = self._load_profile(user_id)
        if profile.avatar_path is None:
            raise AvatarNotFound("尚未上传头像")
        try:
            stored = self._require_avatars().load(user_id, profile.avatar_path)
        except AccountPersistenceError as error:
            raise AccountsUnavailable("头像暂时不可用") from error
        if stored is None:
            raise AvatarNotFound("头像文件不存在")
        return AvatarResult(content_type=stored.content_type, content=stored.content)

    @staticmethod
    def _profile_result(record: AccountProfileRecord) -> AccountProfileResult:
        return AccountProfileResult(
            user_id=record.user_id,
            account_id=record.account_id,
            display_name=record.display_name,
            gender=record.gender,
            birth_date=record.birth_date,
            role=record.role,
            has_avatar=record.avatar_path is not None,
            avatar_color=record.avatar_color,
            avatar_kind=record.avatar_kind,
            theme_key=record.theme_key,
            default_landing_page=record.default_landing_page,
            created_at=record.created_at,
            elfie_count=record.elfie_count,
        )

    @staticmethod
    def _managed_result(
        record: ManagedAccountRecord, default_limit: int
    ) -> ManagedAccountResult:
        override = record.elfie_quota_override
        return ManagedAccountResult(
            user_id=record.user_id,
            account_id=record.account_id,
            display_name=record.display_name,
            role=record.role,
            gender=record.gender,
            birth_date=record.birth_date,
            presence=record.presence,
            last_seen_at=record.last_seen_at,
            language=record.language,
            created_at=record.created_at,
            elfie_count=record.elfie_count,
            elfie_quota_override=override,
            effective_elfie_limit=default_limit if override is None else override,
            has_avatar=record.avatar_path is not None,
        )

    @staticmethod
    def _owner_result(record: OwnerAccountRecord) -> OwnerAccountResult:
        return OwnerAccountResult(
            user_id=record.user_id,
            account_id=record.account_id,
            display_name=record.display_name,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _validate_identity(account_id: str, display_name: Optional[str]) -> None:
        normalized = account_id.strip()
        if not _MIN_ACCOUNT_ID_LENGTH <= len(normalized) <= _MAX_ACCOUNT_ID_LENGTH:
            raise AccountValidationFailed("登录账号去除首尾空格后必须为 3-32 个字符")
        if (
            display_name is not None
            and len(display_name.strip()) > _MAX_DISPLAY_NAME_LENGTH
        ):
            raise AccountValidationFailed("显示名称最多 64 个字符")

    @staticmethod
    def _normalize_display_name(display_name: Optional[str]) -> Optional[str]:
        if display_name is None:
            return None
        return display_name.strip() or None

    @staticmethod
    def _validate_avatar(content_type: str, content: bytes) -> None:
        if content_type not in _AVATAR_EXTENSIONS:
            raise AvatarMediaTypeUnsupported("头像仅支持 PNG、JPEG 或 WebP 图片")
        if not content or len(content) > _MAX_AVATAR_BYTES:
            raise AvatarTooLarge("头像不能为空且不得超过 2 MiB")
        if content_type == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n"):
            return
        if content_type == "image/jpeg" and content.startswith(b"\xff\xd8\xff"):
            return
        if (
            content_type == "image/webp"
            and len(content) >= 12
            and content[:4] == b"RIFF"
            and content[8:12] == b"WEBP"
        ):
            return
        raise AvatarContentInvalid("头像内容与图片格式不匹配")

    def _require_management(self) -> AccountManagementPort:
        if self._management is None:
            raise AccountsUnavailable("账户管理服务未装配")
        return self._management

    def _require_sessions(self) -> AccountSessionPort:
        if self._sessions is None:
            raise AccountsUnavailable("账户会话服务未装配")
        return self._sessions

    def _require_security_policy(self) -> SecurityPolicyPort:
        if self._security_policy is None:
            raise AccountsUnavailable("账户安全策略未装配")
        return self._security_policy

    def _require_avatars(self) -> AccountAvatarPort:
        if self._avatars is None:
            raise AccountsUnavailable("头像服务未装配")
        return self._avatars

    def _require_quota_policy(self) -> AccountQuotaPolicyPort:
        if self._quota_policy is None:
            raise AccountsUnavailable("账户额度策略未装配")
        return self._quota_policy


__all__ = ("AccountsService", "RateLimiter")
