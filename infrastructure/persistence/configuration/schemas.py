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
    elif document_id is ConfigDocumentId.REASONING_CONSTITUTION:
        _validate_reasoning_constitution(document, label)
    elif document_id is ConfigDocumentId.EMOTION_EXPRESSIONS:
        _validate_emotion_defaults(document, label)
    elif document_id is ConfigDocumentId.EMOTION_DYNAMICS:
        _validate_emotion_dynamics(document, label)
    elif document_id is ConfigDocumentId.NEST_DEFAULTS:
        _validate_nest_defaults(document, label)
    elif document_id is ConfigDocumentId.SPECIES_CATALOG:
        _validate_species_catalog_shape(document, label)
    elif document_id is ConfigDocumentId.GENESIS_SOURCE_PACKAGE:
        _validate_genesis_source_package_shape(document, label)
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


def _validate_reasoning_constitution(document: Mapping[str, Any], label: str) -> None:
    _keys(
        document,
        {
            "version",
            "application_frame_text",
            "operating_contract_text",
            "max_prefix_bytes",
        },
        label,
    )
    _require_keys(
        document,
        {"version", "application_frame_text", "operating_contract_text"},
        label,
    )
    _positive_int(document.get("version"), f"{label}.version")
    _string(document.get("application_frame_text"), f"{label}.application_frame_text")
    _string(document.get("operating_contract_text"), f"{label}.operating_contract_text")
    if "max_prefix_bytes" in document:
        value = document.get("max_prefix_bytes")
        if isinstance(value, bool) or not isinstance(value, int) or value < 256:
            raise ConfigSchemaError(f"{label}.max_prefix_bytes 必须是不小于 256 的整数")
    reserved = (
        "[APPLICATION_FRAME]",
        "[IDENTITY_CORE]",
        "[ADAPTIVE_SELF]",
        "[OPERATING_CONTRACT]",
        "[TURN_PROTOCOL]",
        "[CURRENT_BRAIN_STATE]",
    )
    for field in ("application_frame_text", "operating_contract_text"):
        value = document.get(field)
        if isinstance(value, str) and any(
            label_text in value for label_text in reserved
        ):
            raise ConfigSchemaError(f"{label}.{field} 不能包含固定头部标签")


def _validate_emotion_defaults(document: Mapping[str, Any], label: str) -> None:
    _keys(document, {"version", "emotions", "default_expression"}, label)
    emotions = _object(document.get("emotions"), f"{label}.emotions")
    required_emotions = {
        "happiness",
        "sadness",
        "anger",
        "fear",
        "surprise",
        "disgust",
    }
    if set(emotions) != required_emotions:
        raise ConfigSchemaError(f"{label}.emotions 必须恰好包含六种情绪")
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
        threshold = _number(
            expression.get("threshold"), f"{label}.emotions.{emotion_name}.threshold"
        )
        if not 0.0 <= threshold <= 1.0:
            raise ConfigSchemaError(
                f"{label}.emotions.{emotion_name}.threshold 必须在 0 到 1 之间"
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


def _validate_emotion_dynamics(document: Mapping[str, Any], label: str) -> None:
    """Validate the six-channel, bundled-only dynamic parameter document."""

    _keys(
        document,
        {
            "version",
            "channels",
            "strength_knots",
            "source_weights",
            "presentation",
            "personality",
        },
        label,
    )
    channels = _object(document.get("channels"), f"{label}.channels")
    required = {
        "happiness",
        "sadness",
        "anger",
        "fear",
        "surprise",
        "disgust",
    }
    if set(channels) != required:
        raise ConfigSchemaError(f"{label}.channels 必须恰好包含六种情绪")
    channel_fields = {
        "baseline",
        "positive_gain",
        "negative_gain",
        "half_life_seconds",
        "activation_threshold",
    }
    for name, raw in channels.items():
        channel = _object(raw, f"{label}.channels.{name}")
        _keys(channel, channel_fields, f"{label}.channels.{name}")
        _require_keys(channel, channel_fields, f"{label}.channels.{name}")
        for field in ("baseline", "activation_threshold"):
            value = _number(channel.get(field), f"{label}.channels.{name}.{field}")
            if not 0.0 <= value <= 1.0:
                raise ConfigSchemaError(
                    f"{label}.channels.{name}.{field} 必须在 0 到 1 之间"
                )
        for field in ("positive_gain", "negative_gain", "half_life_seconds"):
            _positive_number(channel.get(field), f"{label}.channels.{name}.{field}")
    knots = document.get("strength_knots")
    if not isinstance(knots, list) or len(knots) < 2:
        raise ConfigSchemaError(f"{label}.strength_knots 必须是至少两个数字")
    previous = -1.0
    for index, value in enumerate(knots):
        number = _number(value, f"{label}.strength_knots[{index}]")
        if not 0.0 <= number <= 1.0 or number < previous:
            raise ConfigSchemaError(
                f"{label}.strength_knots 必须是 0 到 1 的非降序数组"
            )
        previous = number
    weights = _object(document.get("source_weights"), f"{label}.source_weights")
    sources = {"physical", "social", "execution", "internal", "model"}
    _keys(weights, sources, f"{label}.source_weights")
    _require_keys(weights, sources, f"{label}.source_weights")
    for source, value in weights.items():
        _positive_number(value, f"{label}.source_weights.{source}")
    presentation = _object(document.get("presentation"), f"{label}.presentation")
    _keys(
        presentation,
        {"trend_threshold", "secondary_ratio"},
        f"{label}.presentation",
    )
    _require_keys(
        presentation,
        {"trend_threshold", "secondary_ratio"},
        f"{label}.presentation",
    )
    for field in ("trend_threshold", "secondary_ratio"):
        value = _number(presentation.get(field), f"{label}.presentation.{field}")
        if not 0.0 <= value <= 1.0:
            raise ConfigSchemaError(f"{label}.presentation.{field} 必须在 0 到 1 之间")
    _object(document.get("personality"), f"{label}.personality")


def _validate_nest_defaults(document: Mapping[str, Any], label: str) -> None:
    _keys(document, {"version", "nest"}, label)
    nest = _object(document.get("nest"), f"{label}.nest")
    _keys(nest, {"bed_count"}, f"{label}.nest")
    _positive_int(nest.get("bed_count"), f"{label}.nest.bed_count")


def _validate_species_catalog_shape(document: Mapping[str, Any], label: str) -> None:
    _keys(
        document,
        {
            "version",
            "schema_version",
            "catalog_version",
            "appearance_protocol_version",
            "world_package_version",
            "species",
        },
        label,
    )
    _positive_int(document.get("schema_version"), f"{label}.schema_version")
    for field in (
        "catalog_version",
        "appearance_protocol_version",
        "world_package_version",
    ):
        _string(document.get(field), f"{label}.{field}")
    species = document.get("species")
    if not isinstance(species, list) or not species:
        raise ConfigSchemaError(f"{label}.species 必须是非空数组")
    allowed = {
        "species_id",
        "package",
        "species_package_id",
        "status",
        "sort_order",
        "definition_version",
    }
    for index, raw in enumerate(species):
        item = _object(raw, f"{label}.species[{index}]")
        _keys(item, allowed, f"{label}.species[{index}]")
        for field in (
            "species_id",
            "package",
            "species_package_id",
            "definition_version",
        ):
            _string(item.get(field), f"{label}.species[{index}].{field}")
        if item.get("status") not in ("draft", "published", "retired"):
            raise ConfigSchemaError(
                f"{label}.species[{index}].status 必须是 draft/published/retired"
            )
        sort_order = item.get("sort_order")
        if (
            isinstance(sort_order, bool)
            or not isinstance(sort_order, int)
            or sort_order < 0
        ):
            raise ConfigSchemaError(
                f"{label}.species[{index}].sort_order 必须是非负整数"
            )


def _validate_genesis_source_package_shape(
    document: Mapping[str, Any], label: str
) -> None:
    """Validate the bounded, source-only Genesis package document."""

    _keys(
        document,
        {
            "version",
            "schema_version",
            "package_version",
            "world_id",
            "display_name",
            "known_region",
            "earth_relation",
            "places",
            "story_events",
            "knowledge",
            "unknown_boundaries",
            "genesis",
        },
        label,
    )
    _require_keys(
        document,
        {
            "version",
            "schema_version",
            "package_version",
            "world_id",
            "display_name",
            "known_region",
            "earth_relation",
            "places",
            "story_events",
            "knowledge",
            "unknown_boundaries",
        },
        label,
    )
    _positive_int(document.get("version"), f"{label}.version")
    _positive_int(document.get("schema_version"), f"{label}.schema_version")
    for field in ("package_version", "world_id", "display_name"):
        _string(document.get(field), f"{label}.{field}")

    region = _object(document.get("known_region"), f"{label}.known_region")
    _keys(region, {"id", "name", "aliases"}, f"{label}.known_region")
    _require_keys(region, {"id", "name", "aliases"}, f"{label}.known_region")
    _string(region.get("id"), f"{label}.known_region.id")
    _string(region.get("name"), f"{label}.known_region.name")
    _string_list(
        region.get("aliases"), f"{label}.known_region.aliases", allow_empty=True
    )

    relation = _object(document.get("earth_relation"), f"{label}.earth_relation")
    relation_fields = {
        "civilization_relation_to_earth",
        "earth_arrival_statement",
        "earth_home_name",
        "earth_home_role",
    }
    _keys(relation, relation_fields, f"{label}.earth_relation")
    _require_keys(relation, relation_fields, f"{label}.earth_relation")
    for field in relation_fields:
        _string(relation.get(field), f"{label}.earth_relation.{field}")

    places = document.get("places")
    if not isinstance(places, list) or not places:
        raise ConfigSchemaError(f"{label}.places 必须是非空数组")
    place_ids: set[str] = set()
    place_fields = {
        "id",
        "version",
        "label",
        "kind",
        "parent_id",
        "aliases",
        "description",
        "status",
    }
    for index, raw in enumerate(places):
        place = _object(raw, f"{label}.places[{index}]")
        _keys(place, place_fields, f"{label}.places[{index}]")
        _require_keys(
            place,
            {
                "id",
                "version",
                "label",
                "kind",
                "parent_id",
                "aliases",
                "description",
                "status",
            },
            f"{label}.places[{index}]",
        )
        place_id = _string(place.get("id"), f"{label}.places[{index}].id")
        if place_id in place_ids:
            raise ConfigSchemaError(f"{label}.places 出现重复 ID: {place_id}")
        place_ids.add(place_id)
        _positive_int(place.get("version"), f"{label}.places[{index}].version")
        for field in ("label", "kind", "parent_id", "description"):
            _string(place.get(field), f"{label}.places[{index}].{field}")
        _string_list(
            place.get("aliases"), f"{label}.places[{index}].aliases", allow_empty=True
        )
        if place.get("status") not in ("active", "unknown-boundary"):
            raise ConfigSchemaError(
                f"{label}.places[{index}].status 必须是 active/unknown-boundary"
            )

    events = document.get("story_events")
    if not isinstance(events, list) or not events:
        raise ConfigSchemaError(f"{label}.story_events 必须是非空数组")
    event_ids: set[str] = set()
    event_fields = {
        "id",
        "version",
        "label",
        "summary",
        "temporal_label",
        "aliases",
        "source_ref",
    }
    for index, raw in enumerate(events):
        event = _object(raw, f"{label}.story_events[{index}]")
        _keys(event, event_fields, f"{label}.story_events[{index}]")
        _require_keys(event, event_fields, f"{label}.story_events[{index}]")
        event_id = _string(event.get("id"), f"{label}.story_events[{index}].id")
        if event_id in event_ids:
            raise ConfigSchemaError(f"{label}.story_events 出现重复 ID: {event_id}")
        event_ids.add(event_id)
        _positive_int(event.get("version"), f"{label}.story_events[{index}].version")
        for field in ("label", "summary", "temporal_label", "source_ref"):
            _string(event.get(field), f"{label}.story_events[{index}].{field}")
        _string_list(
            event.get("aliases"),
            f"{label}.story_events[{index}].aliases",
            allow_empty=True,
        )

    knowledge = document.get("knowledge")
    if not isinstance(knowledge, list) or not knowledge:
        raise ConfigSchemaError(f"{label}.knowledge 必须是非空数组")
    knowledge_ids: set[str] = set()
    knowledge_fields = {
        "id",
        "version",
        "statement",
        "scope",
        "topic",
        "aliases",
        "retrieval_terms",
        "level",
        "certainty",
        "status",
        "source_ref",
        "related_ids",
        "eligibility",
        "importance",
        "statement_variants",
        "epistemic_kind",
        "prerequisite_ids",
        "acquisition_channels",
        "exposure_weight",
    }
    for index, raw in enumerate(knowledge):
        fact = _object(raw, f"{label}.knowledge[{index}]")
        _keys(fact, knowledge_fields, f"{label}.knowledge[{index}]")
        _require_keys(
            fact,
            knowledge_fields
            - {
                "importance",
                "statement_variants",
                "epistemic_kind",
                "prerequisite_ids",
                "acquisition_channels",
                "exposure_weight",
            },
            f"{label}.knowledge[{index}]",
        )
        fact_id = _string(fact.get("id"), f"{label}.knowledge[{index}].id")
        if fact_id in knowledge_ids:
            raise ConfigSchemaError(f"{label}.knowledge 出现重复 ID: {fact_id}")
        knowledge_ids.add(fact_id)
        _positive_int(fact.get("version"), f"{label}.knowledge[{index}].version")
        for field in ("statement", "scope", "topic", "source_ref"):
            _string(fact.get(field), f"{label}.knowledge[{index}].{field}")
        for field in ("aliases", "retrieval_terms", "related_ids", "eligibility"):
            _string_list(
                fact.get(field),
                f"{label}.knowledge[{index}].{field}",
                allow_empty=True,
            )
        if fact.get("level") not in ("common", "regional", "specialist", "unknown"):
            raise ConfigSchemaError(f"{label}.knowledge[{index}].level 无效")
        if fact.get("certainty") not in ("high", "medium", "low"):
            raise ConfigSchemaError(f"{label}.knowledge[{index}].certainty 无效")
        if fact.get("status") not in ("active", "unknown-boundary"):
            raise ConfigSchemaError(f"{label}.knowledge[{index}].status 无效")
        if "importance" in fact:
            importance = _number(
                fact["importance"], f"{label}.knowledge[{index}].importance"
            )
            if not 0.0 <= importance <= 1.0:
                raise ConfigSchemaError(
                    f"{label}.knowledge[{index}].importance 必须在 [0, 1] 内"
                )
        if "statement_variants" in fact:
            variants = _object(
                fact["statement_variants"],
                f"{label}.knowledge[{index}].statement_variants",
            )
            for key, value in variants.items():
                _string(
                    key,
                    f"{label}.knowledge[{index}].statement_variants key",
                )
                _string(
                    value,
                    f"{label}.knowledge[{index}].statement_variants.{key}",
                )
        if "epistemic_kind" in fact and fact["epistemic_kind"] not in (
            "lived_observation",
            "taught",
            "documented",
            "hearsay",
            "myth",
            "unknown_boundary",
        ):
            raise ConfigSchemaError(f"{label}.knowledge[{index}].epistemic_kind 无效")
        for field in ("prerequisite_ids", "acquisition_channels"):
            if field in fact:
                _string_list(
                    fact[field],
                    f"{label}.knowledge[{index}].{field}",
                    allow_empty=True,
                )
        if "exposure_weight" in fact:
            exposure_weight = _number(
                fact["exposure_weight"],
                f"{label}.knowledge[{index}].exposure_weight",
            )
            if not 0.0 <= exposure_weight <= 1.0:
                raise ConfigSchemaError(
                    f"{label}.knowledge[{index}].exposure_weight 必须在 [0, 1] 内"
                )

    _string_list(document.get("unknown_boundaries"), f"{label}.unknown_boundaries")
    if "genesis" in document:
        _validate_genesis_metadata(document["genesis"], label)


def _validate_genesis_metadata(value: Any, label: str) -> None:
    """Validate generator-only metadata without interpreting its semantics."""

    metadata = _object(value, f"{label}.genesis")
    _keys(
        metadata,
        {
            "package_id",
            "package_version",
            "schema_version",
            "status",
            "member_ids",
            "source_refs",
            "content_sha256",
            "names",
            "population",
            "policy",
            "arrival",
            "routes",
            "coverage_manifest",
            "life_archetypes",
            "relationship_archetypes",
            "episode_themes",
        },
        f"{label}.genesis",
    )
    for field in ("package_id", "package_version", "content_sha256"):
        if field in metadata:
            _string(metadata[field], f"{label}.genesis.{field}")
    if "schema_version" in metadata:
        _positive_int(metadata["schema_version"], f"{label}.genesis.schema_version")
    if "status" in metadata and metadata["status"] not in (
        "draft",
        "published",
        "retired",
    ):
        raise ConfigSchemaError(f"{label}.genesis.status 无效")
    for field in ("member_ids", "source_refs"):
        if field in metadata:
            _string_list(metadata[field], f"{label}.genesis.{field}", allow_empty=True)
    if "names" in metadata:
        names = _object(metadata["names"], f"{label}.genesis.names")
        _keys(names, {"default", "by_species"}, f"{label}.genesis.names")
        if "default" in names:
            _string_list(
                names["default"],
                f"{label}.genesis.names.default",
                allow_empty=True,
            )
        if "by_species" in names:
            by_species = _object(
                names["by_species"], f"{label}.genesis.names.by_species"
            )
            for species_id, values in by_species.items():
                _string(species_id, f"{label}.genesis.names.by_species key")
                _string_list(
                    values,
                    f"{label}.genesis.names.by_species.{species_id}",
                )
    if "population" in metadata:
        population = _object(metadata["population"], f"{label}.genesis.population")
        _keys(
            population,
            {"settlement_weights", "cells"},
            f"{label}.genesis.population",
        )
        if "settlement_weights" in population:
            weights = _object(
                population["settlement_weights"],
                f"{label}.genesis.population.settlement_weights",
            )
            for key, weight in weights.items():
                _string(
                    key,
                    f"{label}.genesis.population.settlement_weights key",
                )
                _positive_number(
                    weight,
                    f"{label}.genesis.population.settlement_weights.{key}",
                )
        if "cells" in population:
            cells = population["cells"]
            if not isinstance(cells, list):
                raise ConfigSchemaError(f"{label}.genesis.population.cells 必须是数组")
            cell_fields = {
                "id",
                "place_id",
                "species_ids",
                "weight",
                "private_home_kind",
            }
            for index, raw in enumerate(cells):
                cell = _object(raw, f"{label}.genesis.population.cells[{index}]")
                cell_label = f"{label}.genesis.population.cells[{index}]"
                _keys(cell, cell_fields, cell_label)
                _require_keys(
                    cell,
                    {"id", "place_id", "species_ids", "weight"},
                    cell_label,
                )
                _string(cell["id"], f"{cell_label}.id")
                _string(cell["place_id"], f"{cell_label}.place_id")
                _string_list(
                    cell["species_ids"],
                    f"{cell_label}.species_ids",
                )
                _positive_number(cell["weight"], f"{cell_label}.weight")
                if "private_home_kind" in cell:
                    _string(
                        cell["private_home_kind"],
                        f"{cell_label}.private_home_kind",
                    )
    if "policy" in metadata:
        policy = _object(metadata["policy"], f"{label}.genesis.policy")
        policy_label = f"{label}.genesis.policy"
        _keys(
            policy,
            {
                "version",
                "seed_algorithm",
                "relationship_count",
                "episode_count",
                "salient_relationship_count",
                "repeated_relationship_count",
            },
            policy_label,
        )
        for field in ("version", "seed_algorithm"):
            if field in policy:
                _string(policy[field], f"{policy_label}.{field}")
        for field in (
            "relationship_count",
            "episode_count",
            "salient_relationship_count",
            "repeated_relationship_count",
        ):
            if field in policy:
                _integer_pair(policy[field], f"{policy_label}.{field}")
    if "arrival" in metadata:
        arrival = _object(metadata["arrival"], f"{label}.genesis.arrival")
        for field in (
            "eligible_species_ids",
            "eligible_life_stages",
            "required_knowledge_ids",
            "required_module_ids",
        ):
            if field in arrival:
                _string_list(
                    arrival[field],
                    f"{label}.genesis.arrival.{field}",
                    allow_empty=True,
                )
        _keys(
            arrival,
            {
                "eligible_species_ids",
                "eligible_life_stages",
                "required_knowledge_ids",
                "required_module_ids",
            },
            f"{label}.genesis.arrival",
        )
    if "routes" in metadata:
        routes = metadata["routes"]
        if not isinstance(routes, list):
            raise ConfigSchemaError(f"{label}.genesis.routes 必须是数组")
        route_fields = {
            "id",
            "from_place_id",
            "to_place_id",
            "label",
            "aliases",
            "travel_time_band",
            "access_conditions",
        }
        for index, raw in enumerate(routes):
            route = _object(raw, f"{label}.genesis.routes[{index}]")
            route_label = f"{label}.genesis.routes[{index}]"
            _keys(route, route_fields, route_label)
            _require_keys(
                route,
                {"id", "from_place_id", "to_place_id", "label"},
                route_label,
            )
            for field in ("id", "from_place_id", "to_place_id", "label"):
                _string(route[field], f"{route_label}.{field}")
            for field in ("aliases", "access_conditions"):
                if field in route:
                    _string_list(
                        route[field],
                        f"{route_label}.{field}",
                        allow_empty=True,
                    )
            if "travel_time_band" in route:
                _string(
                    route["travel_time_band"],
                    f"{route_label}.travel_time_band",
                )
    if "coverage_manifest" in metadata:
        coverage = _object(
            metadata["coverage_manifest"],
            f"{label}.genesis.coverage_manifest",
        )
        coverage_label = f"{label}.genesis.coverage_manifest"
        _keys(
            coverage,
            {"creator_source_ref", "resident_source_ref", "links"},
            coverage_label,
        )
        _require_keys(
            coverage,
            {"creator_source_ref", "resident_source_ref", "links"},
            coverage_label,
        )
        _string(coverage["creator_source_ref"], f"{coverage_label}.creator_source_ref")
        _string(
            coverage["resident_source_ref"], f"{coverage_label}.resident_source_ref"
        )
        links = coverage["links"]
        if not isinstance(links, list) or not links:
            raise ConfigSchemaError(f"{coverage_label}.links 必须是非空数组")
        link_fields = {"upstream_id", "resident_fact_ids", "disposition", "rationale"}
        for index, raw in enumerate(links):
            link = _object(raw, f"{coverage_label}.links[{index}]")
            link_label = f"{coverage_label}.links[{index}]"
            _keys(link, link_fields, link_label)
            _require_keys(link, {"upstream_id", "resident_fact_ids"}, link_label)
            _string(link["upstream_id"], f"{link_label}.upstream_id")
            _string_list(
                link["resident_fact_ids"],
                f"{link_label}.resident_fact_ids",
                allow_empty=True,
            )
            if "disposition" in link:
                _string(link["disposition"], f"{link_label}.disposition")
                if link["disposition"] not in ("mapped", "deferred", "excluded"):
                    raise ConfigSchemaError(f"{link_label}.disposition 无效")
            if "rationale" in link:
                _string(link["rationale"], f"{link_label}.rationale")

    if "life_archetypes" in metadata:
        _validate_life_archetypes(
            metadata["life_archetypes"], f"{label}.genesis.life_archetypes"
        )
    if "relationship_archetypes" in metadata:
        _validate_relationship_archetypes(
            metadata["relationship_archetypes"],
            f"{label}.genesis.relationship_archetypes",
        )
    if "episode_themes" in metadata:
        _validate_episode_themes(
            metadata["episode_themes"], f"{label}.genesis.episode_themes"
        )


def _validate_life_archetypes(value: Any, label: str) -> None:
    if not isinstance(value, list) or not value:
        raise ConfigSchemaError(f"{label} 必须是非空数组")
    fields = {
        "id",
        "species_ids",
        "life_stages",
        "place_ids",
        "weight",
        "household_roles",
        "care_and_trade_context",
        "learning_path_id",
        "institution_ids",
        "apprenticeship_ids",
        "vocation_id",
        "proficiency_band",
        "workplace_place_id",
    }
    required = {
        "id",
        "species_ids",
        "life_stages",
        "weight",
        "household_roles",
        "care_and_trade_context",
        "learning_path_id",
        "vocation_id",
        "proficiency_band",
    }
    for index, raw in enumerate(value):
        item = _object(raw, f"{label}[{index}]")
        item_label = f"{label}[{index}]"
        _keys(item, fields, item_label)
        _require_keys(item, required, item_label)
        for field in (
            "id",
            "care_and_trade_context",
            "learning_path_id",
            "vocation_id",
            "proficiency_band",
        ):
            _string(item[field], f"{item_label}.{field}")
        for field in (
            "species_ids",
            "life_stages",
            "household_roles",
            "institution_ids",
            "apprenticeship_ids",
            "place_ids",
        ):
            if field in item:
                _string_list(item[field], f"{item_label}.{field}", allow_empty=True)
        _positive_number(item["weight"], f"{item_label}.weight")
        if "workplace_place_id" in item:
            _string(item["workplace_place_id"], f"{item_label}.workplace_place_id")


def _validate_relationship_archetypes(value: Any, label: str) -> None:
    if not isinstance(value, list) or not value:
        raise ConfigSchemaError(f"{label} 必须是非空数组")
    fields = {
        "id",
        "role",
        "person_species_ids",
        "life_stages",
        "weight",
        "initial_trust",
        "importance",
        "familiarity",
        "vocation_id",
        "competency_ids",
        "episode_theme_ids",
    }
    required = {"id", "role", "person_species_ids", "weight"}
    for index, raw in enumerate(value):
        item = _object(raw, f"{label}[{index}]")
        item_label = f"{label}[{index}]"
        _keys(item, fields, item_label)
        _require_keys(item, required, item_label)
        for field in ("id", "role"):
            _string(item[field], f"{item_label}.{field}")
        for field in (
            "person_species_ids",
            "life_stages",
            "competency_ids",
            "episode_theme_ids",
        ):
            if field in item:
                _string_list(item[field], f"{item_label}.{field}", allow_empty=True)
        _positive_number(item["weight"], f"{item_label}.weight")
        for field in ("initial_trust", "importance"):
            if field in item:
                number = _number(item[field], f"{item_label}.{field}")
                if not 0.0 <= number <= 1.0:
                    raise ConfigSchemaError(f"{item_label}.{field} 必须在 [0, 1] 内")
        if "familiarity" in item:
            _string(item["familiarity"], f"{item_label}.familiarity")
        if "vocation_id" in item:
            _string(item["vocation_id"], f"{item_label}.vocation_id")


def _validate_episode_themes(value: Any, label: str) -> None:
    if not isinstance(value, list) or not value:
        raise ConfigSchemaError(f"{label} 必须是非空数组")
    fields = {
        "id",
        "label",
        "weight",
        "life_stages",
        "min_age_years",
        "required_roles",
        "place_kinds",
        "emotional_tone",
        "goal",
        "obstacle",
        "outcome",
        "impact",
        "required_knowledge_ids",
        "required",
        "order",
    }
    required = {
        "id",
        "label",
        "weight",
        "life_stages",
        "emotional_tone",
        "goal",
        "obstacle",
        "outcome",
        "impact",
    }
    for index, raw in enumerate(value):
        item = _object(raw, f"{label}[{index}]")
        item_label = f"{label}[{index}]"
        _keys(item, fields, item_label)
        _require_keys(item, required, item_label)
        for field in (
            "id",
            "label",
            "emotional_tone",
            "goal",
            "obstacle",
            "outcome",
            "impact",
        ):
            _string(item[field], f"{item_label}.{field}")
        for field in (
            "life_stages",
            "required_roles",
            "place_kinds",
            "required_knowledge_ids",
        ):
            if field in item:
                _string_list(item[field], f"{item_label}.{field}", allow_empty=True)
        _positive_number(item["weight"], f"{item_label}.weight")
        if "min_age_years" in item:
            _positive_int(item["min_age_years"], f"{item_label}.min_age_years")
        if "required" in item:
            _boolean(item["required"], f"{item_label}.required")
        if "order" in item:
            _positive_int(item["order"], f"{item_label}.order")


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
            "food_generation_preferences",
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
    preferences = document.get("food_generation_preferences", [])
    if not isinstance(preferences, list):
        raise ConfigSchemaError(f"{label}.food_generation_preferences 必须是数组")


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
        "pricing",
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


def _integer_pair(value: Any, label: str) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 0
            for item in value
        )
        or value[1] < value[0]
    ):
        raise ConfigSchemaError(f"{label} 必须是递增的两个非负整数")
    return int(value[0]), int(value[1])


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
