from runtime.models.groups import DEFAULT_MODEL_GROUPS, ModelGroup, resolve_model_key


def test_default_model_groups_include_expected_food_groups():
    assert tuple(DEFAULT_MODEL_GROUPS) == (
        "coarse",
        "standard",
        "premium",
        "vision",
        "code",
        "organize",
    )


def test_model_group_preserves_model_priority_order():
    group = ModelGroup(
        key="code",
        display_name="代码粮",
        model_keys=("remote_deep", "local_fast"),
    )

    assert group.model_keys == ("remote_deep", "local_fast")


def test_resolve_model_key_returns_first_available_model_in_group():
    available_model_keys = {"local_fast"}

    model_key = resolve_model_key(
        DEFAULT_MODEL_GROUPS["premium"],
        available_model_keys,
    )

    assert model_key == "local_fast"
