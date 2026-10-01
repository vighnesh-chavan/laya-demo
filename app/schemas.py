from typing import Literal, Union

from pydantic import BaseModel, Field, model_validator


class EnumOption(BaseModel):
    label: str
    description: str | None = None


class DecisionRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The question to decide on")
    type: Literal["bool", "enum", "number"]
    options: list[EnumOption] | None = Field(
        default=None, description="Required when type == 'enum'"
    )
    min_value: float | None = Field(default=None, description="Required when type == 'number'")
    max_value: float | None = Field(default=None, description="Required when type == 'number'")

    @model_validator(mode="after")
    def _check_type_fields(self) -> "DecisionRequest":
        if self.type == "enum":
            if not self.options or len(self.options) < 2:
                raise ValueError("type 'enum' requires at least 2 'options'")
        if self.type == "number":
            if self.min_value is None or self.max_value is None:
                raise ValueError("type 'number' requires 'min_value' and 'max_value'")
            if self.min_value >= self.max_value:
                raise ValueError("'min_value' must be less than 'max_value'")
        return self


class DecisionResponse(BaseModel):
    answer: Union[bool, str, float]
    type: Literal["bool", "enum", "number"]
    confidence: float
    latency_ms: float
