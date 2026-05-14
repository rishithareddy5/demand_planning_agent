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


import os
import logging
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
FROM_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")


def send_whatsapp_message(to_number: str, body: str):

    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)

        message = client.messages.create(
            body=body,
            from_=FROM_NUMBER,
            to=to_number
        )

        logger.info(f"Message sent: {message.sid}")

        return {
            "status": "success",
            "sid": message.sid
        }

    except Exception as e:

        logger.error(str(e))

        return {
            "status": "error",
            "message": str(e)
        }
