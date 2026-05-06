from fastapi import APIRouter, HTTPException
from app.schemas.demand_schema import CombinedDemandCycleResponse
from app.schemas.distributor_schema import (
    DistributorContextResponse,
    DemandPlanResponse,
    ParsedReplyRequest,
    ReplyProcessingResponse,
    RecommendationEmailPayloadResponse,
    SKURecommendationResponse,
)
from app.services.demand_cycle_service import DemandCycleService
from app.services.distributor_service import DistributorService
from app.services.email_payload_service import EmailPayloadService
from app.services.recommendation_service import RecommendationService
from app.services.demand_plan_service import DemandPlanService

router = APIRouter(prefix="/api/v1/distributors", tags=["Distributors"])

distributor_service = DistributorService()
recommendation_service = RecommendationService()
demand_plan_service = DemandPlanService()
email_payload_service = EmailPayloadService()
demand_cycle_service = DemandCycleService()


@router.get("/{distributor_code}/context", response_model=DistributorContextResponse)
def get_distributor_context(distributor_code: str):
    try:
        return distributor_service.get_distributor_context(distributor_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{distributor_code}/sku-recommendations", response_model=SKURecommendationResponse)
def get_sku_recommendations(distributor_code: str):
    try:
        return recommendation_service.get_sku_recommendations(distributor_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    
@router.get("/{distributor_code}/demand-plan", response_model=DemandPlanResponse)
def get_demand_plan(distributor_code: str):
    try:
        return demand_plan_service.get_demand_plan(distributor_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get(
    "/{distributor_code}/email-payload",
    response_model=RecommendationEmailPayloadResponse,
)
def get_email_payload(distributor_code: str):
    try:
        return email_payload_service.build_email_payload(distributor_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/{distributor_code}/reply-plan",
    response_model=ReplyProcessingResponse,
)
def process_distributor_reply(
    distributor_code: str,
    reply_request: ParsedReplyRequest,
):
    if reply_request.distributor_code != distributor_code:
        raise HTTPException(
            status_code=400,
            detail="Path distributor_code must match payload distributor_code",
        )

    try:
        return demand_plan_service.process_reply(
            distributor_code,
            reply_request.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get(
    "/{distributor_code}/demand-cycle",
    response_model=CombinedDemandCycleResponse,
)
def get_demand_cycle(distributor_code: str):
    try:
        return demand_cycle_service.run_mocked_demand_cycle(distributor_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
