from __future__ import annotations

from collections.abc import Iterable

import pytest

import infrastructure.models.adoption_narrative as adoption_narrative
from elfie.genesis import GenesisAppearanceIntent, GenesisEngine
from infrastructure.models.adoption_narrative import StructuredAdoptionNarrativeAdapter
from infrastructure.models.fallback_model_execution import FallbackModelExecutionAdapter
from infrastructure.models.model_execution_contracts import (
    StructuredModelExecutionCapabilities,
    StructuredModelExecutionRequest,
    StructuredModelExecutionResult,
)


class FakeExecution:
    def __init__(
        self,
        capabilities: StructuredModelExecutionCapabilities,
        outputs: Iterable[str] = (),
    ) -> None:
        self.capabilities = capabilities
        self.outputs = iter(outputs)
        self.requests: list[StructuredModelExecutionRequest] = []

    def adoption_capabilities(self) -> StructuredModelExecutionCapabilities:
        return self.capabilities

    def generate_adoption_structured(
        self,
        request: StructuredModelExecutionRequest,
    ) -> StructuredModelExecutionResult:
        self.requests.append(request)
        return request.to_result(text=next(self.outputs))


class FailingExecution(FakeExecution):
    def generate_adoption_structured(
        self,
        request: StructuredModelExecutionRequest,
    ) -> StructuredModelExecutionResult:
        self.requests.append(request)
        raise RuntimeError("provider unavailable")


class FlakyExecution(FakeExecution):
    def __init__(self, capabilities, outputs, failures: int) -> None:
        super().__init__(capabilities, outputs)
        self.failures_remaining = failures

    def generate_adoption_structured(
        self,
        request: StructuredModelExecutionRequest,
    ) -> StructuredModelExecutionResult:
        self.requests.append(request)
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise RuntimeError("provider temporarily unavailable")
        return request.to_result(text=next(self.outputs))


def _capabilities(model_key: str) -> StructuredModelExecutionCapabilities:
    return StructuredModelExecutionCapabilities(
        provider="ollama" if model_key.startswith("ollama/") else "openai",
        model_key=model_key,
        supports_json_schema=True,
        supports_tool_calling=False,
        supports_json_mode=True,
        supports_plain_text=True,
        max_output_tokens=1024,
    )


def _candidate():
    return (
        GenesisEngine()
        .generate_batch(
            master_seed=7,
            batch_number=1,
            species_id="fox",
            life_stage="young_adult",
            gender="female",
            appearance=GenesisAppearanceIntent(
                stature="any",
                build="any",
                face="balanced",
                signature="any",
                priority="face",
            ),
            answers=("quiet", "research", "plan", "discuss", "steady"),
        )
        .candidates[0]
    )


def test_small_local_model_is_not_qualified_for_identity_reveal() -> None:
    adapter = StructuredAdoptionNarrativeAdapter(
        FakeExecution(_capabilities("ollama/qwen2.5:0.5b"))
    )

    assert adapter.is_ready() is False


def test_execution_without_adoption_capabilities_is_not_ready() -> None:
    adapter = StructuredAdoptionNarrativeAdapter(FallbackModelExecutionAdapter())

    assert adapter.is_ready() is False


def test_invalid_species_name_and_biography_are_regenerated_once() -> None:
    execution = FakeExecution(
        _capabilities("openai/gpt-5.2"),
        (
            '{"original_name":"狐狸","suggested_name":"fox","personal_story":"狐狸是森林里的动物代表，通常被称为聪明的探索者。"}',
            '这是给你的身份揭晓：\n{"original_name":"洛弥","suggested_name":"小洛","personal_story":"我喜欢先安静地观察周围，再邀请你一起探索新鲜事。遇到变化时，我会认真听你的想法，也愿意慢慢说出自己的感受。"}',
        ),
    )

    reveal = StructuredAdoptionNarrativeAdapter(execution).reveal(
        _candidate(), "很高兴认识你"
    )

    assert reveal.original_name == "洛弥"
    assert reveal.suggested_name == "小洛"
    assert reveal.personal_story.startswith("我喜欢")
    assert len(execution.requests) == 2
    assert all(request.allow_fallback is False for request in execution.requests)
    assert "proper name" in execution.requests[1].prompt


def test_transient_provider_failure_is_retried_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adoption_narrative, "sleep", lambda _seconds: None)
    execution = FlakyExecution(
        _capabilities("openai/gpt-5.2"),
        (
            '{"original_name":"洛弥","suggested_name":"小洛","personal_story":"我喜欢先安静地观察周围，再邀请你一起探索新鲜事。遇到变化时，我会认真听你的想法，也愿意慢慢说出自己的感受。"}',
        ),
        failures=1,
    )

    reveal = StructuredAdoptionNarrativeAdapter(execution).reveal(
        _candidate(), "很高兴认识你"
    )

    assert reveal.original_name == "洛弥"
    assert len(execution.requests) == 2
    assert all(request.allow_fallback is False for request in execution.requests)


def test_provider_failure_does_not_replace_persisted_entry_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adoption_narrative, "sleep", lambda _seconds: None)
    execution = FailingExecution(_capabilities("openai/gpt-5.2"))
    adapter = StructuredAdoptionNarrativeAdapter(execution)

    assert adapter.is_ready() is True
    with pytest.raises(RuntimeError, match="provider unavailable"):
        adapter.reveal(_candidate(), "很高兴认识你")

    assert adapter.is_ready() is True
    with pytest.raises(RuntimeError, match="provider unavailable"):
        adapter.reveal(_candidate(), "很高兴认识你")
    assert len(execution.requests) == 6
