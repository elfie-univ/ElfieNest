"""Strong-model adapter for post-acceptance Adoption identity reveals."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from time import monotonic, sleep
from typing import Any, Mapping, Protocol

from elfie.genesis import BIG_FIVE_TRAITS, CandidateReveal, GenesisCandidate
from elfie.profile import get_species_definition

from .model_execution_adapter import StructuredCapabilityView
from .model_execution_contracts import (
    StructuredGenerationMode,
    StructuredMessage,
    StructuredModelExecutionRequest,
)

_REVEAL_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["original_name", "suggested_name", "personal_story"],
    "properties": {
        "original_name": {"type": "string", "minLength": 2, "maxLength": 16},
        "suggested_name": {"type": "string", "minLength": 2, "maxLength": 12},
        "personal_story": {"type": "string", "minLength": 24, "maxLength": 220},
    },
}
_REVEAL_RETRY_DELAYS_SECONDS = (0.35, 0.8)
_REVEAL_TOTAL_TIMEOUT_SECONDS = 30.0


class AdoptionStructuredModelExecution(Protocol):
    def adoption_capabilities(self) -> StructuredCapabilityView: ...

    def generate_adoption_structured(
        self, request: StructuredModelExecutionRequest
    ): ...


class StructuredAdoptionNarrativeAdapter:
    """Use only a qualified structured model for names and short biography."""

    def __init__(self, execution: AdoptionStructuredModelExecution) -> None:
        self._execution = execution

    def is_ready(self) -> bool:
        return self._qualified_capabilities() is not None

    def _qualified_capabilities(self) -> StructuredCapabilityView | None:
        try:
            capabilities = self._execution.adoption_capabilities()
        except (AttributeError, OSError, RuntimeError, ValueError):
            return None
        return capabilities if _is_qualified(capabilities) else None

    def reveal(
        self,
        candidate: GenesisCandidate,
        invitation_message: str,
        *,
        deadline: float | None = None,
    ) -> CandidateReveal:
        deadline = (
            deadline
            if deadline is not None
            else monotonic() + _REVEAL_TOTAL_TIMEOUT_SECONDS
        )
        capabilities = self._qualified_capabilities()
        if capabilities is None:
            raise RuntimeError("configured model is temporarily unavailable")
        mode = (
            StructuredGenerationMode.JSON_SCHEMA
            if capabilities.supports_json_schema
            else StructuredGenerationMode.JSON_TEXT
        )
        feedback = ""
        for attempt in range(len(_REVEAL_RETRY_DELAYS_SECONDS) + 1):
            remaining = deadline - monotonic()
            if remaining <= 0.0:
                raise TimeoutError("Adoption reveal exceeded its total time budget")
            prompt = _prompt(candidate, invitation_message, feedback)
            request = StructuredModelExecutionRequest(
                prompt=prompt,
                messages=(
                    StructuredMessage(
                        role="system",
                        content=(
                            "你在为一位已经同意继续认识用户的 Elfie 写身份揭晓。"
                            "名字必须是专有名字，自我介绍必须用第一人称自然中文。"
                            "只输出符合 JSON Schema 的 JSON，不要写解释、Markdown 或额外字段。"
                        ),
                    ),
                    StructuredMessage(role="user", content=prompt),
                ),
                response_schema_name="adoption_candidate_reveal_v1",
                response_schema=_REVEAL_SCHEMA,
                selected_mode=mode,
                allowed_tools=(),
                # Identity reveals must never silently fall back to the tiny
                # emergency model. A weak fallback can return species labels or
                # metadata as a fake name and makes a configured outage look
                # like a successful invitation.
                allow_fallback=False,
                provider=capabilities.provider,
                model_key=capabilities.model_key,
                temperature=0.62,
                max_tokens=min(384, capabilities.max_output_tokens),
                timeout_seconds=remaining,
            )
            try:
                result = self._execution.generate_adoption_structured(request)
            except (OSError, RuntimeError) as error:
                if attempt >= len(_REVEAL_RETRY_DELAYS_SECONDS):
                    raise
                remaining = deadline - monotonic()
                if remaining <= 0.0:
                    raise TimeoutError(
                        "Adoption reveal exceeded its total time budget"
                    ) from error
                sleep(min(_REVEAL_RETRY_DELAYS_SECONDS[attempt], remaining))
                continue
            try:
                return _validated_reveal(_parse_json(result.text), candidate.species_id)
            except ValueError as error:
                if attempt >= len(_REVEAL_RETRY_DELAYS_SECONDS):
                    raise
                remaining = deadline - monotonic()
                if remaining <= 0.0:
                    raise TimeoutError(
                        "Adoption reveal exceeded its total time budget"
                    ) from error
                feedback = str(error)
        raise RuntimeError("Adoption reveal validation did not complete")

    def reveal_many(
        self,
        candidates: tuple[GenesisCandidate, ...],
        invitation_message: str,
    ) -> Mapping[str, CandidateReveal]:
        """Run the independent invitation reveals concurrently at the Adapter boundary."""
        if not candidates:
            return {}
        executor = ThreadPoolExecutor(
            max_workers=len(candidates),
            thread_name_prefix="adoption-reveal",
        )
        deadline = monotonic() + _REVEAL_TOTAL_TIMEOUT_SECONDS
        futures = {
            candidate.candidate_id: executor.submit(
                self.reveal,
                candidate,
                invitation_message,
                deadline=deadline,
            )
            for candidate in candidates
        }
        try:
            results: dict[str, CandidateReveal] = {}
            for candidate_id, future in futures.items():
                remaining = deadline - monotonic()
                if remaining <= 0.0:
                    raise TimeoutError("Adoption reveal exceeded its total time budget")
                try:
                    results[candidate_id] = future.result(timeout=remaining)
                except FutureTimeoutError as error:
                    raise TimeoutError(
                        "Adoption reveal exceeded its total time budget"
                    ) from error
            return results
        finally:
            for future in futures.values():
                future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)


def _is_qualified(capabilities: object) -> bool:
    provider = str(getattr(capabilities, "provider", ""))
    model_key = str(getattr(capabilities, "model_key", ""))
    try:
        max_tokens = int(getattr(capabilities, "max_output_tokens", 0))
    except (TypeError, ValueError):
        return False
    structured = bool(
        getattr(capabilities, "supports_json_schema", False)
        or getattr(capabilities, "supports_json_mode", False)
        or getattr(capabilities, "supports_tool_calling", False)
    )
    return (
        bool(provider)
        and bool(model_key)
        and provider.lower() != "fallback"
        and "fallback" not in model_key.lower()
        and structured
        and max_tokens >= 256
        and not _is_obviously_too_small(model_key)
    )


def _is_obviously_too_small(model_key: str) -> bool:
    for match in re.finditer(
        r"(?<![\w.])(\d+(?:\.\d+)?)([bm])\b", model_key, re.IGNORECASE
    ):
        size = float(match.group(1))
        billions = size if match.group(2).lower() == "b" else size / 1000.0
        if billions < 7.0:
            return True
    return False


def _prompt(
    candidate: GenesisCandidate,
    invitation_message: str,
    validation_feedback: str = "",
) -> str:
    scores = dict(zip(BIG_FIVE_TRAITS, candidate.personality.candidate.scores))
    labels = "、".join(candidate.personality.candidate.labels) or "独一无二"
    return json.dumps(
        {
            "task": "以这位 Elfie 本人的口吻，生成身份名字与一段自然的初次自我介绍。",
            "hard_requirements": [
                "original_name 必须是 2-16 字符的专有名字，不能是物种名、类别名或候选编号",
                "suggested_name 必须是 2-12 字符的地球昵称，并且不能与 original_name 相同",
                "personal_story 必须是第一人称自然中文，包含“我”，写 2-3 句、24-220 字",
                "自我介绍只写自己的性格、相处方式或喜欢的事，不解释物种知识，不罗列标签",
                "不要写年龄月数、模型术语、提示词、英文介绍或书名百科内容",
            ],
            "candidate": {
                "species_id": candidate.species_id,
                "life_stage": candidate.life_stage,
                "age_months": candidate.age_months,
                "gender": candidate.gender,
                "big_five_scores": scores,
                "personality_labels": labels,
                "invitation_message": invitation_message,
            },
            "previous_validation_feedback": validation_feedback,
        },
        ensure_ascii=False,
    )


def _parse_json(text: str) -> Mapping[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if len(lines) < 3:
            raise ValueError("Adoption reveal code fence is incomplete")
        raw = "\n".join(lines[1:]).rsplit("```", 1)[0].strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Adoption reveal must contain a JSON object") from error
        try:
            payload = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as nested_error:
            raise ValueError("Adoption reveal JSON is invalid") from nested_error
    if not isinstance(payload, dict):
        raise ValueError("Adoption reveal must be a JSON object")
    return payload


def _validated_reveal(payload: Mapping[str, Any], species_id: str) -> CandidateReveal:
    original = _text(payload.get("original_name"), 16, minimum=2)
    suggested = _text(payload.get("suggested_name"), 12, minimum=2)
    story = _text(payload.get("personal_story"), 220, minimum=24)
    _validate_name(original, species_id)
    _validate_name(suggested, species_id)
    if _normalized_name(original) == _normalized_name(suggested):
        raise ValueError("original_name and suggested_name must be different")
    _validate_story(story)
    return CandidateReveal(
        original_name=original,
        suggested_name=suggested,
        personal_story=story,
    )


def _text(value: object, maximum: int, *, minimum: int = 1) -> str:
    if not isinstance(value, str):
        raise ValueError("Adoption reveal text is invalid")
    value = value.strip()
    if len(value) < minimum or len(value) > maximum:
        raise ValueError("Adoption reveal text length is invalid")
    return value


def _normalized_name(value: str) -> str:
    return re.sub(r"[\s._·\-—'’]", "", value).casefold()


def _validate_name(value: str, species_id: str) -> None:
    normalized = _normalized_name(value)
    forbidden = {
        "fox",
        "foxyfox",
        "dog",
        "puppy",
        "狐",
        "狐狸",
        "小狐狸",
        "狗",
        "小狗",
        "精灵",
        "elfie",
        "anonymous",
        "匿名候选",
    }
    species_tokens = {
        "fox",
        "狐",
        "狐狸",
        "dog",
        "狗",
        "小狗",
        "cat",
        "猫",
        "小猫",
    }
    try:
        species = get_species_definition(species_id)
    except ValueError:
        species = None
    if species is not None:
        species_tokens.update(
            {
                _normalized_name(species.display_name),
                _normalized_name(species.display_name_zh),
                _normalized_name(species.canon_id),
            }
        )
    if normalized in forbidden or any(token in normalized for token in species_tokens):
        raise ValueError(
            "Adoption reveal name must be a proper name, not a species label"
        )
    if normalized.startswith(("候选", "candidate")):
        raise ValueError("Adoption reveal name must not be a candidate number")


def _validate_story(value: str) -> None:
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", value))
    if "我" not in value or cjk_count < 20:
        raise ValueError(
            "Adoption personal_story must be a natural first-person Chinese introduction"
        )
    forbidden_fragments = (
        "personality label",
        "months old",
        "《",
        "物种的代表",
        "通常被称为",
    )
    if any(fragment.casefold() in value.casefold() for fragment in forbidden_fragments):
        raise ValueError(
            "Adoption personal_story must not be encyclopedic or model-generated metadata"
        )
    if re.search(r"\b\d+\s*(?:个?月|months?)\b", value, re.IGNORECASE):
        raise ValueError("Adoption personal_story must not expose age-month metadata")


class UnavailableAdoptionNarrativeAdapter:
    """Explicit fail-closed adapter used when no qualified model is configured."""

    def is_ready(self) -> bool:
        return False

    def reveal(
        self,
        candidate: GenesisCandidate,
        invitation_message: str,
    ) -> CandidateReveal:
        del candidate, invitation_message
        raise RuntimeError("Adoption narrative model is unavailable")

    def reveal_many(
        self,
        candidates: tuple[GenesisCandidate, ...],
        invitation_message: str,
    ) -> Mapping[str, CandidateReveal]:
        del candidates, invitation_message
        raise RuntimeError("Adoption narrative model is unavailable")


__all__ = (
    "StructuredAdoptionNarrativeAdapter",
    "UnavailableAdoptionNarrativeAdapter",
)
