"""Cost-aware policy and stable identity for Provider model validation."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Mapping

from infrastructure.models.provider_records import (
    ProviderConnection,
    ProviderModelRecord,
)
from infrastructure.models.providers.catalog import ProviderCatalog
from infrastructure.models.providers.profiles import get_product

ValidationMode = Literal["full", "cached", "heartbeat"]

FULL_CACHE_WINDOW = timedelta(hours=24)
HEARTBEAT_WINDOW = timedelta(days=30)
SecretResolver = Callable[[str], str]


def _empty_secret(_name: str) -> str:
    return ""


@dataclass(frozen=True)
class ValidationDecision:
    """The least expensive validation operation allowed by current evidence."""

    mode: ValidationMode
    fingerprint: str
    representative_model_id: str | None
    source_run_id: str | None
    full_checked_at: str | None
    full_status: str | None
    reason: str


@dataclass(frozen=True)
class _FullValidationSnapshot:
    run_id: str
    checked_at: datetime
    status: str
    fingerprint: str
    model_ids: tuple[str, ...]


def active_validation_models(
    connection: ProviderConnection,
) -> tuple[ProviderModelRecord, ...]:
    """Return configured models that are enabled for subscription validation."""
    return tuple(
        model
        for model in connection.models
        if not model.hidden and not model.retired and model.discovery_state == "present"
    )


def representative_model_id(
    connection: ProviderConnection,
    *,
    catalog: ProviderCatalog,
) -> str | None:
    """Choose the profile test model, then a deterministic active model."""
    active = active_validation_models(connection)
    if not active:
        return None
    profile = get_product(connection.catalog_id, catalog=catalog)
    profile_test_model = profile.test_model.strip() if profile else ""
    selected = next(
        (
            model.endpoint_model_id
            for model in active
            if model.endpoint_model_id == profile_test_model
            or model.display_name == profile_test_model
            or model.canonical_model_id == profile_test_model
        ),
        None,
    )
    if selected is not None:
        return selected
    return min(model.endpoint_model_id for model in active)


def connection_validation_fingerprint(
    connection: ProviderConnection,
    *,
    secret_resolver: SecretResolver = _empty_secret,
) -> str:
    """Build a non-secret fingerprint for the effective validation inputs."""
    payload = _connection_fingerprint_payload(
        connection,
        secret_resolver=secret_resolver,
    )
    payload["models"] = [
        _model_fingerprint(model)
        for model in sorted(
            active_validation_models(connection),
            key=lambda item: item.endpoint_model_id,
        )
    ]
    return _hash_fingerprint(payload)


def connection_reachability_fingerprint(
    connection: ProviderConnection,
    *,
    secret_resolver: SecretResolver = _empty_secret,
) -> str:
    """Build a transport/auth fingerprint independent of model inventory."""
    return _hash_fingerprint(
        _connection_fingerprint_payload(
            connection,
            secret_resolver=secret_resolver,
        )
    )


def _connection_fingerprint_payload(
    connection: ProviderConnection,
    *,
    secret_resolver: SecretResolver,
) -> dict[str, Any]:
    secret_name = _credential_name(connection)
    secret_revision, cacheable = _credential_revision(secret_name, secret_resolver)
    return {
        "catalog_id": connection.catalog_id,
        "api_base": connection.api_base,
        "api_mode": connection.api_mode,
        "auth_type": connection.auth_type,
        "credential_ref": secret_name,
        "credential_revision": secret_revision,
        "credential_cacheable": cacheable,
    }


def _hash_fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def choose_validation_mode(
    connection: ProviderConnection,
    latest: Mapping[str, Any],
    *,
    catalog: ProviderCatalog,
    now: datetime | None = None,
    force_full: bool = False,
    secret_resolver: SecretResolver = _empty_secret,
) -> ValidationDecision:
    """Choose full, cached, or heartbeat validation without making a request."""
    current_time = _utc(now or datetime.now(timezone.utc))
    fingerprint = connection_validation_fingerprint(
        connection, secret_resolver=secret_resolver
    )
    representative = representative_model_id(connection, catalog=catalog)
    active_ids = tuple(
        sorted(
            model.endpoint_model_id for model in active_validation_models(connection)
        )
    )
    if force_full:
        return _full_decision(fingerprint, representative, "强制全量验证")
    if not active_ids:
        return _full_decision(fingerprint, representative, "没有可验证模型")
    if not _credential_cacheable(connection, secret_resolver):
        return _full_decision(fingerprint, representative, "凭据来自进程环境")

    snapshot = _snapshot_from_report(latest)
    if snapshot is None:
        return _full_decision(fingerprint, representative, "没有完整验证记录")
    if snapshot.fingerprint != fingerprint:
        return _full_decision(fingerprint, representative, "配置或凭据已变化")
    if snapshot.model_ids != active_ids:
        return _full_decision(fingerprint, representative, "模型列表已变化")

    latest_checked_at = _parse_timestamp(latest.get("checked_at"))
    if latest_checked_at is not None:
        latest_age = max(current_time - latest_checked_at, timedelta(0))
        if latest_age <= FULL_CACHE_WINDOW:
            return ValidationDecision(
                mode="cached",
                fingerprint=fingerprint,
                representative_model_id=representative,
                source_run_id=snapshot.run_id,
                full_checked_at=snapshot.checked_at.isoformat(),
                full_status=snapshot.status,
                reason="最近一次验证结果仍在 24 小时缓存期内",
            )

    age = max(current_time - snapshot.checked_at, timedelta(0))
    if age <= FULL_CACHE_WINDOW:
        return ValidationDecision(
            mode="cached",
            fingerprint=fingerprint,
            representative_model_id=representative,
            source_run_id=snapshot.run_id,
            full_checked_at=snapshot.checked_at.isoformat(),
            full_status=snapshot.status,
            reason="完整验证结果仍在 24 小时缓存期内",
        )
    if age <= HEARTBEAT_WINDOW:
        return ValidationDecision(
            mode="heartbeat",
            fingerprint=fingerprint,
            representative_model_id=representative,
            source_run_id=snapshot.run_id,
            full_checked_at=snapshot.checked_at.isoformat(),
            full_status=snapshot.status,
            reason=("完整验证结果已超过 24 小时，需要一次代表模型心跳"),
        )
    return _full_decision(
        fingerprint,
        representative,
        "完整验证结果已超过 30 天",
    )


def _full_decision(
    fingerprint: str,
    representative: str | None,
    reason: str,
) -> ValidationDecision:
    return ValidationDecision(
        mode="full",
        fingerprint=fingerprint,
        representative_model_id=representative,
        source_run_id=None,
        full_checked_at=None,
        full_status=None,
        reason=reason,
    )


def _snapshot_from_report(latest: Mapping[str, Any]) -> _FullValidationSnapshot | None:
    metadata = latest.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    if metadata.get("validation_mode") not in {"full", "heartbeat"}:
        return None
    run_id = metadata.get("full_run_id")
    checked_at = metadata.get("full_checked_at")
    fingerprint = metadata.get("config_fingerprint")
    model_ids = metadata.get("model_ids")
    if not isinstance(run_id, str) or not run_id:
        return None
    if not isinstance(checked_at, str) or not checked_at:
        return None
    if not isinstance(fingerprint, str) or not fingerprint:
        return None
    if not isinstance(model_ids, (list, tuple)) or not all(
        isinstance(model_id, str) for model_id in model_ids
    ):
        return None
    parsed = _parse_timestamp(checked_at)
    if parsed is None:
        return None
    return _FullValidationSnapshot(
        run_id=run_id,
        checked_at=parsed,
        status=str(metadata.get("full_status") or latest.get("status") or "failed"),
        fingerprint=fingerprint,
        model_ids=tuple(sorted(model_ids)),
    )


def _model_fingerprint(model: ProviderModelRecord) -> dict[str, Any]:
    # Capability declarations and probe evidence are channel observations, not
    # stable text-validation inputs.  Capability probes persist their result
    # back onto the model record for UI and inventory projections; including
    # those fields here would immediately invalidate the full model evidence
    # that was just recorded (especially when an undeclared channel becomes
    # verified).  The immutable report observations carry channel-specific
    # proof, while the stable endpoint/profile fields below keep text evidence
    # bound to the actual model configuration.
    return {
        "id": model.endpoint_model_id,
        "display_name": model.display_name,
        "canonical_model_id": model.canonical_model_id,
        "source": model.source,
        "request_profile_id": model.request_profile_id,
        "request_profile_version": model.request_profile_version,
        "context_window_tokens": model.context_window_tokens,
        "max_output_tokens": model.max_output_tokens,
        "hidden": model.hidden,
        "retired": model.retired,
    }


def _credential_name(connection: ProviderConnection) -> str:
    return connection.credential_ref or (
        f"ELFIE_PROVIDER_{connection.connection_id.upper()}_API_KEY"
    )


def _credential_revision(
    secret_name: str,
    secret_resolver: SecretResolver,
) -> tuple[str, bool]:
    if secret_name in os.environ:
        return "process-environment", False
    secret_value = secret_resolver(secret_name)
    if not secret_value:
        return "missing", True
    return hashlib.sha256(secret_value.encode("utf-8")).hexdigest(), True


def _credential_cacheable(
    connection: ProviderConnection,
    secret_resolver: SecretResolver,
) -> bool:
    return _credential_revision(_credential_name(connection), secret_resolver)[1]


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
