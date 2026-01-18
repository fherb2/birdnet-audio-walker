"""
Test audio playback with sounddevice.
"""

import numpy as np
import sounddevice as sd
from birdnet_play.tts import generate_tts

def test_playback():
    """Test if audio plays through speakers."""
    
    print("=" * 60)
    print("Audio Playback Test")
    print("=" * 60)
    
    # Check available audio devices
    print("\nAvailable audio devices:")
    print(sd.query_devices())
    print()
    
    # Generate test audio with TTS
    print("Generating TTS audio...")
    audio_data = generate_tts("Test 12345 Kohlmeise", "de", use_sci=False)
    
    if len(audio_data) == 0:
        print("❌ TTS generation failed")
        return
    
    print(f"✓ Generated {len(audio_data)} samples (~{len(audio_data)/48000:.1f}s)")
    print()
    
    # Play audio
    print("Playing audio through speakers...")
    print("(You should hear: 'Test 12345 Kohlmeise')")
    print()
    
    try:
        sd.play(audio_data, samplerate=48000)
        sd.wait()  # Wait until playback is finished
        
        print("✓ Playback complete!")
        print()
        
        # Ask user if they heard it
        response = input("Did you hear audio from the speakers? [Y/n]: ").strip().lower()
        
        if response in ['y', 'yes', '']:
            print("✅ Audio playback works!")
        else:
            print("⚠️  Audio playback may have issues")
            print("Check your audio device settings")
        
    except Exception as e:
        print(f"❌ Playback error: {e}")
        print()
        print("Possible issues:")
        print("- No audio output device available")
        print("- Audio device permissions")
        print("- Wrong audio device selected")

if __name__ == "__main__":
    test_playback()
