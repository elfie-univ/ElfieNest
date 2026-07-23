"""Elfie Lab HTTP 边界请求模型。"""

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class PortraitRequest(BaseModel):
    data_url: str = Field(min_length=32, max_length=7_000_000)


__all__ = (
    "BigFiveUpdateRequest",
    "CreateElfieRequest",
    "PortraitRequest",
    "TurnRequest",
)
