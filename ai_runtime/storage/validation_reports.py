"""Durable, credential-free Provider and model validation reports."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from ai_runtime.storage.config_store import read_yaml_mapping, write_yaml_mapping
from ai_runtime.storage.data_home import (
    ensure_elfie_home,
    get_model_validation_dir,
    get_provider_validation_dir,
)

REPORT_VERSION = 1
_PROVIDER_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REPORT_STATUS = frozenset({"failed", "passed"})
_PROVIDER_TRIGGER = frozenset({"batch", "single"})
_MODEL_TRIGGER = frozenset({"benchmark"})


@dataclass(frozen=True)
class InvalidReportIdentityError(ValueError):
    identity: str

    def __str__(self) -> str:
        return f"验证报告标识不合法: {self.identity!r}"


def write_provider_validation_report(
    provider_id: str,
    *,
    status: str,
    checked_at: str,
    latency_ms: float | None,
    error: str | None,
    trigger: Literal["batch", "single"],
) -> Path:
    """Write one immutable Provider report and replace its latest projection."""
    _validate_provider_id(provider_id)
    _validate_status(status)
    if trigger not in _PROVIDER_TRIGGER:
        raise ValueError(f"不支持的 Provider 验证触发方式: {trigger}")
    report = {
        "version": REPORT_VERSION,
        "kind": "provider_validation",
        "provider_id": provider_id,
        "trigger": trigger,
        "checked_at": checked_at,
        "status": status,
        "latency_ms": latency_ms,
        "error": error,
    }
    return _write_report(get_provider_validation_dir() / provider_id, report)


def read_latest_provider_validation(provider_id: str) -> dict[str, Any]:
    _validate_provider_id(provider_id)
    return read_yaml_mapping(
        get_provider_validation_dir() / provider_id / "latest.yaml"
    )


def write_model_validation_report(
    provider_id: str,
    model_id: str,
    *,
    status: str,
    checked_at: str,
    latency_ms: float | None,
    latency_class: str | None,
    error: str | None,
    trigger: Literal["benchmark"],
) -> Path:
    """Write one model report without using the model ID as a path component."""
    _validate_provider_id(provider_id)
    normalized_model_id = model_id.strip()
    if not normalized_model_id or len(normalized_model_id) > 200:
        raise InvalidReportIdentityError(model_id)
    _validate_status(status)
    if trigger not in _MODEL_TRIGGER:
        raise ValueError(f"不支持的模型验证触发方式: {trigger}")
    model_key = hashlib.sha256(normalized_model_id.encode("utf-8")).hexdigest()[:16]
    report = {
        "version": REPORT_VERSION,
        "kind": "model_validation",
        "provider_id": provider_id,
        "model_id": normalized_model_id,
        "trigger": trigger,
        "checked_at": checked_at,
        "status": status,
        "latency_ms": latency_ms,
        "latency_class": latency_class,
        "error": error,
    }
    return _write_report(
        get_model_validation_dir() / provider_id / model_key,
        report,
    )


def _validate_provider_id(provider_id: str) -> None:
    if _PROVIDER_ID_PATTERN.fullmatch(provider_id) is None:
        raise InvalidReportIdentityError(provider_id)


def _validate_status(status: str) -> None:
    if status not in _REPORT_STATUS:
        raise ValueError(f"不支持的验证报告状态: {status}")


def _write_report(directory: Path, report: dict[str, Any]) -> Path:
    ensure_elfie_home()
    history_dir = directory / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    _secure_directory(directory)
    _secure_directory(history_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    history_path = history_dir / f"{stamp}.yaml"
    write_yaml_mapping(history_path, report)
    write_yaml_mapping(directory / "latest.yaml", report)
    return history_path


def _secure_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
