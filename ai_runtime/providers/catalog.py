"""Versioned Provider metadata catalog.

The bundled catalog is the offline baseline. A validated full catalog at
``ELFIE_HOME/configs/provider-catalog.yaml`` may replace it after restart,
which leaves a narrow persistence seam for a future remote updater.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping

from ai_runtime.storage.config_store import ConfigStoreError, read_yaml_mapping
from ai_runtime.storage.data_home import get_provider_catalog_path

logger = logging.getLogger("ai_runtime.providers.catalog")

PROVIDER_CATALOG_VERSION = 2
BUNDLED_PROVIDER_CATALOG_PATH = Path(__file__).with_name("provider-catalog.yaml")
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
_MODEL_ROLES = ("cheap", "deep", "multimodal")
_AUTH_TYPES = frozenset({"bearer", "none", "x-api-key"})
_API_MODES = frozenset({"anthropic_messages", "chat_completions", "ollama"})
_CONNECTION_METHODS = frozenset({"api_key", "local", "oauth"})
_USAGE_SCOPES = frozenset({"coding_only", "general", "local"})
_DISCOVERY_STRATEGIES = frozenset(
    {"catalog_only", "ollama", "provider_adapter", "standard_models"}
)


class ProviderCatalogError(ConfigStoreError):
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
    default_models: Dict[str, List[str]]
    connection_method: Literal["local", "api_key", "oauth"]
    oauth_available: bool = False
    test_model: str = ""
    model_descriptions: Dict[str, str] = field(default_factory=dict)
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
class ProviderCatalog:
    version: int
    brands: Dict[str, ProviderBrand]
    products: Dict[str, ProviderProfile]
    endpoint_model_hints: tuple[EndpointModelHint, ...]
    source: Path

    @property
    def profiles(self) -> Dict[str, ProviderProfile]:
        """Return the legacy Provider-keyed view during the staged migration."""
        return {
            profile.legacy_provider_id: profile
            for profile in self.products.values()
        }

    def suggested_models(self, api_base: str) -> list[str]:
        normalized = api_base.lower().rstrip("/")
        for hint in self.endpoint_model_hints:
            if hint.api_base_contains in normalized:
                return list(hint.models)
        return []


def load_provider_catalog(
    override_path: Path | None = None,
) -> ProviderCatalog:
    """Load a validated local full-catalog override or the bundled baseline."""
    candidate = override_path or get_provider_catalog_path()
    if candidate.exists():
        try:
            return _load_catalog_file(candidate)
        except ProviderCatalogError as exc:
            logger.warning(
                "Ignoring invalid Provider catalog override %s: %s",
                candidate,
                exc,
            )
    return _load_catalog_file(BUNDLED_PROVIDER_CATALOG_PATH)


def _load_catalog_file(path: Path) -> ProviderCatalog:
    if not path.is_file():
        raise ProviderCatalogError(f"Provider catalog does not exist: {path}")
    try:
        document = read_yaml_mapping(path)
    except ConfigStoreError as exc:
        raise ProviderCatalogError(str(exc)) from exc
    return _parse_catalog(document, path)


def _parse_catalog(document: Mapping[str, Any], source: Path) -> ProviderCatalog:
    if _contains_secret_field(document):
        raise ProviderCatalogError(
            f"Provider catalog must not contain plaintext credentials: {source}"
        )
    version = document.get("version")
    if version != PROVIDER_CATALOG_VERSION:
        raise ProviderCatalogError(
            f"Unsupported Provider catalog version {version!r}: {source}"
        )
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
        brands[brand_id] = ProviderBrand(
            name=_required_string(raw_brand, "name", brand_id, source),
            logo_asset=str(raw_brand.get("logo_asset") or "").strip(),
        )

    raw_products = document.get("products")
    if not isinstance(raw_products, Mapping) or not raw_products:
        raise ProviderCatalogError(f"Provider catalog has no products: {source}")

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
        profile = _parse_profile(
            catalog_id,
            raw_profile,
            brands,
            source,
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
    return ProviderCatalog(
        version=PROVIDER_CATALOG_VERSION,
        brands=brands,
        products=products,
        endpoint_model_hints=hints,
        source=source,
    )


def _parse_profile(
    catalog_id: str,
    raw: Mapping[str, Any],
    brands: Mapping[str, ProviderBrand],
    source: Path,
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

    raw_models = raw.get("default_models")
    if not isinstance(raw_models, Mapping):
        raise ProviderCatalogError(
            f"Provider {catalog_id!r} default_models must be an object: {source}"
        )
    default_models: Dict[str, List[str]] = {}
    for role in _MODEL_ROLES:
        values = raw_models.get(role)
        if not isinstance(values, list) or not values:
            raise ProviderCatalogError(
                f"Provider {catalog_id!r} requires non-empty {role} models: {source}"
            )
        models = [str(item).strip() for item in values]
        if any(not item for item in models):
            raise ProviderCatalogError(
                f"Provider {catalog_id!r} has an empty {role} model: {source}"
            )
        default_models[role] = list(dict.fromkeys(models))

    test_model = str(raw.get("test_model") or default_models["cheap"][0]).strip()
    raw_descriptions = raw.get("model_descriptions", {})
    if not isinstance(raw_descriptions, Mapping):
        raise ProviderCatalogError(
            f"Provider {catalog_id!r} model_descriptions must be an object: {source}"
        )
    descriptions = {
        str(role): str(description)
        for role, description in raw_descriptions.items()
        if str(role) in _MODEL_ROLES and str(description).strip()
    }
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
        default_models=default_models,
        connection_method=connection_method,  # type: ignore[arg-type]
        oauth_available=oauth_available,
        test_model=test_model,
        model_descriptions=descriptions,
        usage_scope=usage_scope,  # type: ignore[arg-type]
        discovery_strategy=discovery_strategy,  # type: ignore[arg-type]
    )


def _parse_hint(raw: Any, source: Path) -> EndpointModelHint:
    if not isinstance(raw, Mapping):
        raise ProviderCatalogError(f"Endpoint model hint must be an object: {source}")
    contains = str(raw.get("api_base_contains") or "").strip().lower()
    models = raw.get("models")
    if not contains or not isinstance(models, list):
        raise ProviderCatalogError(f"Invalid endpoint model hint: {source}")
    normalized_models = tuple(
        dict.fromkeys(str(model).strip() for model in models if str(model).strip())
    )
    if not normalized_models:
        raise ProviderCatalogError(f"Endpoint model hint has no models: {source}")
    return EndpointModelHint(contains, normalized_models)


def _required_string(
    raw: Mapping[str, Any],
    field_name: str,
    provider_id: str,
    source: Path,
) -> str:
    value = str(raw.get(field_name) or "").strip()
    if not value:
        raise ProviderCatalogError(
            f"Provider {provider_id!r} requires {field_name}: {source}"
        )
    return value


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
    normalized = str(value or "").strip()
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
