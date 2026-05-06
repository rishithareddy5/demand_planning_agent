class ValidationService:
    @staticmethod
    def validate_distributor_context(data: dict) -> dict:
        required_fields = [
            "distributor_id",
            "name",
            "region",
            "channel",
            "recent_order_volume",
            "priority",
        ]

        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            raise ValueError(f"Missing required distributor fields: {', '.join(missing_fields)}")

        return data

    @staticmethod
    def validate_sku_data(data: dict) -> dict:
        required_fields = [
            "sku_id",
            "sku_name",
            "regions",
            "channels",
            "base_score",
        ]

        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            raise ValueError(f"Missing required SKU fields: {', '.join(missing_fields)}")

        return data

    @staticmethod
    def validate_distributor_reply(
        distributor_code: str,
        reply_items: list[dict],
        recommended_skus: list[dict],
    ) -> list[dict]:
        recommended_sku_codes = {sku["sku_code"] for sku in recommended_skus}
        issues: list[dict] = []

        for item in reply_items:
            sku_code = item["sku_code"]
            monthly_quantity = item["monthly_quantity"]

            if sku_code not in recommended_sku_codes:
                issues.append({
                    "sku_code": sku_code,
                    "message": (
                        f"SKU '{sku_code}' is not part of the recommended set for distributor "
                        f"'{distributor_code}'"
                    ),
                })

            if monthly_quantity < 0:
                issues.append({
                    "sku_code": sku_code,
                    "message": "Monthly quantity cannot be negative",
                })

        return issues

    @staticmethod
    def validate_parsed_reply(parsed_reply: dict) -> dict:
        distributor_code = parsed_reply.get("distributor_code")
        confirmed_30d_qty = parsed_reply.get("confirmed_30d_qty")
        sku_lines = parsed_reply.get("sku_lines")

        # Allow the current placeholder parser shape to flow through this validator too.
        if sku_lines is None:
            sku_lines = parsed_reply.get("parsed_lines", [])

        issues: list[dict] = []

        if not distributor_code:
            issues.append({
                "sku_code": None,
                "message": "distributor_code is required",
            })

        if confirmed_30d_qty is None or confirmed_30d_qty <= 0:
            issues.append({
                "sku_code": None,
                "message": "confirmed_30d_qty must be greater than 0",
            })

        if not sku_lines:
            issues.append({
                "sku_code": None,
                "message": "sku_lines must not be empty",
            })

        for line in sku_lines or []:
            sku_code = line.get("sku_code")
            quantity = line.get("qty", line.get("monthly_quantity"))

            if not sku_code:
                issues.append({
                    "sku_code": None,
                    "message": "Each sku line must include sku_code",
                })

            if quantity is None or quantity <= 0:
                issues.append({
                    "sku_code": sku_code,
                    "message": "Each sku line must include qty greater than 0",
                })

        return {
            "distributor_code": distributor_code or "",
            "is_valid": len(issues) == 0,
            "issues": issues,
        }
