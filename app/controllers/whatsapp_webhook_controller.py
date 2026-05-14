# app/controllers/whatsapp_webhook_controller.py
"""
import logging
from fastapi import APIRouter, Request, Response, Form
from app.services.whatsapp_service import send_whatsapp_message
from app.services import ReplyParserService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["WhatsApp"])

reply_parser = ReplyParserService()


@router.post("/whatsapp")
async def receive_whatsapp(
    request: Request,
    From: str = Form(None),      # Twilio sends form data, not JSON
    Body: str = Form(None),
    NumMedia: int = Form(0),
    MediaUrl0: str = Form(None),
    MediaContentType0: str = Form(None),
):
    
    Twilio WhatsApp webhook — receives incoming messages from distributors.
    Parses reply text using existing ReplyParserService.
    Routes into the same Temporal workflow as email replies.
    
    sender = From or "unknown"
    body   = Body or ""

    logger.info(f"[WhatsApp] Received from {sender}: {body[:80]}")

    # Check if they sent an Excel attachment
    if NumMedia and NumMedia > 0 and MediaUrl0:
        # Download the Excel, parse it the same way as email attachment
        logger.info(f"[WhatsApp] Excel attachment received from {sender}")
        response_text = "✅ Received your Excel! Processing your demand... We'll confirm shortly."
        send_whatsapp_message(sender, response_text)
        #TODO: Download MediaUrl0, save to /tmp, pass to AttachmentParserService
        return Response(content="<?xml version='1.0'?><Response></Response>",
                        media_type="text/xml")

    # Parse text reply using existing service
    parsed = reply_parser.execute(body)

    if parsed["parse_status"] == "PARSED":
        items_text = "\n".join(
            f"  • {item['product_name']}: {item['quantity']} units"
            for item in parsed["items"]
        )
        confirmation = (
            f"✅ Got it! Your demand has been recorded:\n\n"
            f"{items_text}\n\n"
            f"Distributor: {parsed.get('distributor_id', 'Detected automatically')}\n"
            f"We'll confirm your order shortly."
        )
        send_whatsapp_message(sender, confirmation)
    else:
        hint = (
            "⚠️ We couldn't read your reply. Please use this format:\n\n"
            "PRODUCT NAME - QUANTITY\n\n"
            "Example:\nMALKIST CHEESE JUMBO PACK - 100\nBENG BENG WAFER - 50"
        )
        send_whatsapp_message(sender, hint)

    # Return TwiML empty response (required by Twilio)
    return Response(
        content="<?xml version='1.0'?><Response></Response>",
        media_type="text/xml"
    )
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
    

import os

from fastapi import APIRouter, Form, Response

from app.services.whatsapp_service import send_whatsapp_message
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/webhook",
    tags=["WhatsApp"]
)


@router.get("/test")
async def test_whatsapp():

    return {
        "status": "working"
    }


@router.post("/whatsapp")
async def receive_whatsapp(
    From: str = Form(None),
    Body: str = Form(None)
):

    logger.info(f"Sender: {From}")
    logger.info(f"Message: {Body}")

    send_whatsapp_message(
        From,
        f"✅ Message received!\n\nYou said:\n{Body}"
    )

    return Response(
        content="<?xml version='1.0'?><Response></Response>",
        media_type="text/xml"
    )