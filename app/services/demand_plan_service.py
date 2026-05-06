from app.services.distributor_service import DistributorService
from app.services.recommendation_service import RecommendationService
from app.services.validation_service import ValidationService


class DemandPlanService:
    def __init__(self) -> None:
        self.distributor_service = DistributorService()
        self.recommendation_service = RecommendationService()
        self.validation_service = ValidationService()

    def get_demand_plan(self, distributor_code: str) -> dict:
        distributor = self.distributor_service.get_distributor_context(distributor_code)
        recommendations = self.recommendation_service.get_sku_recommendations(distributor_code)

        return {
            "distributor": distributor,
            "recommended_skus": recommendations["recommended_skus"],
        }

    def process_reply(self, distributor_code: str, reply_payload: dict) -> dict:
        distributor = self.distributor_service.get_distributor_context(distributor_code)
        recommendations = self.recommendation_service.get_sku_recommendations(distributor_code)
        reply_items = reply_payload["items"]

        issues = self.validation_service.validate_distributor_reply(
            distributor_code=distributor_code,
            reply_items=reply_items,
            recommended_skus=recommendations["recommended_skus"],
        )

        weekly_plan = [
            {
                "sku_code": item["sku_code"],
                "monthly_quantity": item["monthly_quantity"],
                "weekly_quantities": self._split_monthly_quantity(item["monthly_quantity"]),
            }
            for item in reply_items
        ]

        return {
            "distributor_code": distributor["distributor_code"],
            "distributor_name": distributor["name"],
            "confirmed_by": reply_payload["confirmed_by"],
            "notes": reply_payload.get("notes"),
            "is_valid": len(issues) == 0,
            "issues": issues,
            "weekly_plan": weekly_plan,
        }

    @staticmethod
    def _split_monthly_quantity(monthly_quantity: int) -> list[int]:
        base_quantity = monthly_quantity // 4
        remainder = monthly_quantity % 4

        weekly_quantities = [base_quantity] * 4
        for index in range(remainder):
            weekly_quantities[index] += 1

        return weekly_quantities
