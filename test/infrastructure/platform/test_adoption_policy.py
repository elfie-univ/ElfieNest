from app.features.adoption import AdoptionPolicyRecord
from app.features.configuration.settings import (
    StoredElfieSettings,
    StoredRuntimeSettings,
    StoredSecuritySettings,
)
from infrastructure.platform import SettingsAdoptionPolicyAdapter


class Settings:
    def load_elfie_settings(self) -> StoredElfieSettings:
        return StoredElfieSettings(
            max_elfies_per_user=4,
            personality_presets_enabled=(("好奇探索", True), ("活泼好动", False)),
        )

    def save_elfie_settings(self, settings: StoredElfieSettings) -> None:
        raise AssertionError("read-only policy adapter")

    def load_runtime_settings(self) -> StoredRuntimeSettings:
        raise AssertionError("unrelated settings section")

    def save_runtime_settings(self, settings: StoredRuntimeSettings) -> None:
        raise AssertionError("unrelated settings section")

    def load_security_settings(self) -> StoredSecuritySettings:
        raise AssertionError("unrelated settings section")

    def save_security_settings(self, settings: StoredSecuritySettings) -> None:
        raise AssertionError("unrelated settings section")


def test_policy_adapter_reads_the_settings_authority_without_writing() -> None:
    policy: AdoptionPolicyRecord = SettingsAdoptionPolicyAdapter(
        Settings()
    ).load_policy()

    assert policy.default_elfie_limit == 4
    assert "好奇探索" in policy.enabled_personality_styles
    assert "活泼好动" not in policy.enabled_personality_styles
