"""
Text-to-Speech generation for detection announcements.
Uses Microsoft Edge TTS (edge-tts).
"""

import asyncio
import numpy as np
from io import BytesIO
from pydub import AudioSegment
from loguru import logger

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logger.warning("edge-tts not installed, TTS will be disabled")


# Voice mapping for different languages (using female voices by default)
VOICES = {
    'de': 'de-DE-KatjaNeural',
    'en': 'en-US-JennyNeural',
    'cs': 'cs-CZ-VlastaNeural',
    'fr': 'fr-FR-DeniseNeural',
    'it': 'it-IT-ElsaNeural',
    'es': 'es-ES-ElviraNeural',
    'pl': 'pl-PL-ZofiaNeural',
    'nl': 'nl-NL-ColetteNeural',
}


async def _generate_tts_async(text: str, voice: str) -> bytes:
    """
    Generate TTS audio asynchronously using edge-tts.
    
    Args:
        text: Text to synthesize
        voice: Voice name (e.g., 'de-DE-KatjaNeural')
        
    Returns:
        Audio data as bytes (MP3 format)
    """
    communicate = edge_tts.Communicate(text, voice)
    
    audio_data = BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.write(chunk["data"])
    
    audio_data.seek(0)
    return audio_data.read()


def generate_tts(text: str, language_code: str, use_sci: bool = False) -> np.ndarray:
    """
    Generate TTS audio as numpy array.
    
    Args:
        text: Text to synthesize
        language_code: Language code (e.g., 'de', 'en', 'cs')
        use_sci: If True, use English voice (for scientific names)
        
    Returns:
        Numpy array with audio samples (int16, mono, 48kHz)
        Returns silence if TTS fails or is unavailable.
    """
    if not EDGE_TTS_AVAILABLE:
        logger.debug("edge-tts not available, returning silence")
        return np.zeros(48000, dtype=np.int16)
    
    if use_sci:
        voice = VOICES['en']
    else:
        voice = VOICES.get(language_code, VOICES['en'])
    
    logger.debug(f"Generating TTS: '{text}' (voice: {voice})")
    
    try:
        audio_bytes = asyncio.run(_generate_tts_async(text, voice))
        
        if not audio_bytes:
            logger.warning("TTS returned empty data")
            return np.zeros(48000, dtype=np.int16)
        
        audio_segment = AudioSegment.from_mp3(BytesIO(audio_bytes))
        audio_segment = audio_segment.set_channels(1)
        audio_segment = audio_segment.set_frame_rate(48000)
        audio_segment = audio_segment.set_sample_width(2)
        
        samples = np.array(audio_segment.get_array_of_samples(), dtype=np.int16)
        
        logger.debug(f"TTS generated: {len(samples)} samples (~{len(samples)/48000:.1f}s)")
        
        return samples
        
    except asyncio.TimeoutError:
        logger.error("TTS timeout - no internet connection?")
        return np.zeros(48000, dtype=np.int16)
        
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        return np.zeros(48000, dtype=np.int16)


def test_tts():
    """Test TTS functionality."""
    if not EDGE_TTS_AVAILABLE:
        print("edge-tts not installed")
        print("Install with: pip install edge-tts")
        return
    
    print("Testing TTS...")
    
    print("Generating German TTS...")
    audio_de = generate_tts("12345 Kohlmeise", "de", use_sci=False)
    print(f"German: {len(audio_de)} samples")
    
    print("Generating English TTS (scientific)...")
    audio_en = generate_tts("12345 Parus major", "de", use_sci=True)
    print(f"English: {len(audio_en)} samples")
    
    print("Generating Czech TTS...")
    audio_cs = generate_tts("12345 Sýkora koňadra", "cs", use_sci=False)
    print(f"Czech: {len(audio_cs)} samples")
    
    print("\nTTS test complete!")
    print("Note: Audio was not played, only generated.")


if __name__ == "__main__":
    test_tts()