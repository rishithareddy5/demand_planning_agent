from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.fetch_distributor_context_service import FetchDistributorContextService
from app.services.sku_recommendation_service import SKURecommendationService
from app.services.build_demand_email_service import BuildDemandEmailService

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/{distributor_id}")
def get_recommendations(distributor_id: str, db: Session = Depends(get_db)):
    context_service = FetchDistributorContextService(db)
    recommendation_service = SKURecommendationService()
    email_service = BuildDemandEmailService()

    context = context_service.execute(distributor_id)
    recommendations = recommendation_service.execute(distributor_id)
    email_preview = email_service.execute(context, recommendations)

    return {
        "context": context,
        "recommendations": recommendations,
        "email_preview": email_preview
    }