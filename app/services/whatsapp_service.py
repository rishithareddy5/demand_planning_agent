"""# app/services/whatsapp_service.py
import os
import logging
from twilio.rest import Client

logger = logging.getLogger(__name__)

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN")
FROM_NUMBER  = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")


def send_whatsapp_message(to_number: str, body: str) -> dict:
    
    Sends a WhatsApp message via Twilio.
    to_number must be in format: whatsapp:+91XXXXXXXXXX
    
    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        message = client.messages.create(
            body=body,
            from_=FROM_NUMBER,
            to=f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number
        )
        logger.info(f"[WhatsApp] Sent to {to_number} | SID: {message.sid}")
        return {"status": "success", "sid": message.sid}
    except Exception as e:
        logger.error(f"[WhatsApp] Failed to send to {to_number}: {e}")
        return {"status": "error", "message": str(e)}


def send_demand_whatsapp(distributor_id: str, to_number: str, recommendations: list) -> dict:
    
    Sends the demand collection message to a distributor via WhatsApp.
    
    rec_lines = "\n".join(
        f"  ⭐ {r}" for r in recommendations[:5]
    ) if recommendations else "  (No specific recommendations this cycle)"

    body = f
Hello Distributor {distributor_id} 👋

Your monthly demand collection form is ready!

*Recommended products for this cycle:*
{rec_lines}

Please reply with your quantities in this format:
PRODUCT NAME - QUANTITY

Example:
MALKIST CHEESE JUMBO PACK - 100
BENG BENG WAFER CHOCOLATE - 75

Or reply *EXCEL* to receive the Excel form as an attachment.

Thank you! 🙏
— Demand Planning Team
.strip()

    return send_whatsapp_message(to_number, body)
"""

"""
WhatsApp Service
Sends WhatsApp messages via the Twilio API.
"""

import os
import logging
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
FROM_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

TWILIO_API_URL = f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}/Messages.json"


def send_whatsapp_message(to: str, message: str) -> bool:
    """
    Send a WhatsApp message via Twilio.

    Args:
        to:      Recipient number in Twilio format, e.g. "whatsapp:+1234567890"
        message: Text body to send

    Returns:
        True on success, False on failure.
    """
    if not ACCOUNT_SID or not AUTH_TOKEN:
        logger.warning("[WhatsApp] Twilio credentials not set – message NOT sent.")
        logger.info(f"[WhatsApp] Would have sent to {to}:\n{message}")
        return False

    # Ensure recipient has the whatsapp: prefix
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"

    try:
        response = requests.post(
            TWILIO_API_URL,
            data={
                "From": FROM_NUMBER,
                "To": to,
                "Body": message,
            },
            auth=HTTPBasicAuth(ACCOUNT_SID, AUTH_TOKEN),
            timeout=15,
        )

        if response.status_code in (200, 201):
            sid = response.json().get("sid", "")
            logger.info(f"[WhatsApp] Message sent to {to} | SID: {sid}")
            return True
        else:
            logger.error(
                f"[WhatsApp] Send failed | Status: {response.status_code} | "
                f"Body: {response.text[:300]}"
            )
            return False

    except requests.exceptions.RequestException as exc:
        logger.error(f"[WhatsApp] Network error sending message: {exc}")
        return False
