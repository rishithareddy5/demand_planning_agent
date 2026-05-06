from typing import List


def build_demand_email(
    distributor_id: str,
    distributor_email: str,
    recommendations: List[str] = None
) -> dict:

    if recommendations:
        recommended_block = "\n".join(
            f"{i}. {product}"
            for i, product in enumerate(recommendations, start=1)
        )
    else:
        recommended_block = "  No recommendations available at this time."

    subject = "Demand Request for Upcoming Month"

    body = f"""Dear Distributor,

Greetings from Lipton Enterprises.

We are planning for the upcoming month and request you to share your expected product demand.

Your Distributor ID: {distributor_id}

Recommended Products for You This Month:
{recommended_block}

Please provide your expected demand for the next 30 days in the following format:

Product Name - Quantity

Example:
MALKIST CHEESE 48 PCS X 72 - 100
BENG BENG WAFER 22GM - 250

You may also fill in the attached Excel sheet and reply to this email.
If replying via Excel, please keep the columns: Product Name | Quantity.

We look forward to your response.

Regards,
Lipton Enterprises - Demand Planning Team
"""

    return {
        "to_email":  distributor_email,
        "subject":   subject,
        "body":      body,
    }