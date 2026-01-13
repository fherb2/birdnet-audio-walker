"""
Audio segmentation and windowing functions.
"""

import numpy as np
import soundfile as sf
from loguru import logger
from config import SEGMENT_LENGTH_SEC, STRIDE_SEC, FADE_LENGTH_SEC


def generate_segments(
    total_duration: float,
    segment_length: float = SEGMENT_LENGTH_SEC,
    stride: float = STRIDE_SEC
) -> list[tuple[float, float]]:
    """
    Generate segment boundaries (start, end) in seconds.
    
    Args:
        total_duration: Total audio duration in seconds
        segment_length: Segment length in seconds
        stride: Stride between segments in seconds
        
    Returns:
        List of (start_time, end_time) tuples
    """
    segments = []
    start = 0.0
    
    while start < total_duration:
        end = min(start + segment_length, total_duration)
        
        # Only add segment if it's at least 1 second long
        if end - start >= 1.0:
            segments.append((start, end))
        
        start += stride
    
    logger.debug(f"Generated {len(segments)} segments for {total_duration:.1f}s audio")
    return segments


def apply_hann_window(
    audio_segment: np.ndarray,
    sample_rate: int,
    fade_length: float = FADE_LENGTH_SEC
) -> np.ndarray:
    """
    Apply Hann window (raised cosine) to audio segment.
    
    Window shape:
    - Fade-In: 0.0s - fade_length (Hann window)
    - Constant: fade_length - (segment_length - fade_length) (multiplier = 1.0)
    - Fade-Out: (segment_length - fade_length) - segment_length (Hann window)
    
    Args:
        audio_segment: Audio data (1D numpy array)
        sample_rate: Sample rate in Hz
        fade_length: Length of fade in/out in seconds
        
    Returns:
        Windowed audio segment
    """
    n_samples = len(audio_segment)
    fade_samples = int(fade_length * sample_rate)
    
    # Create window array (initialize with ones)
    window = np.ones(n_samples)
    
    # Apply Hann window for fade-in
    if fade_samples > 0:
        fade_in = np.hanning(2 * fade_samples)[:fade_samples]
        window[:fade_samples] = fade_in
    
    # Apply Hann window for fade-out
    if fade_samples > 0 and n_samples > fade_samples:
        fade_out = np.hanning(2 * fade_samples)[fade_samples:]
        window[-fade_samples:] = fade_out
    
    # Apply window
    return audio_segment * window


def load_audio_segment(
    wav_path: str,
    start_time: float,
    end_time: float,
    apply_window: bool = True
) -> tuple[np.ndarray, int]:
    """
    Load and optionally window a segment from WAV file.
    
    Args:
        wav_path: Path to WAV file
        start_time: Start time in seconds
        end_time: End time in seconds
        apply_window: Whether to apply Hann window
        
    Returns:
        Tuple of (audio_segment, sample_rate)
        audio_segment is a 1D numpy array (mono)
    """
    # Get file info
    info = sf.info(wav_path)
    sample_rate = info.samplerate
    
    # Calculate frame positions
    start_frame = int(start_time * sample_rate)
    end_frame = int(end_time * sample_rate)
    num_frames = end_frame - start_frame
    
    # Read audio segment
    audio_segment, _ = sf.read(
        wav_path,
        start=start_frame,
        frames=num_frames,
        dtype='float32'
    )
    
    # Convert stereo to mono if needed
    if len(audio_segment.shape) > 1:
        audio_segment = np.mean(audio_segment, axis=1)
    
    # Apply Hann window
    if apply_window:
        audio_segment = apply_hann_window(audio_segment, sample_rate)
    
    return audio_segment, sample_rate
