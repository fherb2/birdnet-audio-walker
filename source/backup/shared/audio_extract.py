"""
Audio snippet extraction from WAV files.
"""

import wave
import numpy as np
from pathlib import Path
from typing import Tuple, Dict
from datetime import datetime
from loguru import logger


def calculate_snippet_offsets(
    detection: Dict,
    pm_seconds: float
) -> Tuple[float, float]:
    """
    Calculate start/end offsets for snippet extraction with PM buffer.
    
    Args:
        detection: Detection dict from query_detections() with:
            - file_timestamp_utc: File start timestamp (str ISO format)
            - segment_start_utc: Detection start timestamp (str ISO format)
            - segment_end_utc: Detection end timestamp (str ISO format)
            - file_duration_seconds: Total file duration (float)
        pm_seconds: Plus/Minus buffer in seconds
        
    Returns:
        Tuple of (start_offset, end_offset) in seconds from file start.
        Automatically clipped to [0, file_duration].
        
    Example:
        File starts at 08:32:00, duration 60s
        Detection at 08:32:21.5 - 08:32:24.5 (offset 21.5 - 24.5)
        PM = 2.0s
        -> Returns (19.5, 26.5)
    """
    # Parse timestamps
    file_timestamp = datetime.fromisoformat(detection['file_timestamp_utc'])
    segment_start = datetime.fromisoformat(detection['segment_start_utc'])
    segment_end = datetime.fromisoformat(detection['segment_end_utc'])
    file_duration = detection['file_duration_seconds']
    
    # Calculate base offsets (in seconds from file start)
    segment_start_offset = (segment_start - file_timestamp).total_seconds()
    segment_end_offset = (segment_end - file_timestamp).total_seconds()
    
    # Apply PM buffer
    start_offset = segment_start_offset - pm_seconds
    end_offset = segment_end_offset + pm_seconds
    
    # Clip to file boundaries
    start_offset = max(0.0, start_offset)
    end_offset = min(file_duration, end_offset)
    
    logger.debug(
        f"Snippet offsets: {start_offset:.2f}s - {end_offset:.2f}s "
        f"(PM={pm_seconds}s, clipped to file boundaries)"
    )
    
    return start_offset, end_offset


def extract_snippet(
    wav_path: Path,
    start_offset_seconds: float,
    end_offset_seconds: float
) -> Tuple[np.ndarray, int]:
    """
    Extract audio snippet from WAV file.
    
    Args:
        wav_path: Path to WAV file
        start_offset_seconds: Start offset in seconds from file start
        end_offset_seconds: End offset in seconds from file start
        
    Returns:
        Tuple of (audio_data, sample_rate)
        - audio_data: numpy array with audio samples (int16, mono or stereo)
        - sample_rate: Sample rate in Hz
        
    Raises:
        FileNotFoundError: If WAV file doesn't exist
        ValueError: If offsets are invalid or outside file duration
    """
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV file not found: {wav_path}")
    
    # Open WAV file
    with wave.open(str(wav_path), 'rb') as wav:
        sample_rate = wav.getframerate()
        n_channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        total_frames = wav.getnframes()
        total_duration = total_frames / sample_rate
        
        # Validate offsets
        if start_offset_seconds < 0 or end_offset_seconds < 0:
            raise ValueError(f"Negative offsets not allowed: {start_offset_seconds}, {end_offset_seconds}")
        
        if start_offset_seconds >= total_duration:
            raise ValueError(
                f"Start offset {start_offset_seconds}s exceeds file duration {total_duration}s"
            )
        
        if end_offset_seconds > total_duration:
            logger.warning(
                f"End offset {end_offset_seconds}s exceeds file duration {total_duration}s, "
                f"clipping to {total_duration}s"
            )
            end_offset_seconds = total_duration
        
        if start_offset_seconds >= end_offset_seconds:
            raise ValueError(
                f"Start offset {start_offset_seconds}s >= end offset {end_offset_seconds}s"
            )
        
        # Calculate frame positions
        start_frame = int(start_offset_seconds * sample_rate)
        end_frame = int(end_offset_seconds * sample_rate)
        n_frames = end_frame - start_frame
        
        # Seek to start position
        wav.setpos(start_frame)
        
        # Read audio data
        raw_data = wav.readframes(n_frames)
        
        # Convert to numpy array
        if sample_width == 1:
            dtype = np.uint8
        elif sample_width == 2:
            dtype = np.int16
        elif sample_width == 4:
            dtype = np.int32
        else:
            raise ValueError(f"Unsupported sample width: {sample_width}")
        
        audio_data = np.frombuffer(raw_data, dtype=dtype)
        
        # Reshape for multi-channel audio
        if n_channels > 1:
            audio_data = audio_data.reshape(-1, n_channels)
        
        logger.debug(
            f"Extracted snippet: {start_offset_seconds:.2f}s - {end_offset_seconds:.2f}s "
            f"({n_frames} frames, {n_channels} channels, {sample_rate}Hz)"
        )
        
        return audio_data, sample_rate
