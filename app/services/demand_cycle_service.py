from app.services.demand_plan_service import DemandPlanService
from app.services.demand_planning_service import DemandPlanningService
from app.services.email_payload_service import EmailPayloadService
from app.services.reply_parse_service import ReplyParseService
from app.services.validation_service import ValidationService


class DemandCycleService:
    def __init__(self) -> None:
        self.demand_plan_service = DemandPlanService()
        self.email_payload_service = EmailPayloadService()
        self.reply_parse_service = ReplyParseService()
        self.validation_service = ValidationService()
        self.demand_planning_service = DemandPlanningService()

    def run_mocked_demand_cycle(self, distributor_code: str) -> dict:
        demand_plan = self.demand_plan_service.get_demand_plan(distributor_code)
        email_payload = self.email_payload_service.build_email_payload(distributor_code)
        parsed_reply = self.reply_parse_service.parse_reply(distributor_code).model_dump()

        confirmed_30d_qty = sum(
            line.get("monthly_quantity", 0) or 0
            for line in parsed_reply["parsed_lines"]
        )

        validation_input = {
            "distributor_code": parsed_reply["distributor_code"],
            "confirmed_30d_qty": confirmed_30d_qty,
            "sku_lines": [
                {
                    "sku_code": line.get("sku_code"),
                    "qty": line.get("monthly_quantity"),
                }
                for line in parsed_reply["parsed_lines"]
            ],
        }
        validation_result = self.validation_service.validate_parsed_reply(validation_input)
        weekly_demand_plan = self.demand_planning_service.build_weekly_plan(
            distributor_code=distributor_code,
            confirmed_30d_qty=confirmed_30d_qty,
        )

        return {
            "distributor_code": distributor_code,
            "demand_plan": demand_plan,
            "email_payload": email_payload,
            "parsed_reply": parsed_reply,
            "validation_result": validation_result,
            "weekly_demand_plan": weekly_demand_plan,
        }
