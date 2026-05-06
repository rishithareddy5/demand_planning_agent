class DemandPlanningService:
    def build_weekly_plan(
        self,
        distributor_code: str,
        confirmed_30d_qty: int,
    ) -> dict:
        base_quantity = confirmed_30d_qty // 4
        remainder = confirmed_30d_qty % 4

        weekly_quantities = [base_quantity] * 4
        for index in range(remainder):
            weekly_quantities[index] += 1

        return {
            "distributor_code": distributor_code,
            "weekly_plan": [
                {
                    "sku_code": "CONFIRMED_30D_TOTAL",
                    "monthly_quantity": confirmed_30d_qty,
                    "weekly_quantities": weekly_quantities,
                }
            ],
            "week1_qty": weekly_quantities[0],
            "week2_qty": weekly_quantities[1],
            "week3_qty": weekly_quantities[2],
            "week4_qty": weekly_quantities[3],
        }
