"""
WhatsApp Webhook Controller v3 - Complete Multimodal Support
Handles: Text | Excel | Images (OCR) | Audio (Whisper)
Standalone - no Temporal/RedPanda dependencies
"""

import logging
import os
import requests
import pandas as pd

from fastapi import APIRouter, Form, Response

from app.services.whatsapp_service import send_whatsapp_message
from app.services.reply_parser_service import (
    parse_reply,
    calculate_confidence,
    match_sku
)
from app.services.attachment_parser_service import parse_excel_file
from app.services.ocr_service import get_ocr_service

# Optional: Audio service (only if installed)
try:
    from app.services.audio_service import get_audio_service
    AUDIO_ENABLED = True
except ImportError:
    AUDIO_ENABLED = False
    logging.warning("[WhatsApp] Audio service not available (install openai-whisper)")

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
    """Health check endpoint"""
    return {
        "status": "working",
        "service": "whatsapp_webhook_v3",
        "features": {
            "text": True,
            "excel": True,
            "ocr": True,
            "audio": AUDIO_ENABLED
        }
    }


@router.post("/whatsapp")
async def receive_whatsapp(
    From: str = Form(None),
    Body: str = Form(None),
    NumMedia: int = Form(0),
    MediaUrl0: str = Form(None),
    MediaContentType0: str = Form(None),
):
    """
    Main WhatsApp webhook endpoint
    Routes to: text | excel | image | audio handlers
    """
    
    sender = From or "unknown"
    body = Body or ""

    logger.info(f"[WhatsApp] Message from {sender}")
    logger.info(f"[WhatsApp] Body: {body[:100]}")
    logger.info(f"[WhatsApp] Media: {NumMedia}, Type: {MediaContentType0}")

    # ===================================================================
    # MEDIA ROUTING
    # ===================================================================
    
    if NumMedia and NumMedia > 0 and MediaUrl0:
        
        # Download media
        try:
            os.makedirs("whatsapp_uploads", exist_ok=True)
            
            file_response = requests.get(
                MediaUrl0,
                auth=(ACCOUNT_SID, AUTH_TOKEN),
                timeout=30
            )
            
            if file_response.status_code != 200:
                logger.error(f"[WhatsApp] Download failed: {file_response.status_code}")
                send_whatsapp_message(sender, "❌ Failed to download file.")
                return _twilio_empty_response()
            
            # Route by content type
            content_type = MediaContentType0 or ""
            
            # AUDIO
            if content_type.startswith("audio/"):
                return await _handle_audio(sender, file_response.content, content_type)
            
            # IMAGE
            elif content_type.startswith("image/"):
                return await _handle_image_ocr(sender, file_response.content)
            
            # EXCEL
            elif "spreadsheet" in content_type or content_type in [
                "application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ]:
                return await _handle_excel(sender, file_response.content)
            
            # UNKNOWN
            else:
                logger.warning(f"[WhatsApp] Unsupported type: {content_type}")
                send_whatsapp_message(
                    sender,
                    "⚠️ Unsupported file type.\n\n"
                    "Supported formats:\n"
                    "• Text messages\n"
                    "• Images (JPG, PNG)\n"
                    "• Excel (.xlsx)\n"
                    "• Voice messages"
                )
                return _twilio_empty_response()
                
        except Exception as e:
            logger.error(f"[WhatsApp] Media error: {e}", exc_info=True)
            send_whatsapp_message(sender, "❌ Error processing file.")
            return _twilio_empty_response()

    # ===================================================================
    # TEXT MESSAGE
    # ===================================================================
    
    return await _handle_text_message(sender, body)


# ===================================================================
# HANDLER: AUDIO TRANSCRIPTION
# ===================================================================

async def _handle_audio(sender: str, audio_data: bytes, content_type: str) -> Response:
    """Handle audio/voice message transcription"""
    
    if not AUDIO_ENABLED:
        send_whatsapp_message(
            sender,
            "⚠️ Audio transcription not available.\n"
            "Please send text or image instead."
        )
        return _twilio_empty_response()
    
    try:
        logger.info(f"[WhatsApp] Processing audio: {content_type}")
        
        # Determine file extension
        ext_map = {
            "audio/ogg": "ogg",
            "audio/mpeg": "mp3",
            "audio/mp4": "m4a",
            "audio/amr": "amr",
            "audio/wav": "wav"
        }
        ext = ext_map.get(content_type, "ogg")
        filename = f"voice_message.{ext}"
        
        # Transcribe
        audio_service = get_audio_service(model_size="base")
        result = audio_service.transcribe_whatsapp_voice(audio_data, filename)
        
        logger.info(f"[Audio] Transcription: {result['success']}")
        logger.info(f"[Audio] Text: {result.get('text', '')[:100]}")
        
        if not result['success']:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"[Audio] Failed: {error_msg}")
            
            send_whatsapp_message(
                sender,
                "⚠️ Could not transcribe audio.\n"
                "Please try:\n"
                "• Speaking clearly\n"
                "• Reducing background noise\n"
                "• Sending text instead"
            )
            return _twilio_empty_response()
        
        # Got transcription - parse as text
        transcribed_text = result['text']
        language = result.get('language', 'unknown')
        confidence = result.get('confidence', 0.0)
        
        logger.info(f"[Audio] Transcribed ({language}): {transcribed_text}")
        
        # Parse the transcribed text for demand
        parsed = parse_reply(sender, transcribed_text)
        
        # Build response
        if parsed["items"]:
            items_text = "\n".join([
                f"• {item['sku_name'].title()} — {item['quantity']} units"
                for item in parsed["items"]
            ])
            
            response_text = (
                f"🎤 Voice Message Transcribed\n\n"
                f"Language: {language.upper()}\n"
                f"Confidence: {int(confidence * 100)}%\n\n"
                f"You said:\n\"{transcribed_text}\"\n\n"
                f"Parsed Demand:\n{items_text}"
            )
            
            if parsed["confidence"] < 0.75:
                response_text += "\n\n⚠️ Low confidence. Please verify."
        
        else:
            response_text = (
                f"🎤 Voice Transcribed:\n\"{transcribed_text}\"\n\n"
                f"⚠️ Could not parse demand.\n"
                f"Please use format: PRODUCT - QUANTITY"
            )
        
        send_whatsapp_message(sender, response_text)
        return _twilio_empty_response()
        
    except Exception as e:
        logger.error(f"[Audio] Handler error: {e}", exc_info=True)
        send_whatsapp_message(sender, "❌ Audio processing failed.")
        return _twilio_empty_response()


# ===================================================================
# HANDLER: IMAGE OCR
# ===================================================================

async def _handle_image_ocr(sender: str, image_data: bytes) -> Response:
    """Handle image OCR demand extraction"""
    try:
        # Save image
        image_path = "whatsapp_uploads/demand_image.jpg"
        with open(image_path, "wb") as f:
            f.write(image_data)
        
        logger.info(f"[WhatsApp] Image saved: {image_path}")
        
        # Run OCR
        ocr_service = get_ocr_service()
        result = ocr_service.extract_demand_from_image(image_path, preprocess=True)
        
        logger.info(f"[OCR] Success: {result['success']}, Rows: {len(result['rows'])}")
        
        if not result['success']:
            send_whatsapp_message(
                sender,
                "⚠️ Could not read image.\n\n"
                "Tips:\n"
                "• Good lighting\n"
                "• Clear focus\n"
                "• No shadows/glare"
            )
            return _twilio_empty_response()
        
        # Match SKUs
        matched_items = []
        
        for row in result['rows']:
            if row.get('sku_id'):
                matched_items.append({
                    'sku_id': row['sku_id'],
                    'sku_name': row.get('sku_name', row['sku_id']),
                    'quantity': row['quantity'],
                    'confidence': row['confidence'],
                    'source': 'ocr_image'
                })
            elif row.get('sku_name'):
                sku_id, sku_name, match_score = match_sku(
                    f"{row['sku_name']} {row.get('description', '')}",
                    min_score=70
                )
                
                if sku_id:
                    matched_items.append({
                        'sku_id': sku_id,
                        'sku_name': sku_name or row['sku_name'],
                        'quantity': row['quantity'],
                        'confidence': row['confidence'] * (match_score / 100),
                        'match_score': match_score
                    })
        
        # Build response
        if matched_items:
            avg_confidence = sum(i['confidence'] for i in matched_items) / len(matched_items)
            
            items_text = "\n".join([
                f"• {item['sku_name'].title()} — {item['quantity']} units"
                for item in matched_items
            ])
            
            emoji = "✅" if avg_confidence >= 0.75 else "⚠️"
            
            response_text = (
                f"{emoji} Image Demand Parsed\n\n"
                f"Confidence: {int(avg_confidence * 100)}%\n"
                f"Products: {len(matched_items)}\n\n"
                f"{items_text}"
            )
            
            if avg_confidence < 0.75:
                response_text += "\n\n⚠️ Please verify quantities."
        
        else:
            response_text = (
                "⚠️ Could not extract demand.\n\n"
                f"Detected text:\n{result['raw_ocr_text'][:200]}"
            )
        
        send_whatsapp_message(sender, response_text)
        return _twilio_empty_response()
        
    except Exception as e:
        logger.error(f"[OCR] Error: {e}", exc_info=True)
        send_whatsapp_message(sender, "❌ Image processing failed.")
        return _twilio_empty_response()


# ===================================================================
# HANDLER: EXCEL
# ===================================================================
def _extract_product_name(item: dict) -> str:
    """
    Extract clean product name from parsed item
    """

    # Best case
    if item.get("sku_name"):
        return item["sku_name"].title()

    raw = item.get("matched_text", "")

    if not raw:
        return "Unknown Product"

    # Split before duplicate SKU section starts
    if "SKU" in raw:
        raw = raw.split("SKU")[0]

    # Remove trailing quantity
    parts = raw.rsplit("-", 1)

    if len(parts) > 1:
        raw = parts[0]

    # Clean spacing
    raw = " ".join(raw.split())

    return raw.title()

async def _handle_excel(sender: str, file_data: bytes) -> Response:
    """Handle Excel attachment parsing"""
    try:
        file_path = "whatsapp_uploads/demand_upload.xlsx"
        with open(file_path, "wb") as f:
            f.write(file_data)
        
        logger.info(f"[Excel] File saved: {file_path}")
        
        df = pd.read_excel(file_path)
        product_col, qty_col = _detect_columns(df)
        
        parsed_lines = []
        
        if product_col and qty_col:
            for _, row in df.iterrows():
                try:
                    product = str(row[product_col]).strip()
                    quantity = row[qty_col]
                    
                    if pd.isna(product) or pd.isna(quantity):
                        continue
                    
                    row_context = " ".join([
                        str(v) for v in row.values if pd.notna(v)
                    ])
                    
                    parsed_lines.append(f"{product} - {quantity} {row_context}")
                except:
                    continue
        else:
            for _, row in df.iterrows():
                row_text = " ".join([str(v) for v in row.values if pd.notna(v)])
                if row_text.strip():
                    parsed_lines.append(row_text)
        
        combined_text = "\n".join(parsed_lines)
        parsed = parse_reply(sender, combined_text)
        logger.info(f"[Excel DEBUG] Parsed items: {parsed['items']}")
        
        if parsed["items"]:
            confidence = calculate_confidence("UNKNOWN", parsed["items"], "demand")
            
            items_text = "\n".join([
            f"• {_extract_product_name(item)} — {item['quantity']} units"
            for item in parsed["items"]
        ])
            
            emoji = "✅" if confidence >= 0.75 else "⚠️"
            
            response_text = (
                f"{emoji} Excel Parsed\n\n"
                f"Confidence: {int(confidence * 100)}%\n"
                f"Products: {len(parsed['items'])}\n\n"
                f"{items_text}"
            )
        else:
            response_text = "⚠️ Could not extract demand from Excel."
        
        send_whatsapp_message(sender, response_text)
        return _twilio_empty_response()
        
    except Exception as e:
        logger.error(f"[Excel] Error: {e}", exc_info=True)
        send_whatsapp_message(sender, "❌ Excel processing failed.")
        return _twilio_empty_response()


# ===================================================================
# HANDLER: TEXT MESSAGE
# ===================================================================

async def _handle_text_message(sender: str, body: str) -> Response:
    """Handle plain text demand messages"""
    
    parsed = parse_reply(sender, body)
    logger.info(f"[TEXT DEBUG] {parsed}")
    
    logger.info(f"[Text] Parsed: {len(parsed.get('items', []))} items")
    
    if parsed["items"]:
        confidence_percent = int(parsed["confidence"] * 100)
        
        items_text = "\n".join([
            f"• {_extract_product_name(item)} — {item['quantity']} units"
            for item in parsed["items"]
        ])
        
        emoji = "✅" if parsed["confidence"] >= 0.75 else "⚠️"
        
        response_text = (
            f"{emoji} Demand Recorded\n\n"
            f"Confidence: {confidence_percent}%\n\n"
            f"{items_text}"
        )
        
        if parsed["confidence"] < 0.75:
            response_text += "\n\n⚠️ Low confidence. Please verify."
    
    elif parsed["reply_type"] in ["negative", "informational"]:
        response_text = "✅ Acknowledged. No demand recorded."
    
    elif parsed["needs_followup"]:
        response_text = (
            "⚠️ Couldn't understand demand.\n\n"
            "Format:\nPRODUCT - QUANTITY\n\n"
            "Example:\nMALKIST CHEESE - 100"
        )
    
    else:
        response_text = "✅ Acknowledged."
    
    send_whatsapp_message(sender, response_text)
    return _twilio_empty_response()


def _clean_product_name(item: dict) -> str:
    """
    Clean product display name for WhatsApp responses
    """

    # Best case: real sku_name exists
    if item.get("sku_name"):
        return item["sku_name"]

    raw = item.get("matched_text", "")

    if not raw:
        return "Unknown Product"

    # Remove quantity tail
    raw = raw.split("|")[0]

    # Remove duplicate SKU codes like SKU01
    words = raw.split()

    cleaned = []

    for word in words:

        # Skip SKU codes
        if word.upper().startswith("SKU"):
            continue

        # Skip pure numbers
        if word.isdigit():
            continue

        cleaned.append(word)

    # Limit overly long responses
    result = " ".join(cleaned[:8]).strip()

    return result or "Unknown Product"

# ===================================================================
# UTILITIES
# ===================================================================

def _detect_columns(df: pd.DataFrame) -> tuple:
    """
    Detect best product + quantity columns
    Priority:
    sku_name > product_name > description
    """

    normalized = {
        col.lower().strip(): col
        for col in df.columns
    }

    product_col = None
    qty_col = None

    # PRIORITY 1 — sku_name
    for key, original in normalized.items():
        if key == "sku_name":
            product_col = original
            break

    # PRIORITY 2 — product/name/item columns
    if not product_col:
        for key, original in normalized.items():
            if any(w in key for w in ["product", "name", "item"]):
                product_col = original
                break

    # PRIORITY 3 — description fallback
    if not product_col:
        for key, original in normalized.items():
            if "description" in key:
                product_col = original
                break

    # Quantity column
    for key, original in normalized.items():
        if any(w in key for w in ["qty", "quantity", "demand", "units"]):
            qty_col = original
            break

    return product_col, qty_col


def _twilio_empty_response() -> Response:
    """Return empty TwiML response"""
    return Response(
        content="<?xml version='1.0'?><Response></Response>",
        media_type="text/xml"
    )
