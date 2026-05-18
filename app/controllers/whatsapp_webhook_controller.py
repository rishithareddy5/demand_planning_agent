import logging
import os
import requests
import pandas as pd

from app.services.reply_parser_service import (
    parse_demand_lines,
    calculate_confidence
)

from fastapi import APIRouter, Form, Response
from paddleocr import PaddleOCR
from app.services.whatsapp_service import send_whatsapp_message
from app.services.reply_parser_service import parse_reply
from PIL import Image, ImageEnhance

ocr = PaddleOCR(
    use_angle_cls=True,  #  ocr instance
    lang='en',
    enable_mkldnn=False
)

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

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

            file_response = requests.get(
                MediaUrl0,
                auth=(ACCOUNT_SID, AUTH_TOKEN)
            )

            file_name = f"whatsapp_uploads/demand_upload.xlsx"

            with open(file_name, "wb") as f:
                f.write(file_response.content)

            logger.info(f"[WhatsApp] File saved: {file_name}")

        
        # ---------------------------------------------------
        # IMAGE FILES
        # ---------------------------------------------------
            if MediaContentType0 and MediaContentType0.startswith("image/"):

                logger.info("[WhatsApp] Image received")

                image_path = "whatsapp_uploads/demand_image.jpg"

                with open(image_path, "wb") as f:
                    f.write(file_response.content)

                logger.info(f"[WhatsApp] Image saved: {image_path}")


                # ----------------------------------------
                # IMAGE PREPROCESSING
                # ----------------------------------------

                image = Image.open(image_path)

                # Upscale image
                image = image.resize(
                    (image.width * 2, image.height * 2)
                )

                # Increase sharpness
                sharpness = ImageEnhance.Sharpness(image)
                image = sharpness.enhance(2.5)

                # Increase contrast
                contrast = ImageEnhance.Contrast(image)
                image = contrast.enhance(1.8)

                processed_image_path = (
                    "whatsapp_uploads/processed_image.jpg"
                )

                image.save(processed_image_path)

                logger.info(
                    f"[WhatsApp] Processed image saved: "
                    f"{processed_image_path}"
                )

                # ----------------------------------------
                # OCR USING PADDLEOCR
                # ----------------------------------------
                result = ocr.predict(processed_image_path)
                texts = result[0]["rec_texts"]
                boxes = result[0]["rec_boxes"]

                for text, box in zip(texts, boxes):

                    print("TEXT:", text)
                    print("BOX:", box)
                    print("--------")

                extracted_lines = result[0]["rec_texts"]

                extracted_text = "\n".join(extracted_lines)

                logger.info(
                    f"[WhatsApp] OCR Extracted Text:\n{extracted_text}"
                )

                # ----------------------------------------
                # STRUCTURED OCR TABLE PARSING
                # ----------------------------------------

                texts = result[0]["rec_texts"]

                products = []

                i = 0

                while i < len(texts):

                    current_text = texts[i].strip()

                    if (
                            current_text.upper().startswith("SKU")
                            and current_text.upper() not in [
                                "SKU_ID",
                                "SKU NAME",
                                "SKU_DESCRIPTION",
                                "SKU DESCRIPTION"
                            ]
                        ):

                        try:

                            sku_id = current_text

                            sku_name = texts[i + 1].strip()

                            quantity_text = texts[i + 3].strip()

                            quantity = int(
                                ''.join(
                                    filter(str.isdigit, quantity_text)
                                )
                            )

                            products.append({
                                "sku_id": sku_id,
                                "sku_name": sku_name,
                                "quantity": quantity
                            })

                            i += 4

                        except Exception as e:

                            logger.error(f"OCR row parse failed: {e}")

                            i += 1

                    else:

                        i += 1

                logger.info(f"[WhatsApp] Structured OCR Products: {products}")

                if products:

                    items_text = "\n".join([
                        f"• {item['sku_name'].title()} — "
                        f"{item['quantity']} units"
                        for item in products
                    ])

                    response_text = (
                        f"🖼️ Image Demand Parsed Successfully\n\n"
                        f"{items_text}"
                    )

                else:

                    response_text = (
                        "⚠️ Could not parse image rows."
                    )

                send_whatsapp_message(
                    sender,
                    response_text
                )

                return Response(
                    content="<?xml version='1.0'?><Response></Response>",
                    media_type="text/xml"
                )
                
            # ----------------------------------------
            # READ EXCEL
            # ----------------------------------------
            df = pd.read_excel(file_name)

            product_col, qty_col = detect_columns(df)

            parsed_lines = []

            # ---------------------------------------------------
            # COLUMN-AWARE PARSING
            # ---------------------------------------------------
            if product_col and qty_col:

                logger.info(
                    f"[WhatsApp] Detected columns: "
                    f"{product_col}, {qty_col}"
                )

                for _, row in df.iterrows():

                    try:

                        product = str(row[product_col]).strip()
                        quantity = row[qty_col]

                        if pd.isna(product) or pd.isna(quantity):
                            continue

                        # FULL ROW CONTEXT
                        row_context = " ".join(
                            [
                                str(value)
                                for value in row.values
                                if pd.notna(value)
                            ]
                        )

                        # HYBRID LINE
                        line = f"{product} - {quantity} {row_context}"

                        parsed_lines.append(line)

                    except Exception:
                        continue

            # ---------------------------------------------------
            # FALLBACK: FULL ROW PARSING
            # ---------------------------------------------------
            else:

                logger.warning(
                    "[WhatsApp] Could not detect columns. "
                    "Using full-row fallback parsing."
                )

                for _, row in df.iterrows():

                    row_text = " ".join(
                        [
                            str(value)
                            for value in row.values
                            if pd.notna(value)
                        ]
                    )

                    if row_text.strip():
                        parsed_lines.append(row_text)

            combined_text = "\n".join(parsed_lines)

            parsed = parse_reply(sender, combined_text)

            # ----------------------------------------
            # AGGREGATE RESULTS
            # ----------------------------------------
            if parsed["items"]:

                confidence = calculate_confidence(
                    distributor_id="UNKNOWN",
                    matched_items=parsed["items"],
                    reply_type="demand"
                )

                items_text = "\n".join([
                    f"• {item['sku_name'].title()} — {item['quantity']} units"
                    for item in parsed["items"]
                ])

                response_text = (
                    f"✅ Excel Demand Parsed Successfully\n\n"
                    f"Confidence: {int(confidence * 100)}%\n\n"
                    f"Products:\n"
                    f"{items_text}"
                )

            else:

                response_text = (
                    "⚠️ Could not extract demand items from Excel."
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

def detect_columns(df):

    normalized = {
        col.lower().strip(): col
        for col in df.columns
    }

    product_col = None
    qty_col = None

    product_keywords = [
        "product",
        "sku",
        "item",
        "description",
        "product name"
    ]

    qty_keywords = [
        "qty",
        "quantity",
        "demand",
        "units"
    ]

    for key, original in normalized.items():

        if any(word in key for word in product_keywords):
            product_col = original

        if any(word in key for word in qty_keywords):
            qty_col = original

    return product_col, qty_col