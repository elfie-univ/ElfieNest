"""Elfie Lab HTTP 边界请求模型。"""

from typing import Any, Dict, List, Literal, Optional

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

    food_id: Optional[str] = Field(default=None, min_length=1, max_length=80)
    subscription_id: Optional[str] = Field(default=None, min_length=1, max_length=160)
    subscription_name: Optional[str] = Field(default=None, max_length=80)
    connection_type: Literal["ollama", "openai"]
    display_name: str = Field(min_length=1, max_length=80)
    api_base: Optional[str] = Field(default=None, max_length=500)
    api_key: Optional[str] = Field(default=None, max_length=2000)
    models: List[str] = Field(default_factory=list)
    primary_model: str = Field(default="", max_length=500)
    reasoning_model: str = Field(default="", max_length=500)
    vision_model: str = Field(default="", max_length=500)
    tool_model: str = Field(default="", max_length=500)
    fallback_model: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_configuration(self) -> "ConfigureFoodRequest":
        normalized_name = self.display_name.strip()
        if not normalized_name:
            raise ValueError("粮食名称不能为空")
        self.display_name = normalized_name

        normalized_models = tuple(
            dict.fromkeys(model.strip() for model in self.models if model.strip())
        )
        if not normalized_models:
            raise ValueError("粮食配置至少要包含一个模型")
        self.models = list(normalized_models)

        if self.food_id:
            self.food_id = self.food_id.strip()
        if self.subscription_id:
            self.subscription_id = self.subscription_id.strip()
        if self.subscription_name is not None:
            self.subscription_name = self.subscription_name.strip() or None

        primary = self.primary_model.strip()
        if not primary:
            raise ValueError("主模型不能为空")
        if primary not in self.models:
            raise ValueError("主模型必须来自“模型列表”")
        self.primary_model = primary

        role_models = {
            "reasoning_model": self.reasoning_model.strip(),
            "vision_model": self.vision_model.strip(),
            "tool_model": self.tool_model.strip(),
            "fallback_model": self.fallback_model.strip(),
        }
        for role_name, model_reference in role_models.items():
            if model_reference and model_reference not in self.models:
                raise ValueError(f"{role_name}必须来自“模型列表”")
            setattr(self, role_name, model_reference)

        if self.api_base is not None:
            self.api_base = self.api_base.strip()
            if self.api_base == "":
                self.api_base = None
        if self.api_key is not None:
            self.api_key = self.api_key.strip()
            if self.api_key == "":
                self.api_key = None

        if self.connection_type == "ollama" and self.api_key is not None:
            raise ValueError("本机 Ollama 不需要 API Key")
        if (
            self.food_id is None
            and not self.subscription_id
            and self.connection_type == "openai"
            and self.api_base is None
        ):
            raise ValueError("新建粮食必须填写 API URL")
        return self


class ProbeOllamaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_base: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def normalize_api_base(self) -> "ProbeOllamaRequest":
        if self.api_base is not None:
            self.api_base = self.api_base.strip() or None
        return self


class SaveReviewerSubscriptionRequest(BaseModel):
    """独立远程评审订阅；不接受 Ollama、本地地址或粮食字段。"""

    model_config = ConfigDict(extra="forbid")

    subscription_id: Optional[str] = Field(default=None, min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=80)
    api_base: str = Field(min_length=1, max_length=500)
    api_key: Optional[str] = Field(default=None, max_length=2000)
    models: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_configuration(self) -> "SaveReviewerSubscriptionRequest":
        self.display_name = self.display_name.strip()
        self.api_base = self.api_base.strip()
        self.subscription_id = (
            self.subscription_id.strip() if self.subscription_id else None
        )
        self.api_key = self.api_key.strip() if self.api_key else None
        self.models = list(
            dict.fromkeys(item.strip() for item in self.models if item.strip())
        )
        if not self.models:
            raise ValueError("评审订阅至少要包含一个模型")
        return self


class MessageAttachmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_id: str = Field(min_length=1, max_length=70)
    filename: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^\S(?:.*\S)?$",
    )


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_domain: Literal["communication", "embodied"]
    message: str = Field(default="", max_length=8000)
    vision_media_id: Optional[str] = Field(default=None, max_length=70)
    attachments: List[MessageAttachmentRequest] = Field(
        default_factory=list, max_length=5
    )
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
            if not self.message.strip() and not self.attachments:
                raise ValueError("通信输入必须包含消息或附件")
            if (
                self.vision_media_id is not None
                or self.impact_force > 0
                or self.gentle_stroke > 0
                or self.salience_score >= 70
            ):
                raise ValueError("通信输入不能混入具身刺激")
        elif self.attachments:
            raise ValueError("具身输入不能混入通信附件")
        return self


class PortraitRequest(BaseModel):
    data_url: str = Field(min_length=32, max_length=7_000_000)


class CreateEvaluationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: Literal["quick", "standard"]
    food_key: str = Field(min_length=1, max_length=160)
    judge_subscription_id: str = Field(min_length=1, max_length=160)
    judge_model: str = Field(default="", max_length=500)


class CreateSingleEvaluationBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elfie_id: str = Field(min_length=1, max_length=160)
    suite: Literal["quick", "standard"]
    food_key: str = Field(min_length=1, max_length=160)
    judge_subscription_id: str = Field(min_length=1, max_length=160)
    judge_model: str = Field(default="", max_length=500)
    title: str = Field(default="", max_length=80)
    purpose: str = Field(default="", max_length=500)


class CreatePairedEvaluationBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elfie_id: str = Field(min_length=1, max_length=160)
    suite: Literal["quick", "standard"]
    comparison_variable: Literal["food", "code"]
    food_key_a: Optional[str] = Field(default=None, min_length=1, max_length=160)
    food_key_b: Optional[str] = Field(default=None, min_length=1, max_length=160)
    judge_subscription_id: str = Field(min_length=1, max_length=160)
    judge_model: str = Field(default="", max_length=500)
    code_ref_a: Optional[str] = Field(default=None, min_length=1, max_length=240)
    code_ref_b: Optional[str] = Field(default=None, min_length=1, max_length=240)
    title: str = Field(default="", max_length=80)
    purpose: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_pair_inputs(self) -> "CreatePairedEvaluationBatchRequest":
        if self.comparison_variable == "food":
            if self.food_key_a is None:
                raise ValueError("粮食对比必须选择粮食 A")
            if self.food_key_b is None:
                raise ValueError("粮食对比必须选择粮食 B")
            if self.food_key_a.lower().strip() == self.food_key_b.lower().strip():
                raise ValueError("粮食 A 与粮食 B 必须不同")
            if self.code_ref_a is not None or self.code_ref_b is not None:
                raise ValueError("粮食对比不能选择两个代码分支")
        else:
            if self.food_key_a is not None:
                raise ValueError("代码对比只选择一个共同粮食")
            if self.food_key_b is None:
                raise ValueError("代码对比必须选择共同粮食")
            if self.code_ref_a is None or self.code_ref_b is None:
                raise ValueError("代码对比必须选择代码分支 A 和 B")
            code_ref_a = self.code_ref_a.strip()
            code_ref_b = self.code_ref_b.strip()
            if code_ref_a == code_ref_b:
                raise ValueError("代码分支 A 与代码分支 B 必须不同")
            self.code_ref_a = code_ref_a
            self.code_ref_b = code_ref_b
        return self


class CompareEvaluationReportsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_a_id: str = Field(min_length=1, max_length=160)
    report_b_id: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_distinct_reports(self) -> "CompareEvaluationReportsRequest":
        if self.report_a_id == self.report_b_id:
            raise ValueError("请选择两份不同的评测报告")
        return self


__all__ = (
    "BigFiveUpdateRequest",
    "ConfigureFoodRequest",
    "CreateElfieRequest",
    "CreateEvaluationRunRequest",
    "CreatePairedEvaluationBatchRequest",
    "CreateSingleEvaluationBatchRequest",
    "CompareEvaluationReportsRequest",
    "SaveReviewerSubscriptionRequest",
    "MessageAttachmentRequest",
    "PortraitRequest",
    "ProbeOllamaRequest",
    "TurnRequest",
)
