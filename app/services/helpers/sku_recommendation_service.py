from app.repositories.graph_repository import GraphRepository


class SKURecommendationService:
    def __init__(self):
        self.graph_repo = GraphRepository()

    def execute(
        self,
        distributor_id: str,
        strong_sku_ids: list[str] | None = None,
        preferred_categories: list[str] | None = None,
        exclude_sku_ids: list[str] | None = None,
        limit: int = 5,
    ):
        recommendations = self.graph_repo.get_related_recommendations(
            distributor_id=distributor_id,
            strong_sku_ids=strong_sku_ids or [],
            preferred_categories=preferred_categories or [],
            exclude_sku_ids=exclude_sku_ids or [],
            limit=limit,
        )

        return {
            "distributor_id": distributor_id,
            "recommendations": recommendations
        }
