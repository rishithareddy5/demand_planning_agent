"""
Audio Transcription Service for WhatsApp Voice Messages
Uses OpenAI Whisper for speech-to-text conversion
"""

import logging
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import tempfile
import subprocess

logger = logging.getLogger(__name__)


class AudioFormat(Enum):
    """Supported audio formats"""
    OGG = "ogg"  # WhatsApp default
    MP3 = "mp3"
    WAV = "wav"
    M4A = "m4a"
    AMR = "amr"


@dataclass
class TranscriptionResult:
    """Structured transcription result"""
    text: str
    language: str
    confidence: float
    duration: Optional[float] = None
    segments: Optional[list] = None


class AudioConverter:
    """Convert various audio formats to WAV for Whisper"""
    
    @staticmethod
    def convert_to_wav(input_path: str, output_path: str) -> bool:
        """
        Convert audio file to WAV format using ffmpeg
        Returns: True if successful
        """
        try:
            # Check if ffmpeg is available
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                timeout=5
            )
            
            if result.returncode != 0:
                logger.error("[Audio] ffmpeg not available")
                return False
            
            # Convert to WAV: 16kHz, mono, 16-bit (optimal for Whisper)
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-ar', '16000',  # Sample rate
                '-ac', '1',      # Mono
                '-c:a', 'pcm_s16le',  # 16-bit PCM
                '-y',  # Overwrite output
                output_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info(f"[Audio] Converted to WAV: {output_path}")
                return True
            else:
                logger.error(f"[Audio] Conversion failed: {result.stderr.decode()}")
                return False
                
        except FileNotFoundError:
            logger.error("[Audio] ffmpeg not installed. Install: apt-get install ffmpeg")
            return False
        except subprocess.TimeoutExpired:
            logger.error("[Audio] Conversion timeout")
            return False
        except Exception as e:
            logger.error(f"[Audio] Conversion error: {e}")
            return False


class WhisperTranscriber:
    """Whisper-based transcription engine"""
    
    _model = None
    _model_size = "base"  # Options: tiny, base, small, medium, large
    
    @classmethod
    def get_model(cls, model_size: str = "base"):
        """
        Lazy load Whisper model
        
        Model sizes:
        - tiny: fastest, least accurate (~1GB RAM)
        - base: good balance (~1GB RAM) ← DEFAULT
        - small: better accuracy (~2GB RAM)
        - medium: production quality (~5GB RAM)
        - large: best accuracy (~10GB RAM)
        """
        if cls._model is None or cls._model_size != model_size:
            try:
                import whisper
                
                logger.info(f"[Audio] Loading Whisper model: {model_size}")
                cls._model = whisper.load_model(model_size)
                cls._model_size = model_size
                logger.info("[Audio] Whisper model loaded")
                
            except Exception as e:
                logger.error(f"[Audio] Whisper load failed: {e}")
                cls._model = None
        
        return cls._model
    
    @classmethod
    def transcribe(
        cls,
        audio_path: str,
        language: Optional[str] = None,
        model_size: str = "base"
    ) -> Optional[TranscriptionResult]:
        """
        Transcribe audio file using Whisper
        
        Args:
            audio_path: Path to audio file (preferably WAV)
            language: Language code (e.g., 'en', 'hi', 'ta') or None for auto-detect
            model_size: Whisper model size
        
        Returns:
            TranscriptionResult or None if failed
        """
        model = cls.get_model(model_size)
        
        if model is None:
            return None
        
        try:
            logger.info(f"[Audio] Transcribing: {audio_path}")
            
            # Whisper transcribe options
            options = {
                'fp16': False,  # Use FP32 for CPU
                'language': language,  # None = auto-detect
                'task': 'transcribe',  # 'transcribe' or 'translate'
            }
            
            result = model.transcribe(audio_path, **options)
            
            # Extract results
            text = result['text'].strip()
            detected_language = result.get('language', 'unknown')
            
            # Calculate average confidence from segments
            segments = result.get('segments', [])
            if segments:
                # Whisper doesn't provide per-word confidence
                # Use a heuristic: longer transcriptions = higher confidence
                confidence = min(len(text) / 100, 0.95)  # Cap at 0.95
            else:
                confidence = 0.5
            
            logger.info(f"[Audio] Transcribed: '{text[:100]}...' ({detected_language})")
            
            return TranscriptionResult(
                text=text,
                language=detected_language,
                confidence=confidence,
                segments=segments
            )
            
        except Exception as e:
            logger.error(f"[Audio] Transcription failed: {e}", exc_info=True)
            return None


class AudioTranscriptionService:
    """
    Main audio service for WhatsApp voice messages
    Handles: download → convert → transcribe → parse
    """
    
    def __init__(self, model_size: str = "base"):
        """
        Initialize service
        
        Args:
            model_size: Whisper model size (tiny/base/small/medium/large)
        """
        self.model_size = model_size
        self.converter = AudioConverter()
        self.transcriber = WhisperTranscriber()
    
    def transcribe_audio(
        self,
        audio_path: str,
        language: Optional[str] = None,
        auto_convert: bool = True
    ) -> Dict[str, Any]:
        """
        Transcribe audio file to text
        
        Args:
            audio_path: Path to audio file
            language: Expected language (None = auto-detect)
            auto_convert: Automatically convert to WAV if needed
        
        Returns:
            {
                'success': bool,
                'text': str,
                'language': str,
                'confidence': float,
                'error': Optional[str]
            }
        """
        try:
            # Ensure audio directory exists
            os.makedirs("whatsapp_uploads", exist_ok=True)
            
            # Check if conversion needed
            working_path = audio_path
            
            if auto_convert and not audio_path.lower().endswith('.wav'):
                logger.info("[Audio] Converting to WAV format")
                
                wav_path = "whatsapp_uploads/converted_audio.wav"
                
                if not self.converter.convert_to_wav(audio_path, wav_path):
                    return {
                        'success': False,
                        'text': '',
                        'language': 'unknown',
                        'confidence': 0.0,
                        'error': 'Audio conversion failed. Ensure ffmpeg is installed.'
                    }
                
                working_path = wav_path
            
            # Transcribe
            result = self.transcriber.transcribe(
                working_path,
                language=language,
                model_size=self.model_size
            )
            
            if result is None:
                return {
                    'success': False,
                    'text': '',
                    'language': 'unknown',
                    'confidence': 0.0,
                    'error': 'Transcription failed. Check if Whisper is installed.'
                }
            
            return {
                'success': True,
                'text': result.text,
                'language': result.language,
                'confidence': result.confidence,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"[Audio] Service error: {e}", exc_info=True)
            return {
                'success': False,
                'text': '',
                'language': 'unknown',
                'confidence': 0.0,
                'error': str(e)
            }
    
    def transcribe_whatsapp_voice(
        self,
        audio_data: bytes,
        filename: str = "voice_message.ogg"
    ) -> Dict[str, Any]:
        """
        Transcribe WhatsApp voice message
        
        Args:
            audio_data: Raw audio bytes from Twilio
            filename: Original filename (for format detection)
        
        Returns:
            Same as transcribe_audio()
        """
        try:
            # Save audio data
            audio_path = f"whatsapp_uploads/{filename}"
            
            with open(audio_path, 'wb') as f:
                f.write(audio_data)
            
            logger.info(f"[Audio] Saved voice message: {audio_path}")
            
            # Transcribe
            return self.transcribe_audio(audio_path, auto_convert=True)
            
        except Exception as e:
            logger.error(f"[Audio] WhatsApp voice error: {e}")
            return {
                'success': False,
                'text': '',
                'language': 'unknown',
                'confidence': 0.0,
                'error': str(e)
            }


# Singleton instance
_audio_service = None


def get_audio_service(model_size: str = "base") -> AudioTranscriptionService:
    """
    Get singleton audio service
    
    Args:
        model_size: Whisper model size (only used on first call)
    """
    global _audio_service
    
    if _audio_service is None:
        _audio_service = AudioTranscriptionService(model_size=model_size)
    
    return _audio_service


# ============================================
# Installation Check
# ============================================

def check_dependencies() -> Dict[str, bool]:
    """
    Check if required dependencies are installed
    Returns: {'whisper': bool, 'ffmpeg': bool}
    """
    deps = {
        'whisper': False,
        'ffmpeg': False
    }
    
    # Check Whisper
    try:
        import whisper
        deps['whisper'] = True
    except ImportError:
        logger.warning("[Audio] Whisper not installed")
    
    # Check ffmpeg
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            timeout=5
        )
        deps['ffmpeg'] = (result.returncode == 0)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("[Audio] ffmpeg not installed")
    
    return deps


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "="*60)
    print("Audio Transcription Service - Dependency Check")
    print("="*60)
    
    deps = check_dependencies()
    
    for name, installed in deps.items():
        status = "✅ Installed" if installed else "❌ Missing"
        print(f"{name}: {status}")
    
    if not deps['whisper']:
        print("\nInstall Whisper: pip install openai-whisper")
    
    if not deps['ffmpeg']:
        print("\nInstall ffmpeg:")
        print("  Ubuntu/Debian: sudo apt-get install ffmpeg")
        print("  macOS: brew install ffmpeg")
        print("  Windows: Download from https://ffmpeg.org/")
    
    print("="*60)
