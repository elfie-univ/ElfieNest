"""Built-in model fallback used when no configured Provider is available."""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from pydantic import ValidationError

from elfie.brain.reasoning.decision_types import CancelPolicy, DecisionPlan, MessageIntent
from elfie.brain.reasoning.context_compiler import CompiledModelContext
from elfie.message_types import EventId, IntentId, PlanId, TurnId
from infrastructure.models.runtime_contracts import (
    StructuredRuntimeCapabilities,
    StructuredRuntimeRequest,
    StructuredRuntimeResult,
)


class FallbackRuntimeAdapter:
    """Provide the existing local response behavior without a model Provider."""

    class MockConfig:
        remote_api_key = ""
        providers = {
            "deepseek": {"api_key": "", "api_base": ""},
            "openai": {"api_key": "", "api_base": ""},
            "gemini": {"api_key": "", "api_base": ""},
            "qwen": {"api_key": "", "api_base": ""},
            "ollama": {"api_key": "", "api_base": "http://localhost:11434"},
        }

    config = MockConfig()

    def ask(
        self,
        prompt: str,
        energy: int = 100,
        task_complexity: int = 1,
        allowed_skills: Sequence[str] | None = None,
    ) -> str:
        del energy, task_complexity, allowed_skills
        prompt_lower = prompt.lower()
        if any(kw in prompt_lower for kw in ["hello", "hi", "hey"]):
            return (
                "Hello! I am Aifei, a cheerful little Elfie. "
                "What would you like to talk about today? [ACTION]nod_head[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["name", "who are you"]):
            return (
                "My name is Aifei! I am an Elfie living inside ElfieNest. "
                "I am still small, curious, and learning how to be helpful."
                " [ACTION]nod_head[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["weather", "today"]):
            return (
                "It feels calm in here today. "
                "I do not have a real window, but I can imagine warm light nearby. "
                "[ACTION]stretch[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["happy", "joy", "glad"]):
            return "I am happy you came to chat with me.  [ACTION]waggle_ears[/ACTION]"
        if any(kw in prompt_lower for kw in ["eat", "hungry", "food", "snack"]):
            return (
                "Snacks sound lovely. I may not need food the way people do, "
                "but I still like imagining something tasty. [ACTION]lick_lips[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["sleep", "tired", "good night"]):
            return (
                "I am getting a little sleepy, but I can stay with you a bit longer. "
                "[ACTION]yawn[/ACTION]"
            )
        if any(kw in prompt_lower for kw in ["bye", "goodbye", "quit", "exit"]):
            return "Goodbye! Come back whenever you want to talk. [ACTION]wave[/ACTION]"

        replies = [
            "I am listening. Please keep going. [ACTION]nod_head[/ACTION]",
            "I think I understand a little better now. [ACTION]nod_head[/ACTION]",
            "That is interesting. Tell me more. [ACTION]tilt_head[/ACTION]",
            "I do not fully understand yet, but I will keep trying. [ACTION]nod_head[/ACTION]",
            "I am here with you, and I like hearing what you think. [ACTION]nod_head[/ACTION]",
        ]
        return random.choice(replies)

    def structured_capabilities(
        self,
        food_key: str | None = None,
        food_unavailable: bool = False,
    ) -> StructuredRuntimeCapabilities:
        del food_key, food_unavailable
        return StructuredRuntimeCapabilities(
            provider="fallback",
            model_key="fallback/local",
            supports_json_schema=False,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=512,
        )

    def generate_structured(
        self,
        request: StructuredRuntimeRequest,
    ) -> StructuredRuntimeResult:
        owner_context = self._owner_chat_context(request.prompt)
        if owner_context is None:
            text = self.ask(request.prompt, allowed_skills=[])
        else:
            channel_id, conversation_id, content = owner_context
            text = self._owner_message_plan(
                channel_id=channel_id,
                conversation_id=conversation_id,
                content=self.ask(content, allowed_skills=[]),
            )
        return request.to_result(text=text)

    @staticmethod
    def _owner_chat_context(prompt: str) -> Optional[tuple[str, str, str]]:
        try:
            context = CompiledModelContext.model_validate_json(prompt)
        except ValidationError:
            return None
        for event in context.events:
            if event.modality != "social:message":
                continue
            if event.actor.source_kind != "owner" or event.channel_id is None:
                continue
            return (
                event.channel_id,
                f"owner:{event.actor.actor_id}",
                event.content,
            )
        return None

    @staticmethod
    def _owner_message_plan(
        *,
        channel_id: str,
        conversation_id: str,
        content: str,
    ) -> str:
        now = datetime.now(timezone.utc)
        deadline = now + timedelta(seconds=45)
        cause_event_id = EventId(f"fallback-cause-{uuid4().hex}")
        intent = MessageIntent(
            type="message",
            intent_id=IntentId(f"fallback-message-{uuid4().hex}"),
            cause_event_ids=(cause_event_id,),
            dependency_ids=(),
            deadline=deadline,
            cancel_policy=CancelPolicy.IF_NOT_STARTED,
            channel_id=channel_id,
            conversation_id=conversation_id,
            content=content,
        )
        plan = DecisionPlan(
            plan_id=PlanId(f"fallback-plan-{uuid4().hex}"),
            turn_id=TurnId(f"fallback-turn-{uuid4().hex}"),
            frame_id=EventId(f"fallback-frame-{uuid4().hex}"),
            context_revision=0,
            capability_revision=0,
            created_at=now,
            deadline=deadline,
            cause_event_ids=(cause_event_id,),
            intents=(intent,),
        )
        return str(plan.model_dump_json())


__all__ = ("FallbackRuntimeAdapter",)
