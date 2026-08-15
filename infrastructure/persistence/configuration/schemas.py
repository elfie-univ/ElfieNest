"""Strict schemas for the registered application configuration documents.

The registry owns document identity and lifecycle metadata.  This module owns
the small, technical shape checks that must happen before a document reaches a
semantic owner.  Detailed Provider and Model semantics remain in their owning
Infrastructure modules.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Iterable

from infrastructure.persistence.configuration.documents import ConfigDocumentId


class ConfigSchemaError(ValueError):
    """A registered configuration document violates its declared shape."""


def validate_registered_document(
    document_id: ConfigDocumentId,
    document: Mapping[str, Any],
    path: Path,
) -> None:
    """Validate one registered document before semantic consumers see it."""

    label = f"{document_id.value} ({path})"
    if document_id is ConfigDocumentId.SYSTEM_DEFAULTS:
        _validate_system_defaults(document, label)
    elif document_id is ConfigDocumentId.RUNTIME_SETTINGS:
        _validate_runtime_settings(document, label)
    elif document_id is ConfigDocumentId.TOOL_DEFAULTS:
        _validate_tools_document(document, label, partial=False)
    elif document_id is ConfigDocumentId.TOOL_SETTINGS:
        _validate_tools_document(document, label, partial=True)
    elif document_id is ConfigDocumentId.ENERGY_DEFAULTS:
        _validate_energy_defaults(document, label)
    elif document_id is ConfigDocumentId.SELFHOOD_DEFAULTS:
        _validate_selfhood_defaults(document, label)
    elif document_id is ConfigDocumentId.EMOTION_EXPRESSIONS:
        _validate_emotion_defaults(document, label)
    elif document_id is ConfigDocumentId.NEST_DEFAULTS:
        _validate_nest_defaults(document, label)
    elif document_id is ConfigDocumentId.MODEL_CATALOG:
        _validate_model_catalog_shape(document, label)
    elif document_id in (
        ConfigDocumentId.PROVIDER_CATALOG,
        ConfigDocumentId.PROVIDER_CATALOG_OVERRIDE,
    ):
        _validate_provider_catalog_shape(document, label)
    elif document_id is ConfigDocumentId.PROVIDER_CONNECTIONS:
        _validate_provider_connections_shape(document, label)
    elif document_id is ConfigDocumentId.AUTH_ENV:
        raise ConfigSchemaError(f"{label} 是 secret 文档，必须通过 secret Adapter 读取")


def _validate_system_defaults(document: Mapping[str, Any], label: str) -> None:
    _keys(document, {"version", "system"}, label)
    system = _object(document.get("system"), f"{label}.system")
    _validate_system(system, f"{label}.system", partial=False)


def _validate_runtime_settings(document: Mapping[str, Any], label: str) -> None:
    _keys(
        document,
        {
            "version",
            "config_version",
            "system",
            "models",
            "runtime_policy",
            "ollama_host",
            "energy_threshold_fast",
            "complexity_threshold_deep",
            "temperature",
            "max_tokens",
        },
        label,
    )
    if "system" in document:
        _validate_system(
            _object(document["system"], f"{label}.system"),
            f"{label}.system",
            partial=True,
            allow_runtime_extensions=True,
        )
    if "config_version" in document:
        _positive_int(document["config_version"], f"{label}.config_version")
    if "models" in document:
        _mapping_of_mappings(document["models"], f"{label}.models")
    if "runtime_policy" in document:
        _object(document["runtime_policy"], f"{label}.runtime_policy")
    if "ollama_host" in document:
        _string(document["ollama_host"], f"{label}.ollama_host")
    if "energy_threshold_fast" in document:
        _number(document["energy_threshold_fast"], f"{label}.energy_threshold_fast")
    if "complexity_threshold_deep" in document:
        _positive_int(
            document["complexity_threshold_deep"],
            f"{label}.complexity_threshold_deep",
        )
    if "temperature" in document:
        temperature = _number(document["temperature"], f"{label}.temperature")
        if not 0.0 <= temperature <= 2.0:
            raise ConfigSchemaError(f"{label}.temperature 必须在 0 到 2 之间")
    if "max_tokens" in document:
        _positive_int(document["max_tokens"], f"{label}.max_tokens")


def _validate_system(
    system: Mapping[str, Any],
    label: str,
    *,
    partial: bool,
    allow_runtime_extensions: bool = False,
) -> None:
    section_names = {"adoption", "engine", "security", "model_execution"}
    if not partial:
        _keys(system, section_names, label)
    if not partial:
        _require_keys(system, section_names, label)
    if "adoption" in system:
        adoption = _object(system["adoption"], f"{label}.adoption")
        adoption_fields = {"max_elfies_per_user", "personality_presets_enabled"}
        if allow_runtime_extensions:
            adoption_fields.add("allowed_species_ids")
        _keys(
            adoption,
            adoption_fields,
            f"{label}.adoption",
        )
        if not partial:
            _require_keys(
                adoption,
                {"max_elfies_per_user", "personality_presets_enabled"},
                f"{label}.adoption",
            )
        if "allowed_species_ids" in adoption:
            _string_list(
                adoption["allowed_species_ids"],
                f"{label}.adoption.allowed_species_ids",
                allow_empty=True,
            )
        _validate_optional_positive_int(
            adoption,
            "max_elfies_per_user",
            f"{label}.adoption",
        )
        if "personality_presets_enabled" in adoption:
            _boolean_map(
                adoption["personality_presets_enabled"],
                f"{label}.adoption.personality_presets_enabled",
            )
    if "engine" in system:
        engine = _object(system["engine"], f"{label}.engine")
        _keys(engine, {"tick_interval_sec"}, f"{label}.engine")
        if not partial:
            _require_keys(engine, {"tick_interval_sec"}, f"{label}.engine")
        if "tick_interval_sec" in engine:
            _positive_number(
                engine["tick_interval_sec"],
                f"{label}.engine.tick_interval_sec",
            )
    if "security" in system:
        security = _object(system["security"], f"{label}.security")
        _keys(
            security,
            {"session_ttl_days", "rate_limit"},
            f"{label}.security",
        )
        if not partial:
            _require_keys(
                security,
                {"session_ttl_days", "rate_limit"},
                f"{label}.security",
            )
        _validate_optional_positive_int(
            security,
            "session_ttl_days",
            f"{label}.security",
        )
        if "rate_limit" in security:
            rate_limit = _object(
                security["rate_limit"],
                f"{label}.security.rate_limit",
            )
            _keys(
                rate_limit,
                {"max_attempts", "window_seconds"},
                f"{label}.security.rate_limit",
            )
            if not partial:
                _require_keys(
                    rate_limit,
                    {"max_attempts", "window_seconds"},
                    f"{label}.security.rate_limit",
                )
            _validate_optional_positive_int(
                rate_limit,
                "max_attempts",
                f"{label}.security.rate_limit",
            )
            _validate_optional_positive_int(
                rate_limit,
                "window_seconds",
                f"{label}.security.rate_limit",
            )
    if "model_execution" in system:
        model_execution = _object(
            system["model_execution"],
            f"{label}.model_execution",
        )
        _keys(
            model_execution,
            {
                "ollama_host",
                "energy_threshold_fast",
                "complexity_threshold_deep",
                "temperature",
                "max_tokens",
            },
            f"{label}.model_execution",
        )
        if not partial:
            _require_keys(
                model_execution,
                {
                    "ollama_host",
                    "energy_threshold_fast",
                    "complexity_threshold_deep",
                    "temperature",
                    "max_tokens",
                },
                f"{label}.model_execution",
            )
        if "ollama_host" in model_execution:
            _string(
                model_execution["ollama_host"], f"{label}.model_execution.ollama_host"
            )
        if "energy_threshold_fast" in model_execution:
            _positive_number(
                model_execution["energy_threshold_fast"],
                f"{label}.model_execution.energy_threshold_fast",
            )
        if "complexity_threshold_deep" in model_execution:
            _positive_int(
                model_execution["complexity_threshold_deep"],
                f"{label}.model_execution.complexity_threshold_deep",
            )
        if "temperature" in model_execution:
            temperature = _number(
                model_execution["temperature"],
                f"{label}.model_execution.temperature",
            )
            if not 0.0 <= temperature <= 2.0:
                raise ConfigSchemaError(
                    f"{label}.model_execution.temperature 必须在 0 到 2 之间"
                )
        if "max_tokens" in model_execution:
            _positive_int(
                model_execution["max_tokens"],
                f"{label}.model_execution.max_tokens",
            )
    if not partial:
        for section_name in ("adoption", "engine", "security", "model_execution"):
            section = _object(system[section_name], f"{label}.{section_name}")
            _require_nonempty(section, f"{label}.{section_name}")


def _validate_tools_document(
    document: Mapping[str, Any],
    label: str,
    *,
    partial: bool,
) -> None:
    _keys(document, {"version", "tools"}, label)
    tools = _object(document.get("tools"), f"{label}.tools")
    allowed_tools = {"web_search", "local_file"}
    _keys(tools, allowed_tools, f"{label}.tools")
    if not partial:
        _require_keys(tools, allowed_tools, f"{label}.tools")
    for tool_name, raw_config in tools.items():
        config = _object(raw_config, f"{label}.tools.{tool_name}")
        if tool_name == "web_search":
            allowed = {
                "enabled",
                "provider",
                "api_base",
                "api_key_env",
                "max_results",
                "max_result_bytes",
                "timeout_seconds",
                "max_tool_calls",
                "max_total_result_bytes",
            }
            _keys(config, allowed, f"{label}.tools.{tool_name}")
            _validate_optional_bool(config, "enabled", f"{label}.tools.{tool_name}")
            _validate_optional_string(config, "provider", f"{label}.tools.{tool_name}")
            _validate_optional_string(config, "api_base", f"{label}.tools.{tool_name}")
            _validate_optional_string(
                config,
                "api_key_env",
                f"{label}.tools.{tool_name}",
            )
            for field in (
                "max_results",
                "max_result_bytes",
                "max_tool_calls",
                "max_total_result_bytes",
            ):
                _validate_optional_positive_int(
                    config, field, f"{label}.tools.{tool_name}"
                )
            _validate_optional_positive_number(
                config,
                "timeout_seconds",
                f"{label}.tools.{tool_name}",
            )
        else:
            allowed = {
                "enabled",
                "root",
                "root_policy",
                "max_read_bytes",
                "max_items",
                "max_result_bytes",
                "max_tool_calls",
                "max_total_result_bytes",
            }
            _keys(config, allowed, f"{label}.tools.{tool_name}")
            _validate_optional_bool(config, "enabled", f"{label}.tools.{tool_name}")
            for field in ("root", "root_policy"):
                _validate_optional_string(config, field, f"{label}.tools.{tool_name}")
            for field in (
                "max_read_bytes",
                "max_items",
                "max_result_bytes",
                "max_tool_calls",
                "max_total_result_bytes",
            ):
                _validate_optional_positive_int(
                    config, field, f"{label}.tools.{tool_name}"
                )
    if not partial:
        for tool_name in allowed_tools:
            _require_nonempty(
                _object(tools[tool_name], f"{label}.tools.{tool_name}"),
                f"{label}.tools.{tool_name}",
            )


def _validate_energy_defaults(document: Mapping[str, Any], label: str) -> None:
    _keys(document, {"version", "limits"}, label)
    limits = _object(document.get("limits"), f"{label}.limits")
    _keys(limits, {"energy", "fatigue", "runtime_usage"}, f"{label}.limits")
    _require_keys(limits, {"energy", "fatigue", "runtime_usage"}, f"{label}.limits")
    energy = _object(limits.get("energy"), f"{label}.limits.energy")
    energy_fields = {
        "max_value",
        "initial_value",
        "depletion_rate_per_sec",
        "depletion_per_remote_chat",
        "depletion_per_local_chat",
        "recovery_rate_sleep_per_sec",
    }
    _keys(energy, energy_fields, f"{label}.limits.energy")
    _require_keys(energy, energy_fields, f"{label}.limits.energy")
    fatigue = _object(limits.get("fatigue"), f"{label}.limits.fatigue")
    fatigue_fields = {
        "initial_value",
        "max_value",
        "accumulation_rate_per_sec",
        "decay_rate_sleep_per_sec",
        "hibernation_threshold",
        "wakeup_threshold",
    }
    _keys(fatigue, fatigue_fields, f"{label}.limits.fatigue")
    _require_keys(fatigue, fatigue_fields, f"{label}.limits.fatigue")
    for section_name, section in (("energy", energy), ("fatigue", fatigue)):
        for field, value in section.items():
            _number(value, f"{label}.limits.{section_name}.{field}")
    usage = _object(limits.get("runtime_usage"), f"{label}.limits.runtime_usage")
    _keys(
        usage,
        {"daily_token_soft_limit", "observe_only"},
        f"{label}.limits.runtime_usage",
    )
    _positive_int(
        usage.get("daily_token_soft_limit"),
        f"{label}.limits.runtime_usage.daily_token_soft_limit",
    )
    _boolean(usage.get("observe_only"), f"{label}.limits.runtime_usage.observe_only")


def _validate_selfhood_defaults(document: Mapping[str, Any], label: str) -> None:
    _keys(document, {"version", "metadata", "big_five", "speech_style"}, label)
    metadata = _object(document.get("metadata"), f"{label}.metadata")
    _keys(metadata, {"name", "version", "description"}, f"{label}.metadata")
    _require_keys(metadata, {"name", "version", "description"}, f"{label}.metadata")
    for field in ("name", "version", "description"):
        _string(metadata.get(field), f"{label}.metadata.{field}")
    big_five = _object(document.get("big_five"), f"{label}.big_five")
    traits = {
        "openness",
        "conscientiousness",
        "extraversion",
        "agreeableness",
        "neuroticism",
    }
    _keys(big_five, traits, f"{label}.big_five")
    _require_keys(big_five, traits, f"{label}.big_five")
    for field, value in big_five.items():
        score = _number(value, f"{label}.big_five.{field}")
        if not 0.0 <= score <= 1.0:
            raise ConfigSchemaError(f"{label}.big_five.{field} 必须在 0 到 1 之间")
    speech = _object(document.get("speech_style"), f"{label}.speech_style")
    _keys(
        speech,
        {"greetings", "mutter_templates", "verbal_ticks"},
        f"{label}.speech_style",
    )
    _require_keys(
        speech,
        {"greetings", "mutter_templates", "verbal_ticks"},
        f"{label}.speech_style",
    )
    _string_list(speech.get("greetings"), f"{label}.speech_style.greetings")
    mutters = _object(
        speech.get("mutter_templates"), f"{label}.speech_style.mutter_templates"
    )
    for mood, values in mutters.items():
        _string_list(values, f"{label}.speech_style.mutter_templates.{mood}")
    _string(speech.get("verbal_ticks"), f"{label}.speech_style.verbal_ticks")


def _validate_emotion_defaults(document: Mapping[str, Any], label: str) -> None:
    _keys(document, {"version", "emotions", "default_expression"}, label)
    emotions = _object(document.get("emotions"), f"{label}.emotions")
    for emotion_name, raw_expression in emotions.items():
        expression = _object(raw_expression, f"{label}.emotions.{emotion_name}")
        _keys(
            expression,
            {"expression", "actions", "voice_modifier", "threshold"},
            f"{label}.emotions.{emotion_name}",
        )
        _string(
            expression.get("expression"), f"{label}.emotions.{emotion_name}.expression"
        )
        _validate_emotion_actions(
            expression.get("actions"),
            f"{label}.emotions.{emotion_name}.actions",
        )
        _string(
            expression.get("voice_modifier"),
            f"{label}.emotions.{emotion_name}.voice_modifier",
        )
        _number(
            expression.get("threshold"), f"{label}.emotions.{emotion_name}.threshold"
        )
    default = _object(document.get("default_expression"), f"{label}.default_expression")
    _keys(
        default,
        {"expression", "actions", "voice_modifier"},
        f"{label}.default_expression",
    )
    _string(default.get("expression"), f"{label}.default_expression.expression")
    _string_list(
        default.get("actions"),
        f"{label}.default_expression.actions",
        allow_empty=True,
    )
    _string(default.get("voice_modifier"), f"{label}.default_expression.voice_modifier")


def _validate_nest_defaults(document: Mapping[str, Any], label: str) -> None:
    _keys(document, {"version", "nest"}, label)
    nest = _object(document.get("nest"), f"{label}.nest")
    _keys(nest, {"bed_count"}, f"{label}.nest")
    _positive_int(nest.get("bed_count"), f"{label}.nest.bed_count")


def _validate_emotion_actions(value: Any, label: str) -> None:
    actions = _object(value, label)
    levels = {"low", "medium", "high"}
    _keys(actions, levels, label)
    _require_keys(actions, levels, label)
    for level in levels:
        _string_list(actions[level], f"{label}.{level}")


def _validate_model_catalog_shape(document: Mapping[str, Any], label: str) -> None:
    _keys(document, {"version", "models", "entries"}, label)
    _object(document.get("models"), f"{label}.models")
    _object(document.get("entries"), f"{label}.entries")


def _mapping_of_mappings(value: Any, label: str) -> None:
    mapping = _object(value, label)
    for key, item in mapping.items():
        if not isinstance(key, str):
            raise ConfigSchemaError(f"{label} 的字段名必须是字符串")
        _object(item, f"{label}.{key}")


def _validate_provider_catalog_shape(
    document: Mapping[str, Any],
    label: str,
) -> None:
    _keys(
        document,
        {
            "version",
            "ollama_recommended_models",
            "brands",
            "products",
            "endpoint_model_hints",
        },
        label,
    )
    _object(document.get("brands"), f"{label}.brands")
    _object(document.get("products"), f"{label}.products")
    recommendations = document.get("ollama_recommended_models", [])
    if not isinstance(recommendations, list):
        raise ConfigSchemaError(f"{label}.ollama_recommended_models 必须是数组")
    hints = document.get("endpoint_model_hints", [])
    if not isinstance(hints, list):
        raise ConfigSchemaError(f"{label}.endpoint_model_hints 必须是数组")


def _validate_provider_connections_shape(
    document: Mapping[str, Any],
    label: str,
) -> None:
    _keys(document, {"version", "connection_counters", "connections"}, label)
    _object(document.get("connection_counters"), f"{label}.connection_counters")
    connections = _object(document.get("connections"), f"{label}.connections")
    connection_fields = {
        "catalog_id",
        "alias",
        "api_base",
        "api_mode",
        "auth_type",
        "credential_ref",
        "installation",
        "models",
        "enabled",
        "archived",
    }
    model_fields = {
        "id",
        "display_name",
        "source",
        "request_profile_id",
        "request_profile_version",
        "canonical_model_id",
        "context_window_tokens",
        "max_output_tokens",
        "supports_tools",
        "supports_vision",
        "supports_reasoning",
        "supports_structured_output",
        "capability_evidence",
        "hidden",
        "retired",
        "available",
        "discovery_state",
        "consecutive_missing",
        "last_seen_at",
    }
    for connection_id, raw_connection in connections.items():
        connection = _object(raw_connection, f"{label}.connections.{connection_id}")
        _keys(connection, connection_fields, f"{label}.connections.{connection_id}")
        models = connection.get("models", [])
        if not isinstance(models, list):
            raise ConfigSchemaError(
                f"{label}.connections.{connection_id}.models 必须是数组"
            )
        for index, raw_model in enumerate(models):
            model = _object(
                raw_model,
                f"{label}.connections.{connection_id}.models[{index}]",
            )
            _keys(
                model,
                model_fields,
                f"{label}.connections.{connection_id}.models[{index}]",
            )


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigSchemaError(f"{label} 必须是对象")
    if any(not isinstance(key, str) for key in value):
        raise ConfigSchemaError(f"{label} 的字段名必须是字符串")
    return value


def _keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ConfigSchemaError(
            f"{label} 包含未知字段: {sorted(str(item) for item in unknown)}"
        )


def _require_keys(
    value: Mapping[str, Any], required: Iterable[str], label: str
) -> None:
    missing = set(required) - set(value)
    if missing:
        raise ConfigSchemaError(
            f"{label} 缺少字段: {sorted(str(item) for item in missing)}"
        )


def _require_nonempty(value: Mapping[str, Any], label: str) -> None:
    if not value:
        raise ConfigSchemaError(f"{label} 不能为空")


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigSchemaError(f"{label} 必须是非空字符串")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigSchemaError(f"{label} 必须是数字")
    return float(value)


def _positive_number(value: Any, label: str) -> float:
    result = _number(value, label)
    if result <= 0:
        raise ConfigSchemaError(f"{label} 必须大于 0")
    return result


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigSchemaError(f"{label} 必须是大于 0 的整数")
    return value


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigSchemaError(f"{label} 必须是布尔值")
    return value


def _string_list(value: Any, label: str, *, allow_empty: bool = False) -> None:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ConfigSchemaError(f"{label} 必须是字符串数组")


def _boolean_map(value: Any, label: str) -> None:
    mapping = _object(value, label)
    if any(not isinstance(item, bool) for item in mapping.values()):
        raise ConfigSchemaError(f"{label} 必须是布尔值对象")


def _validate_optional_string(
    mapping: Mapping[str, Any], field: str, label: str
) -> None:
    if field in mapping:
        if not isinstance(mapping[field], str):
            raise ConfigSchemaError(f"{label}.{field} 必须是字符串")


def _validate_optional_bool(mapping: Mapping[str, Any], field: str, label: str) -> None:
    if field in mapping:
        _boolean(mapping[field], f"{label}.{field}")


def _validate_optional_positive_int(
    mapping: Mapping[str, Any], field: str, label: str
) -> None:
    if field in mapping:
        _positive_int(mapping[field], f"{label}.{field}")


def _validate_optional_positive_number(
    mapping: Mapping[str, Any], field: str, label: str
) -> None:
    if field in mapping:
        _positive_number(mapping[field], f"{label}.{field}")


__all__ = ("ConfigSchemaError", "validate_registered_document")
