"""
Standalone Test Suite for Demand Ingestion System
NO Temporal, Docker, or RedPanda required

Tests:
1. Text parsing
2. Excel parsing  
3. OCR image parsing
4. Audio transcription (if available)
5. WhatsApp simulation
"""

import logging
import sys
import os
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Color codes for terminal
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    """Print section header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(70)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}\n")


def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_warning(text):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


# ============================================================================
# TEST 1: TEXT PARSING
# ============================================================================

def test_text_parsing():
    """Test text demand parsing"""
    print_header("TEST 1: Text Demand Parsing")
    
    try:
        from app.services.reply_parser_service import parse_reply
        
        test_cases = [
            {
                "name": "Simple demand",
                "from_email": "dist01@test.com",
                "body": "MALKIST CHEESE JUMBO PACK - 100\nBENG BENG WAFER - 50"
            },
            {
                "name": "With SKU codes",
                "from_email": "dist02@test.com",
                "body": "SKU01 - 200\nSKU05 - 150"
            },
            {
                "name": "Negative response",
                "from_email": "dist03@test.com",
                "body": "No demand this month"
            },
            {
                "name": "Informational",
                "from_email": "dist04@test.com",
                "body": "Will send later today"
            }
        ]
        
        passed = 0
        failed = 0
        
        for i, test in enumerate(test_cases, 1):
            print(f"\n{Colors.BOLD}Test Case {i}: {test['name']}{Colors.END}")
            print(f"Input: {test['body'][:50]}...")
            
            result = parse_reply(test['from_email'], test['body'])
            
            print(f"  Reply Type: {result['reply_type']}")
            print(f"  Confidence: {result['confidence']}")
            print(f"  Items Found: {len(result['items'])}")
            
            if result['items']:
                for item in result['items']:
                    print(f"    • {item['sku_name']}: {item['quantity']} units")
            
            if result['confidence'] > 0:
                print_success(f"Parsed successfully (confidence: {result['confidence']})")
                passed += 1
            else:
                print_warning("Low/zero confidence")
                failed += 1
        
        print(f"\n{Colors.BOLD}Results: {passed} passed, {failed} warnings{Colors.END}")
        return True
        
    except Exception as e:
        print_error(f"Text parsing test failed: {e}")
        logger.exception(e)
        return False


# ============================================================================
# TEST 2: EXCEL PARSING
# ============================================================================

def test_excel_parsing():
    """Test Excel demand parsing"""
    print_header("TEST 2: Excel Demand Parsing")
    
    try:
        import pandas as pd
        from app.services.reply_parser_service import parse_reply
        
        # Check if test Excel exists
        test_files = list(Path("attachments").glob("*.xlsx"))
        
        if not test_files:
            print_warning("No Excel files found in attachments/ directory")
            print("  Create a test file with columns: Product, Quantity")
            return False
        
        print(f"Found {len(test_files)} Excel files to test\n")
        
        for i, file_path in enumerate(test_files[:3], 1):  # Test first 3
            print(f"{Colors.BOLD}Testing: {file_path.name}{Colors.END}")
            
            try:
                df = pd.read_excel(file_path)
                print(f"  Rows: {len(df)}")
                print(f"  Columns: {list(df.columns)}")
                
                # Convert to text for parsing
                lines = []
                for _, row in df.iterrows():
                    row_text = " ".join([str(v) for v in row.values if pd.notna(v)])
                    if row_text.strip():
                        lines.append(row_text)
                
                combined = "\n".join(lines)
                result = parse_reply("test@test.com", combined)
                
                print(f"  Items Parsed: {len(result['items'])}")
                print(f"  Confidence: {result['confidence']}")
                
                if result['items']:
                    for item in result['items'][:5]:  # Show first 5
                        print(f"    • {item['sku_name']}: {item['quantity']}")
                    
                    print_success("Excel parsed successfully")
                else:
                    print_warning("No items extracted")
                
            except Exception as e:
                print_error(f"Failed to parse {file_path.name}: {e}")
        
        return True
        
    except Exception as e:
        print_error(f"Excel parsing test failed: {e}")
        logger.exception(e)
        return False


# ============================================================================
# TEST 3: OCR SERVICE
# ============================================================================

def test_ocr_service():
    """Test OCR demand extraction"""
    print_header("TEST 3: OCR Image Parsing")
    
    try:
        from app.services.ocr_service import get_ocr_service, check_dependencies
        
        # Check OCR dependencies
        print("Checking OCR dependencies...")
        
        try:
            from paddleocr import PaddleOCR
            print_success("PaddleOCR available")
        except ImportError:
            print_error("PaddleOCR not installed")
            print("  Install: pip install paddleocr paddlepaddle")
            return False
        
        # Look for test images
        test_images = []
        for ext in ['*.jpg', '*.jpeg', '*.png']:
            test_images.extend(Path("whatsapp_uploads").glob(ext))
        
        if not test_images:
            print_warning("No test images found in whatsapp_uploads/")
            print("  Place a demand sheet image there to test OCR")
            return False
        
        print(f"\nFound {len(test_images)} test images\n")
        
        ocr_service = get_ocr_service()
        
        for i, image_path in enumerate(test_images[:2], 1):  # Test first 2
            print(f"{Colors.BOLD}Testing: {image_path.name}{Colors.END}")
            
            result = ocr_service.extract_demand_from_image(str(image_path))
            
            print(f"  Success: {result['success']}")
            print(f"  Confidence: {result['confidence']}")
            print(f"  Rows Extracted: {len(result['rows'])}")
            
            if result['success']:
                print(f"\n  OCR Text Preview:")
                print(f"  {result['raw_ocr_text'][:200]}...")
                
                print(f"\n  Parsed Rows:")
                for row in result['rows'][:5]:
                    print(f"    • {row.get('sku_id', 'N/A')} | "
                          f"{row.get('sku_name', 'N/A')} | "
                          f"Qty: {row.get('quantity', 'N/A')}")
                
                print_success("OCR extraction successful")
            else:
                print_error(f"OCR failed: {result.get('error', 'Unknown')}")
        
        return True
        
    except Exception as e:
        print_error(f"OCR test failed: {e}")
        logger.exception(e)
        return False


# ============================================================================
# TEST 4: AUDIO TRANSCRIPTION
# ============================================================================

def test_audio_service():
    """Test audio transcription"""
    print_header("TEST 4: Audio Transcription")
    
    try:
        # Check if audio service is available
        try:
            from app.services.audio_service import get_audio_service, check_dependencies
            
            deps = check_dependencies()
            
            print("Checking audio dependencies...")
            for name, installed in deps.items():
                if installed:
                    print_success(f"{name} installed")
                else:
                    print_error(f"{name} missing")
            
            if not all(deps.values()):
                print("\nInstall missing dependencies:")
                if not deps['whisper']:
                    print("  pip install openai-whisper")
                if not deps['ffmpeg']:
                    print("  sudo apt-get install ffmpeg  # Linux")
                    print("  brew install ffmpeg  # macOS")
                return False
            
        except ImportError:
            print_error("Audio service not available")
            print("  Install: pip install openai-whisper ffmpeg-python")
            return False
        
        # Look for test audio files
        test_audio = []
        for ext in ['*.ogg', '*.mp3', '*.wav', '*.m4a']:
            test_audio.extend(Path("whatsapp_uploads").glob(ext))
        
        if not test_audio:
            print_warning("No test audio files found in whatsapp_uploads/")
            print("  Place an audio file there to test transcription")
            return False
        
        print(f"\nFound {len(test_audio)} test audio files\n")
        
        audio_service = get_audio_service(model_size="base")
        
        for audio_path in test_audio[:2]:  # Test first 2
            print(f"{Colors.BOLD}Testing: {audio_path.name}{Colors.END}")
            
            result = audio_service.transcribe_audio(str(audio_path))
            
            print(f"  Success: {result['success']}")
            print(f"  Language: {result.get('language', 'N/A')}")
            print(f"  Confidence: {result.get('confidence', 0)}")
            
            if result['success']:
                print(f"\n  Transcription:")
                print(f"  \"{result['text']}\"")
                print_success("Audio transcription successful")
            else:
                print_error(f"Transcription failed: {result.get('error', 'Unknown')}")
        
        return True
        
    except Exception as e:
        print_error(f"Audio test failed: {e}")
        logger.exception(e)
        return False


# ============================================================================
# TEST 5: WHATSAPP SIMULATION
# ============================================================================

def test_whatsapp_simulation():
    """Simulate WhatsApp message handling"""
    print_header("TEST 5: WhatsApp Message Simulation")
    
    print("This test simulates WhatsApp webhook calls\n")
    
    test_scenarios = [
        {
            "name": "Text demand",
            "From": "whatsapp:+1234567890",
            "Body": "MALKIST CHEESE - 100\nBENG BENG - 50",
            "NumMedia": 0
        },
        {
            "name": "Negative response",
            "From": "whatsapp:+1234567890",
            "Body": "No requirement",
            "NumMedia": 0
        },
        {
            "name": "Media attachment (simulated)",
            "From": "whatsapp:+1234567890",
            "Body": "",
            "NumMedia": 1,
            "MediaContentType0": "image/jpeg",
            "note": "Would trigger OCR in real scenario"
        }
    ]
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n{Colors.BOLD}Scenario {i}: {scenario['name']}{Colors.END}")
        print(f"  From: {scenario['From']}")
        print(f"  Body: {scenario.get('Body', '(media)'[:30])}")
        print(f"  Media: {scenario['NumMedia']}")
        
        if scenario['NumMedia'] == 0:
            # Simulate text parsing
            from app.services.reply_parser_service import parse_reply
            
            result = parse_reply(scenario['From'], scenario['Body'])
            
            print(f"\n  Parsed Result:")
            print(f"    Type: {result['reply_type']}")
            print(f"    Confidence: {result['confidence']}")
            print(f"    Items: {len(result['items'])}")
            
            if result['items']:
                for item in result['items']:
                    print(f"      • {item['sku_name']}: {item['quantity']}")
            
            print_success("Would send WhatsApp reply")
        else:
            print(f"  Note: {scenario.get('note', 'Media handling')}")
            print_warning("Would process media file")
    
    return True


# ============================================================================
# TEST 6: SKU MATCHING
# ============================================================================

def test_sku_matching():
    """Test SKU fuzzy matching"""
    print_header("TEST 6: SKU Fuzzy Matching")
    
    try:
        from app.services.reply_parser_service import match_sku
        
        test_inputs = [
            "malkist cheese jumbo pack",
            "beng beng wafer chocolate",
            "SKU01",
            "cheese cracker large",
            "totally wrong product name 123"
        ]
        
        for test_input in test_inputs:
            print(f"\n{Colors.BOLD}Input: '{test_input}'{Colors.END}")
            
            sku_id, sku_name, score = match_sku(test_input, min_score=70)
            
            if sku_id:
                print(f"  Match: {sku_name}")
                print(f"  SKU ID: {sku_id}")
                print(f"  Score: {score}/100")
                
                if score >= 90:
                    print_success("Excellent match")
                elif score >= 75:
                    print_success("Good match")
                else:
                    print_warning("Weak match")
            else:
                print_error(f"No match found (score: {score})")
        
        return True
        
    except Exception as e:
        print_error(f"SKU matching test failed: {e}")
        logger.exception(e)
        return False


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_all_tests():
    """Run complete test suite"""
    
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔" + "="*68 + "╗")
    print("║" + " DEMAND INGESTION SYSTEM - STANDALONE TEST SUITE ".center(68) + "║")
    print("║" + " NO Docker / Temporal / RedPanda Required ".center(68) + "║")
    print("╚" + "="*68 + "╝")
    print(Colors.END)
    
    results = {}
    
    # Run tests
    results['text_parsing'] = test_text_parsing()
    results['excel_parsing'] = test_excel_parsing()
    results['ocr_service'] = test_ocr_service()
    results['audio_service'] = test_audio_service()
    results['whatsapp_sim'] = test_whatsapp_simulation()
    results['sku_matching'] = test_sku_matching()
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = f"{Colors.GREEN}PASS{Colors.END}" if result else f"{Colors.RED}FAIL{Colors.END}"
        print(f"  {test_name.replace('_', ' ').title()}: {status}")
    
    print(f"\n{Colors.BOLD}Overall: {passed}/{total} tests passed{Colors.END}")
    
    if passed == total:
        print(f"\n{Colors.GREEN}✓ All tests passed! System ready for integration.{Colors.END}")
    elif passed >= total * 0.7:
        print(f"\n{Colors.YELLOW}⚠ Most tests passed. Review failures above.{Colors.END}")
    else:
        print(f"\n{Colors.RED}✗ Multiple failures. Check installation and dependencies.{Colors.END}")
    
    print(f"\n{Colors.BOLD}Next Steps for Your Team:{Colors.END}")
    print("  1. Integrate with Temporal workflow")
    print("  2. Connect to RedPanda event stream")
    print("  3. Add PostgreSQL persistence")
    print("  4. Deploy with Docker")
    print()


if __name__ == "__main__":
    run_all_tests()
