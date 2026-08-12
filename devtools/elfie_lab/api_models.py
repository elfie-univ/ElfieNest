"""Elfie Lab HTTP 边界请求模型。"""

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CreateElfieRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    species_id: Literal["dog", "fox"]
    age_years: float = Field(gt=0.0, le=100.0)
    description: str = Field(min_length=1, max_length=240)
    appearance_description: str = Field(min_length=1, max_length=1000)
    personality_description: str = Field(min_length=1, max_length=1000)


class BigFiveUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    openness: float = Field(ge=0.0, le=1.0)
    conscientiousness: float = Field(ge=0.0, le=1.0)
    extraversion: float = Field(ge=0.0, le=1.0)
    agreeableness: float = Field(ge=0.0, le=1.0)
    neuroticism: float = Field(ge=0.0, le=1.0)


class ConfigureFoodRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["local", "openai"]
    model: str = Field(min_length=1, max_length=200)
    api_base: Optional[str] = Field(default=None, max_length=500)
    api_key: Optional[str] = Field(default=None, max_length=2000)
    alias: Optional[str] = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_connection_fields(self) -> "ConfigureFoodRequest":
        if self.mode == "openai":
            if not self.api_base or not self.api_base.strip():
                raise ValueError("OpenAI 兼容服务必须填写 URL")
            if not self.api_key or not self.api_key.strip():
                raise ValueError("OpenAI 兼容服务必须填写 Token")
        elif self.api_key and self.api_key.strip():
            raise ValueError("本地模型不需要 Token")
        return self


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_domain: Literal["communication", "embodied"]
    message: str = Field(default="", max_length=8000)
    vision_media_id: Optional[str] = Field(default=None, max_length=70)
    food_key: str = Field(min_length=1, max_length=40)
    temperature: float = Field(default=24.0, ge=-50.0, le=100.0)
    is_network_online: bool = True
    salience_score: float = Field(default=20.0, ge=0.0, le=100.0)
    impact_force: float = Field(default=0.0, ge=0.0, le=1000.0)
    impact_direction: str = Field(default="none", max_length=40)
    gentle_stroke: float = Field(default=0.0, ge=0.0, le=100.0)
    state_injection: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_domain(self) -> "TurnRequest":
        if self.source_domain == "communication":
            if not self.message.strip():
                raise ValueError("通信输入必须包含消息")
            if (
                self.vision_media_id is not None
                or self.impact_force > 0
                or self.gentle_stroke > 0
                or self.salience_score >= 70
            ):
                raise ValueError("通信输入不能混入具身刺激")
        return self


class PortraitRequest(BaseModel):
    data_url: str = Field(min_length=32, max_length=7_000_000)


__all__ = (
    "BigFiveUpdateRequest",
    "ConfigureFoodRequest",
    "CreateElfieRequest",
    "PortraitRequest",
    "TurnRequest",
)
