"""
Production-Grade OCR Service for Demand Planning
Supports multiple OCR engines with fallback, table detection, and confidence scoring.
"""

import logging
import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import re

from PIL import Image, ImageEnhance, ImageFilter
import numpy as np

logger = logging.getLogger(__name__)


class OCREngine(Enum):
    """Supported OCR engines"""
    PADDLEOCR = "paddleocr"
    EASYOCR = "easyocr"
    TESSERACT = "tesseract"


@dataclass
class OCRResult:
    """Structured OCR result"""
    text: str
    confidence: float
    bbox: Optional[Tuple[int, int, int, int]] = None  # x1, y1, x2, y2


@dataclass
class TableRow:
    """Represents a parsed table row"""
    sku_id: Optional[str]
    sku_name: Optional[str]
    description: Optional[str]
    quantity: Optional[int]
    confidence: float
    raw_text: str


class ImagePreprocessor:
    """Advanced image preprocessing for OCR accuracy"""
    
    @staticmethod
    def preprocess(image_path: str, output_path: str) -> str:
        """
        Apply production-grade preprocessing pipeline
        Returns: path to processed image
        """
        try:
            img = Image.open(image_path)
            
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 1. Resize for optimal OCR (target 2000px width)
            target_width = 2000
            if img.width < target_width:
                scale = target_width / img.width
                new_size = (target_width, int(img.height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # 2. Denoise
            img = img.filter(ImageFilter.MedianFilter(size=3))
            
            # 3. Enhance sharpness
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(2.0)
            
            # 4. Enhance contrast
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)
            
            # 5. Convert to grayscale for better OCR
            img = img.convert('L')
            
            # 6. Apply adaptive thresholding
            img_array = np.array(img)
            # Simple threshold - can be enhanced with cv2.adaptiveThreshold
            threshold = np.mean(img_array)
            img_array = np.where(img_array > threshold, 255, 0).astype(np.uint8)
            img = Image.fromarray(img_array)
            
            # Save processed image
            img.save(output_path, quality=95)
            logger.info(f"[OCR] Preprocessed image saved: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"[OCR] Preprocessing failed: {e}")
            return image_path  # Return original if preprocessing fails


class PaddleOCREngine:
    """PaddleOCR engine wrapper with lazy initialization"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Lazy singleton to avoid memory issues"""
        if cls._instance is None:
            try:
                from paddleocr import PaddleOCR
                cls._instance = PaddleOCR(
                    use_angle_cls=True,
                    lang='en',
                    enable_mkldnn=False,  # Fix for Windows
                    use_gpu=False,
                    show_log=False
                )
                logger.info("[OCR] PaddleOCR initialized")
            except Exception as e:
                logger.error(f"[OCR] PaddleOCR initialization failed: {e}")
                cls._instance = None
        return cls._instance
    
    @classmethod
    def extract(cls, image_path: str) -> List[OCRResult]:
        """Extract text with PaddleOCR"""
        ocr = cls.get_instance()
        if not ocr:
            return []
        
        try:
            result = ocr.ocr(image_path, cls=True)
            
            if not result or not result[0]:
                return []
            
            ocr_results = []
            for line in result[0]:
                bbox = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                text_info = line[1]  # (text, confidence)
                
                text = text_info[0]
                confidence = text_info[1]
                
                # Convert bbox to simple format
                x_coords = [point[0] for point in bbox]
                y_coords = [point[1] for point in bbox]
                simple_bbox = (
                    int(min(x_coords)),
                    int(min(y_coords)),
                    int(max(x_coords)),
                    int(max(y_coords))
                )
                
                ocr_results.append(OCRResult(
                    text=text,
                    confidence=confidence,
                    bbox=simple_bbox
                ))
            
            # Sort by vertical position (top to bottom)
            ocr_results.sort(key=lambda x: x.bbox[1] if x.bbox else 0)
            
            return ocr_results
            
        except Exception as e:
            logger.error(f"[OCR] PaddleOCR extraction failed: {e}")
            return []


class EasyOCREngine:
    """EasyOCR engine wrapper (fallback option)"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Lazy singleton"""
        if cls._instance is None:
            try:
                import easyocr
                cls._instance = easyocr.Reader(['en'], gpu=False)
                logger.info("[OCR] EasyOCR initialized")
            except Exception as e:
                logger.error(f"[OCR] EasyOCR initialization failed: {e}")
                cls._instance = None
        return cls._instance
    
    @classmethod
    def extract(cls, image_path: str) -> List[OCRResult]:
        """Extract text with EasyOCR"""
        reader = cls.get_instance()
        if not reader:
            return []
        
        try:
            results = reader.readtext(image_path)
            
            ocr_results = []
            for bbox, text, confidence in results:
                # bbox is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                x_coords = [point[0] for point in bbox]
                y_coords = [point[1] for point in bbox]
                simple_bbox = (
                    int(min(x_coords)),
                    int(min(y_coords)),
                    int(max(x_coords)),
                    int(max(y_coords))
                )
                
                ocr_results.append(OCRResult(
                    text=text,
                    confidence=confidence,
                    bbox=simple_bbox
                ))
            
            # Sort by vertical position
            ocr_results.sort(key=lambda x: x.bbox[1] if x.bbox else 0)
            
            return ocr_results
            
        except Exception as e:
            logger.error(f"[OCR] EasyOCR extraction failed: {e}")
            return []


class TableParser:
    """Intelligent table structure detection and parsing"""
    
    @staticmethod
    def detect_table_structure(ocr_results: List[OCRResult]) -> Dict[str, Any]:
        """
        Detect table columns and headers
        Returns: {
            'has_table': bool,
            'headers': List[str],
            'column_positions': List[int],
            'rows': List[List[OCRResult]]
        }
        """
        if not ocr_results:
            return {'has_table': False}
        
        # Group texts by vertical position (rows)
        rows = TableParser._group_into_rows(ocr_results)
        
        if len(rows) < 2:
            return {'has_table': False}
        
        # First row is likely headers
        first_row = rows[0]
        header_texts = [r.text.lower().strip() for r in first_row]
        
        # Check for common demand table headers
        header_keywords = ['sku', 'product', 'name', 'description', 'qty', 'quantity', 'demand']
        has_headers = any(any(kw in h for kw in header_keywords) for h in header_texts)
        
        # Detect column positions from first row
        column_positions = sorted([r.bbox[0] for r in first_row if r.bbox])
        
        return {
            'has_table': has_headers,
            'headers': header_texts,
            'column_positions': column_positions,
            'rows': rows[1:] if has_headers else rows  # Skip header row
        }
    
    @staticmethod
    def _group_into_rows(ocr_results: List[OCRResult], row_tolerance: int = 15) -> List[List[OCRResult]]:
        """Group OCR results into rows based on vertical position"""
        if not ocr_results:
            return []
        
        rows = []
        current_row = [ocr_results[0]]
        current_y = ocr_results[0].bbox[1] if ocr_results[0].bbox else 0
        
        for result in ocr_results[1:]:
            result_y = result.bbox[1] if result.bbox else 0
            
            # If within tolerance, same row
            if abs(result_y - current_y) <= row_tolerance:
                current_row.append(result)
            else:
                # New row
                if current_row:
                    # Sort row items by horizontal position
                    current_row.sort(key=lambda x: x.bbox[0] if x.bbox else 0)
                    rows.append(current_row)
                current_row = [result]
                current_y = result_y
        
        # Add last row
        if current_row:
            current_row.sort(key=lambda x: x.bbox[0] if x.bbox else 0)
            rows.append(current_row)
        
        return rows
    
    @staticmethod
    def parse_demand_table(table_structure: Dict[str, Any]) -> List[TableRow]:
        """
        Parse table structure into structured demand rows
        Handles various table formats intelligently
        """
        if not table_structure.get('has_table'):
            return []
        
        rows_data = table_structure.get('rows', [])
        parsed_rows = []
        
        for row_results in rows_data:
            parsed_row = TableParser._parse_single_row(row_results)
            if parsed_row and (parsed_row.sku_id or parsed_row.sku_name):
                parsed_rows.append(parsed_row)
        
        return parsed_rows
    
    @staticmethod
    def _parse_single_row(row_results: List[OCRResult]) -> Optional[TableRow]:
        """Parse a single table row into structured format"""
        if not row_results:
            return None
        
        # Combine all text for raw representation
        raw_text = " ".join([r.text for r in row_results])
        
        # Initialize variables
        sku_id = None
        sku_name = None
        description = None
        quantity = None
        avg_confidence = sum(r.confidence for r in row_results) / len(row_results)
        
        # Pattern 1: SKU ID detection (SKU01, SKU001, etc.)
        for result in row_results:
            if re.match(r'^SKU\d+$', result.text.upper().replace(' ', '')):
                sku_id = result.text.upper().replace(' ', '')
                break
        
        # Pattern 2: Extract quantity (last number in row, or number with unit keywords)
        quantity_candidates = []
        for result in row_results:
            # Look for pure numbers
            numbers = re.findall(r'\b\d+\b', result.text)
            for num in numbers:
                # Check if it's not part of SKU ID
                if not re.match(r'SKU\d+', result.text.upper()):
                    quantity_candidates.append(int(num))
        
        # Take the largest number as quantity (usually demand quantity > SKU number)
        if quantity_candidates:
            quantity = max(quantity_candidates)
        
        # Pattern 3: Extract product name/description
        # Everything that's not SKU ID and not pure quantity
        name_parts = []
        for result in row_results:
            text = result.text.strip()
            
            # Skip if it's the SKU ID
            if sku_id and text.upper().replace(' ', '') == sku_id:
                continue
            
            # Skip if it's purely numeric (quantity)
            if text.isdigit():
                continue
            
            # Skip common header words
            if text.lower() in ['sku', 'product', 'name', 'qty', 'quantity', 'description']:
                continue
            
            # This is likely product name/description
            name_parts.append(text)
        
        if name_parts:
            # First part is usually SKU name, rest is description
            sku_name = name_parts[0]
            if len(name_parts) > 1:
                description = " ".join(name_parts[1:])
        
        # Validate: We need at least SKU or name and a quantity
        if not quantity:
            return None
        
        if not (sku_id or sku_name):
            return None
        
        return TableRow(
            sku_id=sku_id,
            sku_name=sku_name,
            description=description,
            quantity=quantity,
            confidence=avg_confidence,
            raw_text=raw_text
        )


class OCRService:
    """Main OCR service with multi-engine support and intelligent parsing"""
    
    def __init__(self, preferred_engine: OCREngine = OCREngine.PADDLEOCR):
        self.preferred_engine = preferred_engine
        self.preprocessor = ImagePreprocessor()
    
    def extract_demand_from_image(
        self,
        image_path: str,
        preprocess: bool = True
    ) -> Dict[str, Any]:
        """
        Main entry point: Extract structured demand data from image
        
        Returns:
        {
            'success': bool,
            'rows': List[Dict],  # Parsed demand rows
            'confidence': float,
            'engine_used': str,
            'raw_ocr_text': str,
            'error': Optional[str]
        }
        """
        try:
            # Create output directory
            os.makedirs("whatsapp_uploads", exist_ok=True)
            
            # Preprocess image
            processed_path = image_path
            if preprocess:
                processed_path = self.preprocessor.preprocess(
                    image_path,
                    "whatsapp_uploads/processed_image.jpg"
                )
            
            # Run OCR with fallback
            ocr_results = self._run_ocr_with_fallback(processed_path)
            
            if not ocr_results:
                return {
                    'success': False,
                    'rows': [],
                    'confidence': 0.0,
                    'engine_used': 'none',
                    'raw_ocr_text': '',
                    'error': 'OCR extraction failed'
                }
            
            # Detect table structure
            table_structure = TableParser.detect_table_structure(ocr_results)
            
            # Log detected structure
            logger.info(f"[OCR] Table detected: {table_structure.get('has_table')}")
            logger.info(f"[OCR] Headers: {table_structure.get('headers', [])}")
            
            # Parse table into demand rows
            parsed_rows = []
            
            if table_structure.get('has_table'):
                table_rows = TableParser.parse_demand_table(table_structure)
                parsed_rows = [self._table_row_to_dict(row) for row in table_rows]
            else:
                # Fallback: Try to parse as unstructured text
                raw_text = "\n".join([r.text for r in ocr_results])
                logger.warning("[OCR] No table structure detected. Using fallback parsing.")
                parsed_rows = self._fallback_parse(ocr_results)
            
            # Calculate overall confidence
            avg_confidence = 0.0
            if parsed_rows:
                avg_confidence = sum(r['confidence'] for r in parsed_rows) / len(parsed_rows)
            
            # Get raw text for logging
            raw_text = "\n".join([r.text for r in ocr_results])
            
            return {
                'success': True,
                'rows': parsed_rows,
                'confidence': round(avg_confidence, 2),
                'engine_used': self.preferred_engine.value,
                'raw_ocr_text': raw_text,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"[OCR] Extract demand failed: {e}", exc_info=True)
            return {
                'success': False,
                'rows': [],
                'confidence': 0.0,
                'engine_used': 'error',
                'raw_ocr_text': '',
                'error': str(e)
            }
    
    def _run_ocr_with_fallback(self, image_path: str) -> List[OCRResult]:
        """Run OCR with engine fallback"""
        # Try preferred engine first
        if self.preferred_engine == OCREngine.PADDLEOCR:
            results = PaddleOCREngine.extract(image_path)
            if results:
                return results
            
            # Fallback to EasyOCR
            logger.warning("[OCR] PaddleOCR failed, trying EasyOCR")
            return EasyOCREngine.extract(image_path)
        
        elif self.preferred_engine == OCREngine.EASYOCR:
            results = EasyOCREngine.extract(image_path)
            if results:
                return results
            
            # Fallback to PaddleOCR
            logger.warning("[OCR] EasyOCR failed, trying PaddleOCR")
            return PaddleOCREngine.extract(image_path)
        
        return []
    
    @staticmethod
    def _table_row_to_dict(row: TableRow) -> Dict[str, Any]:
        """Convert TableRow to dictionary format"""
        return {
            'sku_id': row.sku_id,
            'sku_name': row.sku_name,
            'description': row.description,
            'quantity': row.quantity,
            'confidence': round(row.confidence, 2),
            'raw_text': row.raw_text
        }
    
    def _fallback_parse(self, ocr_results: List[OCRResult]) -> List[Dict[str, Any]]:
        """
        Fallback parsing when table structure is not detected
        Uses pattern matching on raw OCR text
        """
        parsed = []
        
        i = 0
        while i < len(ocr_results):
            result = ocr_results[i]
            text = result.text.strip()
            
            # Look for SKU pattern
            if re.match(r'^SKU\d+$', text.upper().replace(' ', '')):
                sku_id = text.upper().replace(' ', '')
                
                # Try to get next few items as name and quantity
                try:
                    sku_name = ocr_results[i + 1].text.strip() if i + 1 < len(ocr_results) else None
                    
                    # Look for quantity in next 3 items
                    quantity = None
                    for j in range(i + 1, min(i + 5, len(ocr_results))):
                        qty_match = re.search(r'\b(\d+)\b', ocr_results[j].text)
                        if qty_match:
                            quantity = int(qty_match.group(1))
                            break
                    
                    if sku_name and quantity:
                        parsed.append({
                            'sku_id': sku_id,
                            'sku_name': sku_name,
                            'description': None,
                            'quantity': quantity,
                            'confidence': result.confidence,
                            'raw_text': f"{sku_id} {sku_name} {quantity}"
                        })
                    
                    i += 4  # Skip processed items
                except IndexError:
                    i += 1
            else:
                i += 1
        
        return parsed


# Singleton instance for easy access
_ocr_service = None

def get_ocr_service() -> OCRService:
    """Get singleton OCR service instance"""
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService(preferred_engine=OCREngine.PADDLEOCR)
    return _ocr_service


def check_dependencies():
    """
    Check OCR dependencies availability
    """
    try:
        from paddleocr import PaddleOCR
        from PIL import Image
        return {
            "paddleocr": True,
            "pillow": True,
            "status": "ok"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }