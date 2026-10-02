from __future__ import annotations

import pytest
import yaml

from infrastructure.persistence.configuration.documents import (
    resolve_bundled_config_root,
)
from infrastructure.persistence.configuration.family import (
    load_family_generation_config,
)


def _document() -> dict[str, object]:
    path = resolve_bundled_config_root() / "genesis" / "family.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_published_family_policy_is_one_typed_configuration() -> None:
    config = load_family_generation_config(_document())

    assert config.generation_version == "family-generation.v1"
    assert config.marriage.peak_fraction == 0.25
    assert config.marriage.never_married_probability == 0.1
    assert config.partner_age_gap.offsets == (-2, -1, 0, 1, 2)
    assert config.children.count_distribution == (
        (0, 0.03),
        (1, 0.05),
        (2, 0.5),
        (3, 0.42),
    )
    assert config.children.birth_lag_decay == 0.75
    assert config.lifespan.early_cdf_power == 4
    assert config.lifespan.late_survival_power == 2
    assert config.ancestor_expansion.max_upward_generations == 1


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("marriage", "peak_fraction"), 1.2),
        (("lifespan", "early_cdf_power"), 0),
        (("lifespan", "late_survival_power"), True),
        (("marriage", "sampler_version"), "other.v1"),
        (("children", "birth_lag_decay"), 1.0),
        (("children", "sex_distribution"), {"unknown": 1.0}),
        (("ancestor_expansion", "max_upward_generations"), 2),
    ],
)
def test_family_policy_rejects_values_outside_the_algorithm_contract(
    path: tuple[str, str], value: object
) -> None:
    document = _document()
    section, key = path
    section_value = document[section]
    assert isinstance(section_value, dict)
    section_value[key] = value

    with pytest.raises(ValueError, match="family|家庭"):
        load_family_generation_config(document)
