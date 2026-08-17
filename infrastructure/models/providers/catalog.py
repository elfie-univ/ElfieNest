"""Versioned Provider metadata catalog.

The bundled catalog is the offline baseline. A validated full catalog at
``ELFIE_HOME/configs/provider-catalog.yaml`` may replace it after restart,
which leaves a narrow persistence seam for a future remote updater.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Mapping

PROVIDER_CATALOG_VERSION = 2
_PROVIDER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SECRET_FIELDS = frozenset(
    {
        "access_token",
        "api_key",
        "client_secret",
        "password",
        "refresh_token",
        "secret",
        "token",
    }
)
_AUTH_TYPES = frozenset({"bearer", "none", "x-api-key"})
_API_MODES = frozenset(
    {"anthropic_messages", "chat_completions", "codex_responses", "ollama"}
)
_CONNECTION_METHODS = frozenset({"api_key", "local", "oauth"})
_USAGE_SCOPES = frozenset({"coding_only", "general", "local"})
_DISCOVERY_STRATEGIES = frozenset(
    {"catalog_only", "ollama", "provider_adapter", "standard_models"}
)
_CATALOG_FIELDS = frozenset(
    {
        "version",
        "ollama_recommended_models",
        "brands",
        "products",
        "endpoint_model_hints",
        "food_generation_preferences",
    }
)
_BRAND_FIELDS = frozenset({"name", "logo_asset"})
_PRODUCT_FIELDS = frozenset(
    {
        "brand_id",
        "legacy_provider_id",
        "name",
        "api_base",
        "auth_type",
        "api_mode",
        "base_url_env_var",
        "api_key_env_var",
        "connection_method",
        "oauth_available",
        "test_model",
        "usage_scope",
        "discovery_strategy",
        "bundled_models",
    }
)
_RECOMMENDATION_FIELDS = frozenset({"id", "recommended"})
_HINT_FIELDS = frozenset({"api_base_contains", "models"})
_FOOD_PREFERENCE_FIELDS = frozenset(
    {"catalog_id", "model_id", "priority", "quality_tier"}
)


class ProviderCatalogError(RuntimeError):
    """Provider catalog is missing or violates its versioned schema."""


@dataclass
class ProviderProfile:
    """Declarative defaults for one connectable Provider product."""

    catalog_id: str
    brand_id: str
    legacy_provider_id: str
    name: str
    api_base: str
    auth_type: str
    api_mode: str
    base_url_env_var: str
    api_key_env_var: str
    bundled_models: list[str]
    connection_method: Literal["local", "api_key", "oauth"]
    oauth_available: bool = False
    test_model: str = ""
    usage_scope: Literal["general", "coding_only", "local"] = "general"
    discovery_strategy: Literal[
        "standard_models",
        "provider_adapter",
        "catalog_only",
        "ollama",
    ] = "standard_models"


@dataclass(frozen=True)
class ProviderBrand:
    name: str
    logo_asset: str = ""


@dataclass(frozen=True)
class EndpointModelHint:
    api_base_contains: str
    models: tuple[str, ...]


@dataclass(frozen=True)
class FoodGenerationPreference:
    catalog_id: str
    model_id: str
    priority: int
    quality_tier: int


@dataclass(frozen=True)
class OllamaModelRecommendation:
    """One local Ollama model and whether Setup should emphasize it."""

    model_id: str
    recommended: bool


@dataclass(frozen=True)
class ProviderCatalog:
    version: int
    brands: Dict[str, ProviderBrand]
    products: Dict[str, ProviderProfile]
    endpoint_model_hints: tuple[EndpointModelHint, ...]
    ollama_recommended_models: tuple[OllamaModelRecommendation, ...]
    source: Path
    food_generation_preferences: tuple[FoodGenerationPreference, ...] = ()

    @property
    def profiles(self) -> Dict[str, ProviderProfile]:
        """Return the legacy Provider-keyed view during the staged migration."""
        return {
            profile.legacy_provider_id: profile for profile in self.products.values()
        }

    def suggested_models(self, api_base: str) -> list[str]:
        normalized = api_base.lower().rstrip("/")
        for hint in self.endpoint_model_hints:
            if hint.api_base_contains in normalized:
                return list(hint.models)
        return []

    def food_generation_preference(
        self,
        catalog_id: str,
        model_id: str,
    ) -> FoodGenerationPreference | None:
        return next(
            (
                item
                for item in self.food_generation_preferences
                if item.catalog_id == catalog_id and item.model_id == model_id
            ),
            None,
        )


def parse_provider_catalog(
    document: Mapping[str, Any], source: Path
) -> ProviderCatalog:
    """Parse one already-loaded catalog document.

    File selection and YAML I/O belong to the persistence adapter; this module
    only owns the provider semantic schema and validation rules.
    """
    if _contains_secret_field(document):
        raise ProviderCatalogError(
            f"Provider catalog must not contain plaintext credentials: {source}"
        )
    version = document.get("version")
    if version != PROVIDER_CATALOG_VERSION:
        raise ProviderCatalogError(
            f"Unsupported Provider catalog version {version!r}: {source}"
        )
    _reject_unknown(document, _CATALOG_FIELDS, "Provider catalog", source)
    raw_brands = document.get("brands")
    if not isinstance(raw_brands, Mapping) or not raw_brands:
        raise ProviderCatalogError(f"Provider catalog has no brands: {source}")
    brands: Dict[str, ProviderBrand] = {}
    for brand_id, raw_brand in raw_brands.items():
        if not isinstance(brand_id, str) or not _PROVIDER_ID_PATTERN.fullmatch(
            brand_id
        ):
            raise ProviderCatalogError(f"Invalid brand ID {brand_id!r}: {source}")
        if not isinstance(raw_brand, Mapping):
            raise ProviderCatalogError(
                f"Brand {brand_id!r} must be an object: {source}"
            )
        _reject_unknown(raw_brand, _BRAND_FIELDS, f"Brand {brand_id!r}", source)
        brands[brand_id] = ProviderBrand(
            name=_required_string(raw_brand, "name", brand_id, source),
            logo_asset=_optional_string(
                raw_brand.get("logo_asset"), "logo_asset", brand_id, source
            ),
        )

    raw_products = document.get("products")
    if not isinstance(raw_products, Mapping) or not raw_products:
        raise ProviderCatalogError(f"Provider catalog has no products: {source}")
    ollama_recommended_models = _parse_ollama_recommendations(
        document.get("ollama_recommended_models", ()),
        source,
    )
    ollama_model_ids = [item.model_id for item in ollama_recommended_models]

    products: Dict[str, ProviderProfile] = {}
    legacy_ids: set[str] = set()
    for catalog_id, raw_profile in raw_products.items():
        if not isinstance(catalog_id, str) or not _PROVIDER_ID_PATTERN.fullmatch(
            catalog_id
        ):
            raise ProviderCatalogError(f"Invalid catalog ID {catalog_id!r}: {source}")
        if not isinstance(raw_profile, Mapping):
            raise ProviderCatalogError(
                f"Provider product {catalog_id!r} must be an object: {source}"
            )
        _reject_unknown(
            raw_profile,
            _PRODUCT_FIELDS,
            f"Provider product {catalog_id!r}",
            source,
        )
        profile = _parse_profile(
            catalog_id,
            raw_profile,
            brands,
            source,
            fallback_models=ollama_model_ids if catalog_id == "ollama" else None,
        )
        if profile.legacy_provider_id in legacy_ids:
            raise ProviderCatalogError(
                f"Duplicate legacy_provider_id {profile.legacy_provider_id!r}: {source}"
            )
        legacy_ids.add(profile.legacy_provider_id)
        products[catalog_id] = profile

    required_products = {"ollama", "custom_openai"}
    missing = required_products - products.keys()
    if missing:
        raise ProviderCatalogError(
            f"Provider catalog is missing required products {sorted(missing)}: {source}"
        )

    raw_hints = document.get("endpoint_model_hints", ())
    if not isinstance(raw_hints, list):
        raise ProviderCatalogError(f"endpoint_model_hints must be a list: {source}")
    hints = tuple(_parse_hint(item, source) for item in raw_hints)
    preferences = _parse_food_generation_preferences(
        document.get("food_generation_preferences", ()),
        products,
        source,
    )
    return ProviderCatalog(
        version=PROVIDER_CATALOG_VERSION,
        brands=brands,
        products=products,
        endpoint_model_hints=hints,
        ollama_recommended_models=ollama_recommended_models,
        source=source,
        food_generation_preferences=preferences,
    )


def _parse_profile(
    catalog_id: str,
    raw: Mapping[str, Any],
    brands: Mapping[str, ProviderBrand],
    source: Path,
    *,
    fallback_models: list[str] | None = None,
) -> ProviderProfile:
    brand_id = _required_string(raw, "brand_id", catalog_id, source)
    if brand_id not in brands:
        raise ProviderCatalogError(
            f"Provider {catalog_id!r} references unknown brand {brand_id!r}: {source}"
        )
    legacy_provider_id = _required_string(
        raw,
        "legacy_provider_id",
        catalog_id,
        source,
    )
    if not _PROVIDER_ID_PATTERN.fullmatch(legacy_provider_id):
        raise ProviderCatalogError(
            f"Provider {catalog_id!r} has invalid legacy_provider_id: {source}"
        )
    name = _required_string(raw, "name", catalog_id, source)
    api_base = _required_string(raw, "api_base", catalog_id, source)
    auth_type = _choice(
        raw,
        "auth_type",
        _AUTH_TYPES,
        catalog_id,
        source,
    )
    api_mode = _choice(
        raw,
        "api_mode",
        _API_MODES,
        catalog_id,
        source,
    )
    connection_method = _choice(
        raw,
        "connection_method",
        _CONNECTION_METHODS,
        catalog_id,
        source,
    )
    usage_scope = _choice(
        raw,
        "usage_scope",
        _USAGE_SCOPES,
        catalog_id,
        source,
    )
    discovery_strategy = _choice(
        raw,
        "discovery_strategy",
        _DISCOVERY_STRATEGIES,
        catalog_id,
        source,
    )
    base_url_env_var = _env_name(
        raw.get("base_url_env_var", ""),
        "base_url_env_var",
        catalog_id,
        source,
    )
    api_key_env_var = _env_name(
        raw.get("api_key_env_var", ""),
        "api_key_env_var",
        catalog_id,
        source,
    )
    oauth_available = raw.get("oauth_available", False)
    if not isinstance(oauth_available, bool):
        raise ProviderCatalogError(
            f"Provider {catalog_id!r} oauth_available must be boolean: {source}"
        )
    if connection_method == "local" and auth_type != "none":
        raise ProviderCatalogError(
            f"Local Provider {catalog_id!r} must use auth_type 'none': {source}"
        )
    if connection_method == "api_key" and not api_key_env_var:
        raise ProviderCatalogError(
            f"API-key Provider {catalog_id!r} requires api_key_env_var: {source}"
        )

    raw_models = raw.get("bundled_models")
    if raw_models is None and fallback_models:
        raw_models = fallback_models
    if not isinstance(raw_models, list):
        raise ProviderCatalogError(
            f"Provider {catalog_id!r} bundled_models must be a list: {source}"
        )
    if any(not isinstance(item, str) or not item.strip() for item in raw_models):
        raise ProviderCatalogError(
            f"Provider {catalog_id!r} bundled_models contains an invalid model: {source}"
        )
    bundled_models = list(dict.fromkeys(item.strip() for item in raw_models))
    if not bundled_models or any(not item for item in bundled_models):
        raise ProviderCatalogError(
            f"Provider {catalog_id!r} has no usable bundled models: {source}"
        )
    raw_test_model = raw.get("test_model")
    if raw_test_model is not None and (
        not isinstance(raw_test_model, str) or not raw_test_model.strip()
    ):
        raise ProviderCatalogError(
            f"Provider {catalog_id!r} has invalid test_model: {source}"
        )
    test_model = (raw_test_model or bundled_models[0]).strip()
    return ProviderProfile(
        catalog_id=catalog_id,
        brand_id=brand_id,
        legacy_provider_id=legacy_provider_id,
        name=name,
        api_base=api_base,
        auth_type=auth_type,
        api_mode=api_mode,
        base_url_env_var=base_url_env_var,
        api_key_env_var=api_key_env_var,
        bundled_models=bundled_models,
        connection_method=connection_method,  # type: ignore[arg-type]
        oauth_available=oauth_available,
        test_model=test_model,
        usage_scope=usage_scope,  # type: ignore[arg-type]
        discovery_strategy=discovery_strategy,  # type: ignore[arg-type]
    )


def _parse_ollama_recommendations(
    raw: Any,
    source: Path,
) -> tuple[OllamaModelRecommendation, ...]:
    if raw in (None, ()):
        return ()
    if not isinstance(raw, list):
        raise ProviderCatalogError(
            f"ollama_recommended_models must be a list: {source}"
        )
    recommendations: list[OllamaModelRecommendation] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            raise ProviderCatalogError(
                f"Ollama recommendation must be an object: {source}"
            )
        _reject_unknown(item, _RECOMMENDATION_FIELDS, "Ollama recommendation", source)
        model_id = _required_text(item.get("id"), "id", "ollama", source)
        recommended = item.get("recommended")
        if not model_id or model_id in seen or not isinstance(recommended, bool):
            raise ProviderCatalogError(f"Invalid Ollama recommendation: {source}")
        seen.add(model_id)
        recommendations.append(
            OllamaModelRecommendation(model_id=model_id, recommended=recommended)
        )
    if recommendations and sum(item.recommended for item in recommendations) != 1:
        raise ProviderCatalogError(
            f"Ollama recommendations must have exactly one recommended model: {source}"
        )
    return tuple(recommendations)


def _parse_hint(raw: Any, source: Path) -> EndpointModelHint:
    if not isinstance(raw, Mapping):
        raise ProviderCatalogError(f"Endpoint model hint must be an object: {source}")
    _reject_unknown(raw, _HINT_FIELDS, "Endpoint model hint", source)
    contains = _required_text(
        raw.get("api_base_contains"), "api_base_contains", "hint", source
    ).lower()
    models = raw.get("models")
    if not contains or not isinstance(models, list):
        raise ProviderCatalogError(f"Invalid endpoint model hint: {source}")
    if any(not isinstance(model, str) or not model.strip() for model in models):
        raise ProviderCatalogError(
            f"Endpoint model hint contains invalid model: {source}"
        )
    normalized_models = tuple(dict.fromkeys(model.strip() for model in models))
    if not normalized_models:
        raise ProviderCatalogError(f"Endpoint model hint has no models: {source}")
    return EndpointModelHint(contains, normalized_models)


def _parse_food_generation_preferences(
    raw: Any,
    products: Mapping[str, ProviderProfile],
    source: Path,
) -> tuple[FoodGenerationPreference, ...]:
    if raw in (None, ()):
        return ()
    if not isinstance(raw, list):
        raise ProviderCatalogError(
            f"food_generation_preferences must be a list: {source}"
        )
    preferences: list[FoodGenerationPreference] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            raise ProviderCatalogError(
                f"Food generation preference must be an object: {source}"
            )
        _reject_unknown(
            item,
            _FOOD_PREFERENCE_FIELDS,
            "Food generation preference",
            source,
        )
        catalog_id = _required_text(
            item.get("catalog_id"), "catalog_id", "food", source
        )
        model_id = _required_text(item.get("model_id"), "model_id", catalog_id, source)
        priority = item.get("priority")
        quality_tier = item.get("quality_tier")
        if (
            catalog_id not in products
            or model_id not in products[catalog_id].bundled_models
            or not isinstance(priority, int)
            or isinstance(priority, bool)
            or priority < 0
            or priority > 1000
            or not isinstance(quality_tier, int)
            or isinstance(quality_tier, bool)
            or quality_tier < 0
            or quality_tier > 3
        ):
            raise ProviderCatalogError(
                f"Invalid Food generation preference: {catalog_id}/{model_id}: {source}"
            )
        key = (catalog_id, model_id)
        if key in seen:
            raise ProviderCatalogError(
                f"Duplicate Food generation preference: {catalog_id}/{model_id}: {source}"
            )
        seen.add(key)
        preferences.append(
            FoodGenerationPreference(
                catalog_id=catalog_id,
                model_id=model_id,
                priority=priority,
                quality_tier=quality_tier,
            )
        )
    return tuple(preferences)


def _required_string(
    raw: Mapping[str, Any],
    field_name: str,
    provider_id: str,
    source: Path,
) -> str:
    return _required_text(raw.get(field_name), field_name, provider_id, source)


def _required_text(value: Any, field_name: str, provider_id: str, source: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderCatalogError(
            f"Provider {provider_id!r} requires {field_name}: {source}"
        )
    return value.strip()


def _optional_string(
    value: Any,
    field_name: str,
    provider_id: str,
    source: Path,
) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ProviderCatalogError(
            f"Provider {provider_id!r} has invalid {field_name}: {source}"
        )
    return value.strip()


def _reject_unknown(
    raw: Mapping[str, Any],
    allowed: frozenset[str],
    label: str,
    source: Path,
) -> None:
    unknown = sorted(str(key) for key in set(raw) - allowed)
    if unknown:
        raise ProviderCatalogError(
            f"{label} contains unknown fields {unknown}: {source}"
        )


def _choice(
    raw: Mapping[str, Any],
    field_name: str,
    choices: frozenset[str],
    provider_id: str,
    source: Path,
) -> str:
    value = _required_string(raw, field_name, provider_id, source)
    if value not in choices:
        raise ProviderCatalogError(
            f"Provider {provider_id!r} has unsupported {field_name} {value!r}: {source}"
        )
    return value


def _env_name(
    value: Any,
    field_name: str,
    provider_id: str,
    source: Path,
) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ProviderCatalogError(
            f"Provider {provider_id!r} has invalid {field_name}: {source}"
        )
    normalized = value.strip()
    if normalized and not _ENV_NAME_PATTERN.fullmatch(normalized):
        raise ProviderCatalogError(
            f"Provider {provider_id!r} has invalid {field_name}: {source}"
        )
    return normalized


def _contains_secret_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() in _SECRET_FIELDS or _contains_secret_field(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_secret_field(item) for item in value)
    return False
