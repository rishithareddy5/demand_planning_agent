from typing import List
from pydantic import BaseModel, Field
from app.schemas.distributor_schema import (
    DemandPlanResponse,
    RecommendationEmailPayloadResponse,
)


class ParsedSKULine(BaseModel):
    sku_code: str = Field(..., min_length=1)
    sku_name: str | None = None
    monthly_quantity: int | None = Field(default=None, ge=0)
    raw_text: str | None = None


class ParsedReplyResponse(BaseModel):
    distributor_code: str
    confirmed_by: str | None = None
    notes: str | None = None
    parsed_lines: List[ParsedSKULine]


class ValidationIssue(BaseModel):
    sku_code: str | None = None
    message: str


class ValidationResultResponse(BaseModel):
    distributor_code: str
    is_valid: bool
    issues: List[ValidationIssue]


class WeeklyDemandLine(BaseModel):
    sku_code: str
    monthly_quantity: int
    weekly_quantities: List[int] = Field(..., min_length=4, max_length=4)


class WeeklyDemandPlanResponse(BaseModel):
    distributor_code: str
    weekly_plan: List[WeeklyDemandLine]
    week1_qty: int
    week2_qty: int
    week3_qty: int
    week4_qty: int


class CombinedDemandCycleResponse(BaseModel):
    distributor_code: str
    demand_plan: DemandPlanResponse
    email_payload: RecommendationEmailPayloadResponse
    parsed_reply: ParsedReplyResponse
    validation_result: ValidationResultResponse
    weekly_demand_plan: WeeklyDemandPlanResponse
