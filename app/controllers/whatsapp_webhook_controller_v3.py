"""
WhatsApp Webhook Controller v3  –  Multimodal WhatsApp ingestion
Handles: Text | Excel | Images (OCR) | Audio (Whisper)

NOTE: Purely a WhatsApp addition. Email flow is untouched.
"""

import logging
import os
import re

import pandas as pd
import requests
from fastapi import APIRouter, Form, Response

from app.services.whatsapp_service import send_whatsapp_message
from app.services.reply_parser_service import (
    parse_reply,
    calculate_confidence,
    match_sku,
)
from app.services.ocr_service import get_ocr_service

try:
    from app.services.audio_service import get_audio_service
    AUDIO_ENABLED = True
except ImportError:
    AUDIO_ENABLED = False
    logging.warning("[WhatsApp] Audio service not available – install openai-whisper")

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["WhatsApp"])


# ============================================================
# Health check
# ============================================================

@router.get("/test")
async def test_whatsapp():
    return {
        "status": "working",
        "service": "whatsapp_webhook_v3",
        "features": {"text": True, "excel": True, "ocr": True, "audio": AUDIO_ENABLED},
    }


# ============================================================
# Main entry point
# ============================================================

@router.post("/whatsapp")
async def receive_whatsapp(
    From: str = Form(None),
    Body: str = Form(None),
    NumMedia: int = Form(0),
    MediaUrl0: str = Form(None),
    MediaContentType0: str = Form(None),
):
    sender = From or "unknown"
    body   = Body or ""

    logger.info(f"[WhatsApp] From={sender} | NumMedia={NumMedia} | Body={body[:80]}")

    if NumMedia and NumMedia > 0 and MediaUrl0:
        try:
            os.makedirs("whatsapp_uploads", exist_ok=True)
            auth      = (ACCOUNT_SID, AUTH_TOKEN) if ACCOUNT_SID and AUTH_TOKEN else None
            file_resp = requests.get(MediaUrl0, auth=auth, timeout=30)

            if file_resp.status_code != 200:
                logger.error(f"[WhatsApp] Download failed: {file_resp.status_code}")
                send_whatsapp_message(sender, "❌ Failed to download file.")
                return _twiml_empty()

            ctype = (MediaContentType0 or "").lower()

            if ctype.startswith("audio/"):
                return await _handle_audio(sender, file_resp.content, ctype)
            if ctype.startswith("image/"):
                return await _handle_image_ocr(sender, file_resp.content)
            if "spreadsheet" in ctype or ctype in (
                "application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ):
                return await _handle_excel(sender, file_resp.content)

            send_whatsapp_message(
                sender,
                "⚠️ Unsupported file type.\n\nSupported: text, images (JPG/PNG), Excel (.xlsx), voice notes.",
            )
            return _twiml_empty()

        except Exception as exc:
            logger.error(f"[WhatsApp] Media error: {exc}", exc_info=True)
            send_whatsapp_message(sender, "❌ Error processing file.")
            return _twiml_empty()

    return await _handle_text(sender, body)


# ============================================================
# WhatsApp text sanitiser
# Handles all the messy ways distributors type demands
# ============================================================

def _sanitize_whatsapp_text(body: str) -> str:
    """
    Normalise WhatsApp message text before passing to parse_reply.

    Handles:
    - Em dash / en dash:  "Product — 100"  →  "Product - 100"
    - Numbered lists:     "1. MALKIST - 100\n2. BENG BENG - 50"  → two lines
    - Bullet lists:       "• MALKIST - 100"  →  "MALKIST - 100"
    - Trailing unit words: "MALKIST - 100 units"  →  "MALKIST - 100"
    - Comma/semicolon/slash separated on one line  →  split into lines
    - Duplicate product+description:
        "Kopiko Cappu Extra Kopiko Cappu 12X230X3.5Gr @ Extra - 25"
        → "Kopiko Cappu Extra - 25"
    """
    if not body:
        return body

    # 1. Normalise line separators
    text = body.replace("\r\n", "\n").replace("\r", "\n")

    # 2. Replace ALL dash variants with standard hyphen-minus
    #    em dash (—), en dash (–), figure dash (‒), horizontal bar (―)
    text = text.replace("\u2014", " - ")   # em dash  —
    text = text.replace("\u2013", " - ")   # en dash  –
    text = text.replace("\u2012", " - ")   # figure dash  ‒
    text = text.replace("\u2015", " - ")   # horizontal bar  ―

    # 3. Split comma/semicolon/slash separated items into lines
    #    only when both sides contain a digit (looks like a demand entry)
    lines_raw = text.splitlines()
    lines_out = []
    for line in lines_raw:
        parts = re.split(r"[,;/|]", line)
        if len(parts) > 1 and all(re.search(r"\d", p) for p in parts if p.strip()):
            lines_out.extend(parts)
        else:
            lines_out.append(line)

    # 4. Per-line cleanup
    cleaned = []
    for line in lines_out:
        line = line.strip()
        if not line:
            continue

        # Strip leading numbering / bullets:  "1. " "1) " "- " "* " "• "
        line = re.sub(r"^(\d+[\.\)]\s*|[-*•·]\s*)", "", line).strip()

        # Strip trailing unit words AFTER the quantity:
        # "MALKIST - 100 units" → "MALKIST - 100"
        # "MALKIST - 100 units pls confirm" → "MALKIST - 100"
        line = re.sub(
            r"(\d+)\s*(units?|pcs?|pieces?|boxes?|cartons?|packs?|cases?)[\s\w,;.]*$",
            r"\1",
            line,
            flags=re.IGNORECASE,
        ).strip()

        # Deduplicate repeated product+description before the dash-qty
        dash_qty = re.search(r"\s*-\s*(\d+)\s*$", line)
        if dash_qty:
            product_part = line[:dash_qty.start()].strip()
            qty_part     = dash_qty.group(0).strip()
            product_part = _deduplicate_product_name(product_part)
            line = f"{product_part} {qty_part}"

        if line:
            cleaned.append(line)

    return "\n".join(cleaned)


def _deduplicate_product_name(name: str) -> str:
    """
    Remove repeated sub-phrases from a product name.
    E.g. "Kopiko Cappu Extra Kopiko Cappu 12X230X3.5Gr @ Extra"
      →  "Kopiko Cappu Extra"
    Strategy: try to find the shortest prefix that fuzzy-matches a real SKU.
    Falls back to taking the first half if no match found.
    """
    words = name.split()
    if len(words) <= 4:
        return name   # short enough, no dedup needed

    # Try progressively longer prefixes and stop at first SKU match
    for length in range(2, len(words) // 2 + 2):
        candidate = " ".join(words[:length])
        sku_id, _, score = match_sku(candidate, min_score=75)
        if sku_id:
            return candidate

    # No match found — check for literal word repetition
    # "A B C A B D" → repeated "A B" prefix → return "A B C"
    half = len(words) // 2
    first_half  = words[:half]
    second_half = words[half:]
    overlap = 0
    for i in range(min(len(first_half), len(second_half))):
        if first_half[i].lower() == second_half[i].lower():
            overlap += 1
        else:
            break
    if overlap >= 2:
        return " ".join(words[:half + (len(words) - half - overlap)])

    return name   # can't deduplicate safely, return as-is


def _resolve_sku_id_in_text(body: str) -> str:
    """
    Replace bare SKU IDs with their real names so parse_reply can match them.
    E.g. "SKU01 - 10"  →  "Malkist Cheese 48 Pcs X 72 - 10"
    """
    from app.data.sku_data import get_sku_id_to_name

    sku_id_to_name = get_sku_id_to_name()
    if not sku_id_to_name:
        return body   # catalogue not loaded, pass through as-is

    def replace_sku(match):
        sku_code = match.group(0).upper()
        real_name = sku_id_to_name.get(sku_code)
        return real_name if real_name else sku_code

    return re.sub(r"\bSKU\d{1,3}\b", replace_sku, body, flags=re.IGNORECASE)


# ============================================================
# Handler: Text
# ============================================================

async def _handle_text(sender: str, body: str) -> Response:
    if not body.strip():
        send_whatsapp_message(
            sender,
            "⚠️ Couldn't understand demand.\n\nFormat:\nPRODUCT - QUANTITY\n\nExample:\nMALKIST CHEESE - 100",
        )
        return _twiml_empty()

    # Step 1 – resolve any bare SKU IDs to real names
    body = _resolve_sku_id_in_text(body)

    # Step 2 – sanitise WhatsApp formatting quirks
    body = _sanitize_whatsapp_text(body)

    logger.info(f"[Text] Sanitised body:\n{body}")

    # Step 3 – parse with existing service
    parsed = parse_reply(sender, body)

    logger.info(
        f"[Text] reply_type={parsed['reply_type']} "
        f"items={len(parsed['items'])} conf={parsed['confidence']}"
    )

    if parsed["items"]:
        emoji      = "✅" if parsed["confidence"] >= 0.75 else "⚠️"
        items_text = _format_items(parsed["items"])
        reply = (
            f"{emoji} Demand Recorded\n\n"
            f"Confidence: {int(parsed['confidence'] * 100)}%\n\n"
            f"{items_text}"
        )
        if parsed["confidence"] < 0.75:
            reply += "\n\n⚠️ Low confidence. Please verify."

    elif parsed["reply_type"] in ("negative", "informational"):
        reply = "✅ Acknowledged. No demand recorded."

    elif parsed["needs_followup"]:
        reply = (
            "⚠️ Couldn't understand demand.\n\n"
            "Format:\nPRODUCT - QUANTITY\n\nExample:\nMALKIST CHEESE - 100"
        )
    else:
        reply = "✅ Acknowledged."

    send_whatsapp_message(sender, reply)
    return _twiml_empty()


# ============================================================
# Handler: Audio
# ============================================================

async def _handle_audio(sender: str, audio_data: bytes, content_type: str) -> Response:
    if not AUDIO_ENABLED:
        send_whatsapp_message(sender, "⚠️ Audio transcription not available.\nPlease send text or image instead.")
        return _twiml_empty()

    try:
        ext_map = {
            "audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a",
            "audio/amr": "amr", "audio/wav": "wav",
        }
        ext       = ext_map.get(content_type, "ogg")
        audio_svc = get_audio_service(model_size="base")
        result    = audio_svc.transcribe_whatsapp_voice(audio_data, f"voice.{ext}")

        if not result["success"]:
            send_whatsapp_message(sender, "⚠️ Could not transcribe audio.\nPlease send text instead.")
            return _twiml_empty()

        transcribed = result["text"]
        language    = result.get("language", "unknown")

        # Run through the same sanitiser + parser
        clean_text  = _sanitize_whatsapp_text(_resolve_sku_id_in_text(transcribed))
        parsed      = parse_reply(sender, clean_text)

        if parsed["items"]:
            items_text = _format_items(parsed["items"])
            reply = (
                f"🎤 Voice Message Transcribed\n\n"
                f"Language: {language.upper()}\n"
                f"You said: \"{transcribed}\"\n\n"
                f"Parsed Demand:\n{items_text}"
            )
            if parsed["confidence"] < 0.75:
                reply += "\n\n⚠️ Low confidence. Please verify."
        else:
            reply = (
                f"🎤 Transcribed: \"{transcribed}\"\n\n"
                "⚠️ Could not parse demand.\nFormat: PRODUCT - QUANTITY"
            )

        send_whatsapp_message(sender, reply)

    except Exception as exc:
        logger.error(f"[Audio] Error: {exc}", exc_info=True)
        send_whatsapp_message(sender, "❌ Audio processing failed.")

    return _twiml_empty()


# ============================================================
# Handler: Image OCR
# ============================================================

async def _handle_image_ocr(sender: str, image_data: bytes) -> Response:
    try:
        image_path = "whatsapp_uploads/demand_image.jpg"
        with open(image_path, "wb") as fh:
            fh.write(image_data)

        ocr_svc = get_ocr_service()
        result  = ocr_svc.extract_demand_from_image(image_path, preprocess=True)

        logger.info(f"[OCR] success={result['success']}, rows={len(result['rows'])}")

        if not result["success"]:
            send_whatsapp_message(
                sender,
                "⚠️ Could not read image.\nTips: good lighting, clear focus, no glare.",
            )
            return _twiml_empty()

        matched_items = []
        for row in result["rows"]:
            raw_name = row.get("sku_name", "")
            qty      = row.get("quantity")
            if not raw_name or qty is None:
                continue

            sku_id, sku_name, score = match_sku(raw_name, min_score=55)
            matched_items.append({
                "sku_id":      sku_id or row.get("sku_id", ""),
                "sku_name":    sku_name or raw_name,
                "quantity":    qty,
                "match_score": score,
                "confidence":  row["confidence"],
            })

        if matched_items:
            avg_conf   = sum(r["confidence"] for r in matched_items) / len(matched_items)
            emoji      = "✅" if avg_conf >= 0.75 else "⚠️"
            items_text = _format_items(matched_items)
            reply = (
                f"{emoji} Image Demand Parsed\n\n"
                f"Confidence: {int(avg_conf * 100)}%\n"
                f"Products: {len(matched_items)}\n\n"
                f"{items_text}"
            )
            if avg_conf < 0.75:
                reply += "\n\n⚠️ Please verify quantities."
        else:
            preview = result["raw_ocr_text"][:200]
            reply   = f"⚠️ Could not extract demand.\n\nDetected text:\n{preview}"

        send_whatsapp_message(sender, reply)

    except Exception as exc:
        logger.error(f"[OCR] Error: {exc}", exc_info=True)
        send_whatsapp_message(sender, "❌ Image processing failed.")

    return _twiml_empty()


# ============================================================
# Handler: Excel
# ============================================================

async def _handle_excel(sender: str, file_data: bytes) -> Response:
    try:
        file_path = "whatsapp_uploads/demand_upload.xlsx"
        with open(file_path, "wb") as fh:
            fh.write(file_data)

        df = pd.read_excel(file_path)
        logger.info(f"[Excel] Columns: {df.columns.tolist()}")

        product_col, qty_col = _detect_excel_columns(df)
        logger.info(f"[Excel] product_col={product_col}, qty_col={qty_col}")

        items = []

        if product_col and qty_col:
            desc_col = _find_col(df, ["description", "sku_description", "sku description"])

            for _, row in df.iterrows():
                try:
                    raw_product = str(row[product_col]).strip()
                    raw_qty     = row[qty_col]

                    if not raw_product or raw_product.lower() in ("nan", "none", ""):
                        continue
                    if pd.isna(raw_qty):
                        continue

                    qty = int(float(str(raw_qty).strip()))
                    if qty <= 0:
                        continue

                    extra       = str(row[desc_col]).strip() if desc_col else ""
                    search_text = f"{raw_product} {extra}".strip()

                    sku_id, sku_name, score = match_sku(search_text, min_score=55)
                    display_name = (sku_name or raw_product).title()

                    items.append({
                        "sku_id":      sku_id or "",
                        "sku_name":    display_name,
                        "quantity":    qty,
                        "match_score": score,
                    })

                except Exception as row_exc:
                    logger.debug(f"[Excel] Row skip: {row_exc}")
                    continue
        else:
            lines  = []
            for _, row in df.iterrows():
                row_text = " ".join(str(v) for v in row.values if pd.notna(v))
                if row_text.strip():
                    lines.append(row_text)
            parsed = parse_reply(sender, "\n".join(lines))
            items  = parsed.get("items", [])

        logger.info(f"[Excel] {len(items)} items extracted")

        if items:
            confidence = calculate_confidence("UNKNOWN", items, "demand")
            emoji      = "✅" if confidence >= 0.75 else "⚠️"
            items_text = _format_items(items)
            reply = (
                f"{emoji} Excel Parsed\n\n"
                f"Confidence: {int(confidence * 100)}%\n"
                f"Products: {len(items)}\n\n"
                f"{items_text}"
            )
        else:
            reply = "⚠️ Could not extract demand from Excel."

        send_whatsapp_message(sender, reply)

    except Exception as exc:
        logger.error(f"[Excel] Error: {exc}", exc_info=True)
        send_whatsapp_message(sender, "❌ Excel processing failed.")

    return _twiml_empty()


# ============================================================
# Utilities
# ============================================================

def _format_items(items: list) -> str:
    lines = []
    for item in items:
        name = (item.get("sku_name") or item.get("matched_text") or "Unknown Product").title()
        qty  = item.get("quantity", 0)
        lines.append(f"• {name} — {qty} units")
    return "\n".join(lines)


def _detect_excel_columns(df: pd.DataFrame):
    normalized  = {col.lower().strip(): col for col in df.columns}
    product_col = qty_col = None

    for kw in ("sku_name", "sku name", "product name", "product", "name", "item", "description"):
        for key, original in normalized.items():
            if kw in key:
                product_col = original
                break
        if product_col:
            break

    for kw in ("qty", "quantity", "demand", "units", "order"):
        for key, original in normalized.items():
            if kw in key:
                qty_col = original
                break
        if qty_col:
            break

    return product_col, qty_col


def _find_col(df: pd.DataFrame, keywords: list):
    normalized = {col.lower().strip(): col for col in df.columns}
    for kw in keywords:
        for key, original in normalized.items():
            if kw in key:
                return original
    return None


def _twiml_empty() -> Response:
    return Response(
        content="<?xml version='1.0'?><Response></Response>",
        media_type="text/xml",
    )
