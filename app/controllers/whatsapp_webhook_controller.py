import logging
import os
import requests

from fastapi import APIRouter, Form, Response

from app.services.whatsapp_service import send_whatsapp_message
from app.services.reply_parser_service import parse_reply

logging.basicConfig(level=logging.INFO)
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
    Body: str = Form(None),
    NumMedia: int = Form(0),
    MediaUrl0: str = Form(None),
    MediaContentType0: str = Form(None),
):

    sender = From or "unknown"
    body = Body or ""

    logger.info(f"[WhatsApp] Received from {sender}: {body}")

    # ---------------------------------------------------
    # EXCEL / MEDIA ATTACHMENT HANDLING
    # ---------------------------------------------------

    if NumMedia and NumMedia > 0 and MediaUrl0:

        logger.info(f"[WhatsApp] Attachment received from {sender}")

        try:

            os.makedirs("whatsapp_uploads", exist_ok=True)

            file_response = requests.get(MediaUrl0)

            file_name = f"whatsapp_uploads/demand_upload.xlsx"

            with open(file_name, "wb") as f:
                f.write(file_response.content)

            logger.info(f"[WhatsApp] File saved: {file_name}")

            response_text = (
                "✅ Excel attachment received successfully.\n\n"
                "Demand sheet uploaded for processing."
            )

        except Exception as e:

            logger.error(str(e))

            response_text = (
                "❌ Failed to process attachment."
            )

        send_whatsapp_message(
            sender,
            response_text
        )

        return Response(
            content="<?xml version='1.0'?><Response></Response>",
            media_type="text/xml"
        )

    # ---------------------------------------------------
    # PARSE DISTRIBUTOR MESSAGE
    # ---------------------------------------------------
    parsed = parse_reply(sender, body)

    logger.info(f"[WhatsApp] Parsed Output: {parsed}")

        # ---------------------------------------------------
    # SUCCESSFUL DEMAND PARSE
    # ---------------------------------------------------
    if parsed["items"]:

        distributor_text = (
            parsed["distributor_id"]
            if parsed["distributor_id"] != "UNKNOWN"
            else "Not Identified"
        )

        confidence_percent = int(parsed["confidence"] * 100)

        items_text = "\n".join(
            [
                f"• {item['sku_name'].title()} — {item['quantity']} units"
                for item in parsed["items"]
            ]
        )

        response_text = (
            f"✅ Demand Recorded Successfully\n\n"
            f"Distributor: {distributor_text}\n"
            f"Confidence: {confidence_percent}%\n\n"
            f"Products:\n"
            f"{items_text}"
        )

        # Low confidence warning
        if parsed["confidence"] < 0.75:

            response_text += (
                "\n\n⚠️ Low confidence parsing detected."
                "\nPlease verify product names."
            )

        # ---------------------------------------------------
    # NEGATIVE / INFORMATIONAL RESPONSES
    # ---------------------------------------------------
    elif parsed["reply_type"] in ["negative", "informational"]:

        response_text = (
    "✅ Acknowledged.\n\n"
    "No demand recorded for this cycle."
)

    # ---------------------------------------------------
    # NEEDS FOLLOWUP
    # ---------------------------------------------------
    elif parsed["needs_followup"]:

        response_text = (
            "⚠️ We couldn't confidently understand your demand.\n\n"
            "Please send using this format:\n\n"
            "PRODUCT NAME - QUANTITY\n\n"
            "Example:\n"
            "MALKIST CHEESE JUMBO PACK - 100\n"
            "BENG BENG WAFER - 50"
        )

    else:

        response_text = (
            "✅ Acknowledged.\n\n"
            "No demand recorded for this cycle."
        )

    # ---------------------------------------------------
    # SEND WHATSAPP RESPONSE
    # ---------------------------------------------------
    send_whatsapp_message(
        sender,
        response_text
    )

    # ---------------------------------------------------
    # TWILIO RESPONSE
    # ---------------------------------------------------
    return Response(
        content="<?xml version='1.0'?><Response></Response>",
        media_type="text/xml"
    )