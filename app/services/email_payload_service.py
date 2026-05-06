from app.services.demand_plan_service import DemandPlanService
from app.services.helpers.build_demand_email_service import BuildDemandEmailService


class EmailPayloadService:
    def __init__(self) -> None:
        self.demand_plan_service = DemandPlanService()
        self.build_demand_email_service = BuildDemandEmailService()

    def build_email_payload(self, distributor_code: str) -> dict:
        demand_plan = self.demand_plan_service.get_demand_plan(distributor_code)
        distributor = demand_plan["distributor"]
        recommended_skus = demand_plan["recommended_skus"]

        helper_payload = self._build_helper_payload(distributor, recommended_skus)
        email_subject = helper_payload.get(
            "subject",
            f"Demand Plan Recommendation for {distributor['distributor_code']}",
        )
        email_body = helper_payload.get("body", self._build_default_body(distributor, recommended_skus))

        return {
            "distributor_code": distributor["distributor_code"],
            "distributor_name": distributor["name"],
            "email_subject": email_subject,
            "email_body": email_body,
            "recommended_skus": recommended_skus,
        }

    def _build_helper_payload(self, distributor: dict, recommended_skus: list[dict]) -> dict:
        distributor_context = {
            "distributor_id": distributor["distributor_id"],
            "sku_demand_signals": distributor.get("sku_demand_signals", []),
        }
        recommendation_response = {
            "recommendations": recommended_skus,
        }

        try:
            return self.build_demand_email_service.execute(
                distributor_context,
                recommendation_response,
            )
        except Exception:
            return {}

    @staticmethod
    def _build_default_body(distributor: dict, recommended_skus: list[dict]) -> str:
        body_lines = [
            f"Hello {distributor['name']},",
            "",
            "Please review the recommended SKUs below for the upcoming demand plan.",
            "",
        ]

        for sku in recommended_skus:
            body_lines.append(
                f"- {sku['sku_code']} ({sku['sku_name']}): score {sku['score']}"
            )

        body_lines.extend([
            "",
            "Please reply with your confirmed monthly quantities for each SKU.",
        ])
        return "\n".join(body_lines)
