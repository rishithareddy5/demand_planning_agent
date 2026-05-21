"""
Standalone Test Suite – Demand Ingestion System
No Docker, Temporal, or RedPanda required.

Run: python test_standalone.py
"""

import os
import sys
import logging

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class C:
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    RESET  = "\033[0m"
    BOLD   = "\033[1m"

def ok(msg):   print(f"  {C.GREEN}✓{C.RESET} {msg}")
def fail(msg): print(f"  {C.RED}✗{C.RESET} {msg}")
def warn(msg): print(f"  {C.YELLOW}⚠{C.RESET} {msg}")
def head(msg): print(f"\n{C.BOLD}{C.BLUE}{'='*55}{C.RESET}\n{C.BOLD}{msg}{C.RESET}")
def info(msg): print(f"  {C.BLUE}ℹ{C.RESET} {msg}")


# ─────────────────────────────────────────────────────────────
# Bootstrap: load SKU data from Excel if files exist.
# The real reply_parser_service uses rapidfuzz + sku_data,
# so SKU_MAP must be populated before match_sku works.
# ─────────────────────────────────────────────────────────────

head("SETUP: Loading SKU Data")

SKU_DATA_LOADED = False

try:
    from app.data.sku_data import load_sku_data, get_sku_names

    # Common locations your project might store the Excel files
    candidate_primary = [
        "db/simple_data/Primary_Sales.xlsx",
        "db/Primary_Sales.xlsx",
        "data/Primary_Sales.xlsx",
        "Primary_Sales.xlsx",
    ]
    candidate_recommended = [
        "db/simple_data/Recommended_Products.xlsx",
        "db/Recommended_Products.xlsx",
        "data/Recommended_Products.xlsx",
        "Recommended_Products.xlsx",
    ]

    primary_file     = next((f for f in candidate_primary if os.path.exists(f)), None)
    recommended_file = next((f for f in candidate_recommended if os.path.exists(f)), None)

    if primary_file:
        load_sku_data(primary_file, recommended_file)
        sku_count = len(get_sku_names())
        ok(f"SKU data loaded from '{primary_file}' — {sku_count} SKUs")
        if recommended_file:
            ok(f"Also loaded recommended products from '{recommended_file}'")
        SKU_DATA_LOADED = True
    else:
        warn("No SKU Excel file found. SKU matching tests will be skipped.")
        warn("Expected one of: " + ", ".join(candidate_primary))
        warn("Place Primary_Sales.xlsx in your project root or db/simple_data/ to enable.")

except Exception as exc:
    warn(f"SKU data load failed: {exc}")


# ─────────────────────────────────────────────────────────────
# TEST 1: Text Demand Parsing
# ─────────────────────────────────────────────────────────────

head("TEST 1: Text Demand Parsing")

try:
    from app.services.reply_parser_service import parse_reply

    # These cases test parsing logic only (not SKU matching),
    # so they work even without the Excel file loaded.
    structural_cases = [
        ("MALKIST CHEESE - 100",                              "demand",       True),
        ("BENG BENG WAFER - 50\nKOPIKO CAPPU EXTRA - 25",    "demand",       True),
        ("no demand this week",                               "negative",     False),
        ("",                                                  "unknown",      False),
        ("MALKIST CHEESE JUMBO PACK - 100\nBENG BENG - 50",  "demand",       True),
    ]

    for text, expected_type, expect_items in structural_cases:
        result = parse_reply("test@test.com", text)
        rtype  = result["reply_type"]
        items  = result["items"]
        has_items = len(items) > 0

        if rtype == expected_type and has_items == expect_items:
            ok(f'"{text[:45]}" → type={rtype}, items={len(items)}, conf={result["confidence"]}')
        else:
            fail(
                f'"{text[:45]}" → type={rtype} (expected {expected_type}), '
                f'items={len(items)} (expected has_items={expect_items})'
            )

except Exception as exc:
    fail(f"Text parsing module error: {exc}")


# ─────────────────────────────────────────────────────────────
# TEST 2: SKU Fuzzy Matching
# ─────────────────────────────────────────────────────────────

head("TEST 2: SKU Fuzzy Matching")

if not SKU_DATA_LOADED:
    warn("Skipping — SKU Excel not found. Load Primary_Sales.xlsx to enable this test.")
else:
    try:
        from app.services.reply_parser_service import match_sku
        from app.data.sku_data import get_sku_names

        sku_names = get_sku_names()
        info(f"Testing against {len(sku_names)} loaded SKUs")

        # Use the first 3 real SKU names from your catalogue for positive tests
        sample_skus = sku_names[:3]

        for sku_name in sample_skus:
            # Use the exact name — should always match
            sku_id, matched_name, score = match_sku(sku_name, min_score=75)
            if sku_id:
                ok(f'"{sku_name}" → {sku_id} (score {score})')
            else:
                fail(f'"{sku_name}" → no match (score {score}) — check rapidfuzz install')

        # Negative test — should never match
        sku_id, _, score = match_sku("xyzzy unknown product 999", min_score=75)
        if not sku_id:
            ok('"xyzzy unknown product 999" → correctly no match')
        else:
            fail(f'"xyzzy unknown product 999" → wrongly matched {sku_id}')

    except Exception as exc:
        fail(f"match_sku error: {exc}")


# ─────────────────────────────────────────────────────────────
# TEST 3: Excel Column Detection
# ─────────────────────────────────────────────────────────────

head("TEST 3: Excel Column Detection & Parsing")

try:
    import pandas as pd
    from app.controllers.whatsapp_webhook_controller_v3 import _detect_excel_columns
    from app.services.reply_parser_service import match_sku as _ms

    df = pd.DataFrame({
        "sku_name":        ["Malkist Cheese", "Beng Beng Wafer", "Kopiko Cappu Extra"],
        "sku_description": ["MALKIST 48PCS",  "BENG BENG 22GM",  "KOPIKO 12X"],
        "Quantity":        [100, 50, 25],
    })

    product_col, qty_col = _detect_excel_columns(df)

    if product_col and qty_col:
        ok(f"Detected product_col='{product_col}', qty_col='{qty_col}'")
    else:
        fail(f"Column detection failed: product_col={product_col}, qty_col={qty_col}")

    items = []
    for _, row in df.iterrows():
        name  = str(row[product_col]).strip()
        qty   = int(row[qty_col])
        sku_id, sku_name, score = _ms(name, min_score=50)
        display = (sku_name or name).title()
        items.append({"sku_name": display, "quantity": qty})

    if len(items) == 3:
        ok(f"Parsed {len(items)} rows from synthetic Excel")
        for it in items:
            ok(f'  {it["sku_name"]} — {it["quantity"]} units')
    else:
        fail(f"Expected 3 rows, got {len(items)}")

except Exception as exc:
    fail(f"Excel test error: {exc}")


# ─────────────────────────────────────────────────────────────
# TEST 4: OCR Service
# ─────────────────────────────────────────────────────────────

head("TEST 4: OCR Service")

try:
    from app.services.ocr_service import (
        get_ocr_service, ImagePreprocessor, TableParser,
        OCREngine, check_dependencies,
    )
    ok("ocr_service module imports correctly")
    ok("ImagePreprocessor, TableParser, OCREngine all present")

    deps = check_dependencies()
    if deps.get("paddleocr"):
        ok("PaddleOCR available")
    else:
        warn("PaddleOCR NOT installed — run: pip install paddleocr paddlepaddle")
    if deps.get("easyocr"):
        ok("EasyOCR available (fallback engine)")
    else:
        warn("EasyOCR not installed (optional fallback) — run: pip install easyocr")
    if deps.get("pillow"):
        ok("Pillow available")
    else:
        fail("Pillow NOT installed — run: pip install Pillow")

except Exception as exc:
    fail(f"OCR service import error: {exc}")


# ─────────────────────────────────────────────────────────────
# TEST 5: Audio Service
# ─────────────────────────────────────────────────────────────

head("TEST 5: Audio Service")

try:
    from app.services.audio_service import check_dependencies as audio_deps
    deps = audio_deps()
    if deps["whisper"]:
        ok("Whisper installed")
    else:
        warn("Whisper NOT installed (audio disabled) — run: pip install openai-whisper")
    if deps["ffmpeg"]:
        ok("ffmpeg available")
    else:
        warn("ffmpeg NOT found — audio conversion may fail")
except Exception as exc:
    fail(f"Audio service error: {exc}")


# ─────────────────────────────────────────────────────────────
# TEST 6: WhatsApp Service
# ─────────────────────────────────────────────────────────────

head("TEST 6: WhatsApp Service")

try:
    from app.services.whatsapp_service import send_whatsapp_message
    ok("whatsapp_service imports correctly")
    ok("send_whatsapp_message callable (Twilio creds from .env at runtime)")
except Exception as exc:
    fail(f"WhatsApp service error: {exc}")


# ─────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────

print(f"\n{C.BOLD}{'='*55}")
print("Done.")
if not SKU_DATA_LOADED:
    print("NOTE: Put Primary_Sales.xlsx in project root to enable SKU match tests.")
print(f"{'='*55}{C.RESET}\n")
