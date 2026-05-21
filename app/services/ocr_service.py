"""
Production-Grade OCR Service for Demand Planning
Merged version: original multi-engine architecture + improved parsing logic.

Engines supported: PaddleOCR (primary) → EasyOCR (fallback)
Features: advanced preprocessing, intelligent table detection,
          confidence scoring, fallback parsing.
"""

import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)


# ============================================================
# Enums & Dataclasses
# ============================================================

class OCREngine(Enum):
    PADDLEOCR = "paddleocr"
    EASYOCR   = "easyocr"
    TESSERACT = "tesseract"


@dataclass
class OCRResult:
    text:       str
    confidence: float
    bbox:       Optional[Tuple[int, int, int, int]] = None


@dataclass
class TableRow:
    sku_id:      Optional[str]
    sku_name:    Optional[str]
    description: Optional[str]
    quantity:    Optional[int]
    confidence:  float
    raw_text:    str


# ============================================================
# Image Preprocessor  (your original — fully intact)
# ============================================================

class ImagePreprocessor:
    """Advanced image preprocessing for OCR accuracy."""

    @staticmethod
    def preprocess(image_path: str, output_path: str) -> str:
        try:
            img = Image.open(image_path)
            if img.mode != "RGB":
                img = img.convert("RGB")

            target_width = 2000
            if img.width < target_width:
                scale    = target_width / img.width
                img      = img.resize((target_width, int(img.height * scale)), Image.Resampling.LANCZOS)

            img = img.filter(ImageFilter.MedianFilter(size=3))
            img = ImageEnhance.Sharpness(img).enhance(2.0)
            img = ImageEnhance.Contrast(img).enhance(1.5)
            img = img.convert("L")

            img_array = np.array(img)
            threshold = np.mean(img_array)
            img_array = np.where(img_array > threshold, 255, 0).astype(np.uint8)
            img       = Image.fromarray(img_array)

            img.save(output_path, quality=95)
            logger.info(f"[OCR] Preprocessed: {output_path}")
            return output_path

        except Exception as exc:
            logger.error(f"[OCR] Preprocessing failed: {exc}")
            return image_path


# ============================================================
# PaddleOCR Engine  (your original singleton)
# ============================================================

class PaddleOCREngine:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            try:
                from paddleocr import PaddleOCR
                cls._instance = PaddleOCR(
                    use_angle_cls=True, lang="en",
                    enable_mkldnn=False, use_gpu=False, show_log=False,
                )
                logger.info("[OCR] PaddleOCR initialized")
            except Exception as exc:
                logger.error(f"[OCR] PaddleOCR init failed: {exc}")
                cls._instance = None
        return cls._instance

    @classmethod
    def extract(cls, image_path: str) -> List[OCRResult]:
        ocr = cls.get_instance()
        if not ocr:
            return []
        try:
            result = ocr.ocr(image_path, cls=True)
            if not result or not result[0]:
                return []
            items = []
            for line in result[0]:
                bbox, (text, conf) = line[0], line[1]
                xs = [p[0] for p in bbox]; ys = [p[1] for p in bbox]
                items.append(OCRResult(
                    text=text, confidence=conf,
                    bbox=(int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))),
                ))
            items.sort(key=lambda x: x.bbox[1] if x.bbox else 0)
            return items
        except Exception as exc:
            logger.error(f"[OCR] PaddleOCR extraction failed: {exc}")
            return []


# ============================================================
# EasyOCR Engine  (your original fallback)
# ============================================================

class EasyOCREngine:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            try:
                import easyocr
                cls._instance = easyocr.Reader(["en"], gpu=False)
                logger.info("[OCR] EasyOCR initialized")
            except Exception as exc:
                logger.error(f"[OCR] EasyOCR init failed: {exc}")
                cls._instance = None
        return cls._instance

    @classmethod
    def extract(cls, image_path: str) -> List[OCRResult]:
        reader = cls.get_instance()
        if not reader:
            return []
        try:
            results = reader.readtext(image_path)
            items   = []
            for bbox, text, conf in results:
                xs = [p[0] for p in bbox]; ys = [p[1] for p in bbox]
                items.append(OCRResult(
                    text=text, confidence=conf,
                    bbox=(int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))),
                ))
            items.sort(key=lambda x: x.bbox[1] if x.bbox else 0)
            return items
        except Exception as exc:
            logger.error(f"[OCR] EasyOCR extraction failed: {exc}")
            return []


# ============================================================
# Table Parser  (your original structure + Claude's cleaner
#                row/qty/name extraction — no more i+1/i+3)
# ============================================================

_HEADER_WORDS = {
    "sku", "product", "item", "name", "qty", "quantity",
    "description", "no", "no.", "demand", "units", "pcs",
}
_SKU_ID_RE = re.compile(r"^SKU\d+$", re.IGNORECASE)


class TableParser:

    @staticmethod
    def detect_table_structure(ocr_results: List[OCRResult]) -> Dict[str, Any]:
        if not ocr_results:
            return {"has_table": False}

        rows = TableParser._group_into_rows(ocr_results)
        if len(rows) < 2:
            return {"has_table": False}

        first_row    = rows[0]
        header_texts = [r.text.lower().strip() for r in first_row]
        header_kws   = {"sku", "product", "name", "description", "qty", "quantity", "demand"}
        has_headers  = any(any(kw in h for kw in header_kws) for h in header_texts)
        col_pos      = sorted([r.bbox[0] for r in first_row if r.bbox])

        return {
            "has_table":        has_headers,
            "headers":          header_texts,
            "column_positions": col_pos,
            "rows":             rows[1:] if has_headers else rows,
        }

    @staticmethod
    def _group_into_rows(
        ocr_results: List[OCRResult], row_tolerance: int = 15
    ) -> List[List[OCRResult]]:
        if not ocr_results:
            return []

        rows        = []
        current_row = [ocr_results[0]]
        current_y   = ocr_results[0].bbox[1] if ocr_results[0].bbox else 0

        for result in ocr_results[1:]:
            result_y = result.bbox[1] if result.bbox else 0
            if abs(result_y - current_y) <= row_tolerance:
                current_row.append(result)
            else:
                current_row.sort(key=lambda x: x.bbox[0] if x.bbox else 0)
                rows.append(current_row)
                current_row = [result]
                current_y   = result_y

        current_row.sort(key=lambda x: x.bbox[0] if x.bbox else 0)
        rows.append(current_row)
        return rows

    @staticmethod
    def parse_demand_table(table_structure: Dict[str, Any]) -> List[TableRow]:
        if not table_structure.get("has_table"):
            return []
        parsed = []
        for row_results in table_structure.get("rows", []):
            row = TableParser._parse_single_row(row_results)
            if row and (row.sku_id or row.sku_name):
                parsed.append(row)
        return parsed

    @staticmethod
    def _parse_single_row(row_results: List[OCRResult]) -> Optional[TableRow]:
        """
        Improved single-row parser.
        FIX: uses rightmost valid integer as qty (not last number blindly),
             strips header words from product name,
             handles unit suffixes like 'pcs'/'units'.
        """
        if not row_results:
            return None

        raw_text = " ".join(r.text for r in row_results)
        avg_conf = sum(r.confidence for r in row_results) / len(row_results)
        texts    = [r.text.strip() for r in row_results]

        # 1. SKU ID
        sku_id = next(
            (t.upper().replace(" ", "") for t in texts if _SKU_ID_RE.match(t.strip())),
            None,
        )

        # 2. Quantity — rightmost pure integer in valid range
        quantity = None
        for t in reversed(texts):
            cleaned = re.sub(r"(?i)(pcs|units?|boxes?|cartons?|packs?)\s*$", "", t).strip()
            if re.match(r"^\d{1,6}$", cleaned):
                val = int(cleaned)
                if 0 < val < 100_000:
                    quantity = val
                    break

        if quantity is None:
            return None

        # 3. Product name — strip SKU ID, quantity token, header words
        qty_str    = str(quantity)
        name_parts = [
            t for t in texts
            if not (sku_id and t.upper().replace(" ", "") == sku_id)
            and not (re.match(r"^\d{1,6}$", t) and t == qty_str)
            and t.lower().strip() not in _HEADER_WORDS
        ]

        sku_name    = name_parts[0].strip() if name_parts else None
        description = " ".join(name_parts[1:]).strip() if len(name_parts) > 1 else None

        if not (sku_id or sku_name):
            return None

        return TableRow(
            sku_id=sku_id, sku_name=sku_name, description=description,
            quantity=quantity, confidence=round(avg_conf, 3), raw_text=raw_text,
        )


# ============================================================
# OCR Service  (your original class + improved fallback)
# ============================================================

class OCRService:

    def __init__(self, preferred_engine: OCREngine = OCREngine.PADDLEOCR):
        self.preferred_engine = preferred_engine
        self.preprocessor     = ImagePreprocessor()

    def extract_demand_from_image(
        self, image_path: str, preprocess: bool = True
    ) -> Dict[str, Any]:
        try:
            os.makedirs("whatsapp_uploads", exist_ok=True)

            processed_path = image_path
            if preprocess:
                processed_path = self.preprocessor.preprocess(
                    image_path, "whatsapp_uploads/processed_image.jpg"
                )

            ocr_results = self._run_ocr_with_fallback(processed_path)
            if not ocr_results:
                return self._fail("OCR extraction returned no results")

            table_structure = TableParser.detect_table_structure(ocr_results)
            logger.info(f"[OCR] Table detected: {table_structure.get('has_table')}")
            logger.info(f"[OCR] Headers: {table_structure.get('headers', [])}")

            if table_structure.get("has_table"):
                table_rows  = TableParser.parse_demand_table(table_structure)
                parsed_rows = [self._table_row_to_dict(r) for r in table_rows]
            else:
                logger.warning("[OCR] No table structure – using fallback parser")
                parsed_rows = self._fallback_parse(ocr_results)

            avg_conf = (
                sum(r["confidence"] for r in parsed_rows) / len(parsed_rows)
                if parsed_rows else 0.0
            )
            raw_text = "\n".join(r.text for r in ocr_results)
            logger.info(f"[OCR] {len(parsed_rows)} rows, avg conf {avg_conf:.2f}")

            return {
                "success": True, "rows": parsed_rows,
                "confidence": round(avg_conf, 2),
                "engine_used": self.preferred_engine.value,
                "raw_ocr_text": raw_text, "error": None,
            }

        except Exception as exc:
            logger.error(f"[OCR] extract_demand_from_image failed: {exc}", exc_info=True)
            return self._fail(str(exc))

    def _run_ocr_with_fallback(self, image_path: str) -> List[OCRResult]:
        if self.preferred_engine == OCREngine.PADDLEOCR:
            results = PaddleOCREngine.extract(image_path)
            if results:
                return results
            logger.warning("[OCR] PaddleOCR failed → trying EasyOCR")
            return EasyOCREngine.extract(image_path)

        elif self.preferred_engine == OCREngine.EASYOCR:
            results = EasyOCREngine.extract(image_path)
            if results:
                return results
            logger.warning("[OCR] EasyOCR failed → trying PaddleOCR")
            return PaddleOCREngine.extract(image_path)

        return []

    @staticmethod
    def _table_row_to_dict(row: TableRow) -> Dict[str, Any]:
        return {
            "sku_id": row.sku_id, "sku_name": row.sku_name,
            "description": row.description, "quantity": row.quantity,
            "confidence": row.confidence, "raw_text": row.raw_text,
        }

    def _fallback_parse(self, ocr_results: List[OCRResult]) -> List[Dict[str, Any]]:
        """
        Improved fallback: groups into rows spatially first,
        then extracts qty + name per row.
        Replaces the old fragile i+1/i+3 offset approach.
        """
        parsed = []
        rows   = TableParser._group_into_rows(ocr_results)

        for row_results in rows:
            texts    = [r.text.strip() for r in row_results]
            avg_conf = sum(r.confidence for r in row_results) / len(row_results)

            if all(t.lower() in _HEADER_WORDS for t in texts):
                continue

            sku_id = next(
                (t.upper().replace(" ", "") for t in texts if _SKU_ID_RE.match(t.strip())),
                None,
            )

            quantity = None
            for t in reversed(texts):
                cleaned = re.sub(r"(?i)(pcs|units?|boxes?|cartons?|packs?)\s*$", "", t).strip()
                if re.match(r"^\d{1,6}$", cleaned):
                    val = int(cleaned)
                    if 0 < val < 100_000:
                        quantity = val
                        break

            if quantity is None:
                continue

            qty_str    = str(quantity)
            name_parts = [
                t for t in texts
                if not (sku_id and t.upper().replace(" ", "") == sku_id)
                and not (re.match(r"^\d{1,6}$", t) and t == qty_str)
                and t.lower() not in _HEADER_WORDS
            ]
            sku_name = " ".join(name_parts).strip() or None

            if not (sku_id or sku_name):
                continue

            parsed.append({
                "sku_id": sku_id, "sku_name": sku_name,
                "description": None, "quantity": quantity,
                "confidence": round(avg_conf, 3),
                "raw_text": " ".join(texts),
            })

        return parsed

    @staticmethod
    def _fail(reason: str) -> Dict[str, Any]:
        return {
            "success": False, "rows": [], "confidence": 0.0,
            "engine_used": "none", "raw_ocr_text": "", "error": reason,
        }


# ============================================================
# Module-level helpers
# ============================================================

_ocr_service: Optional[OCRService] = None


def get_ocr_service() -> OCRService:
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService(preferred_engine=OCREngine.PADDLEOCR)
    return _ocr_service


def check_dependencies() -> Dict[str, Any]:
    result = {"paddleocr": False, "easyocr": False, "pillow": False, "status": "ok"}
    try:
        from paddleocr import PaddleOCR  # noqa
        result["paddleocr"] = True
    except ImportError:
        result["status"] = "partial"
    try:
        import easyocr  # noqa
        result["easyocr"] = True
    except ImportError:
        pass
    try:
        from PIL import Image  # noqa
        result["pillow"] = True
    except ImportError:
        result["status"] = "error"
    return result
