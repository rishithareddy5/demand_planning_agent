class BuildDemandEmailService:
    def execute(self, distributor_context: dict, recommendation_response: dict) -> dict:
        distributor_id = distributor_context["distributor_id"]
        recommendations = recommendation_response["recommendations"]

        subject = f"Demand Planning Request for Distributor {distributor_id}"

        lines = [
            f"Dear Distributor {distributor_id},",
            "",
            "Please confirm your expected demand for the next 30 days.",
            "Based on your purchase graph, we suggest the following SKUs:",
            ""
        ]

        for item in recommendations:
            lines.append(f"{item['sku_id']} - {item['sku_name']}")

        lines.extend([
            "",
            "Please reply in this format:",
            "SKU001 - 100",
            "SKU002 - 250",
            "",
            "Regards,",
            "Demand Planning Team"
        ])

        return {
            "subject": subject,
            "body": "\n".join(lines)
        }