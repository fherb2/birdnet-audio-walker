"""
BirdNET analyzer wrapper.
"""

import os
import tempfile
import numpy as np
import soundfile as sf
from datetime import datetime
from loguru import logger
import birdnet

from config import DEVICE

# Global model instance (loaded once per worker process)
_model = None


def load_model():
    """
    Load BirdNET model (called once per worker process).
    
    Returns:
        BirdNET model instance
    """
    global _model
    if _model is None:
        logger.info("Loading BirdNET model...")
        _model = birdnet.load("acoustic", "2.4", "pb")  # "pb" für ProtoBuf ist korrekt!! S
        logger.info("BirdNET model loaded")
    return _model



def analyze_segment(
    audio_segment: np.ndarray,
    sample_rate: int,
    latitude: float,
    longitude: float,
    timestamp: datetime,
    min_confidence: float = 0.25
) -> list[dict]:
    """
    Analyze audio segment with BirdNET.
    
    Args:
        audio_segment: Audio data (1D numpy array)
        sample_rate: Sample rate in Hz
        latitude: GPS latitude (TODO: use for species filtering)
        longitude: GPS longitude (TODO: use for species filtering)
        timestamp: Recording timestamp (TODO: use for species filtering)
        min_confidence: Minimum confidence threshold
        
    Returns:
        List of detections, each dict with:
        - 'scientific_name': str
        - 'common_name': str (English)
        - 'confidence': float
        - 'start_time': float (relative to segment, in seconds)
        - 'end_time': float (relative to segment, in seconds)
    """
    model = load_model()
    
    # Save audio to temporary file (BirdNET expects file path)
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
        tmp_path = tmp_file.name
        sf.write(tmp_path, audio_segment, sample_rate)
    
    try:
        # Run BirdNET prediction
        # Result is a DataFrame-like object with columns:
        # input, start_time, end_time, species_name, confidence
        result = model.predict(tmp_path, device=DEVICE)

        # Convert to DataFrame
        df = result.to_dataframe()

        # Filter and convert to detections list
        detections = []

        for idx, row in df.iterrows():
            confidence = float(row['confidence'])
            
            # Apply confidence threshold
            if confidence < min_confidence:
                continue
            
            # Parse species_name format: "Scientific_Common Name"
            species_name = row["species_name"]
            if '_' in species_name:
                scientific_name, common_name = species_name.split('_', 1)
            else:
                # Fallback if format is unexpected
                scientific_name = species_name
                common_name = species_name
            
            # Parse time strings (format: "HH:MM:SS.ss" or just seconds)
            # Times are relative to the audio file (our segment), so already correct
            start_time = _parse_time_string(row["start_time"])
            end_time = _parse_time_string(row["end_time"])
            
            detections.append({
                'scientific_name': scientific_name,
                'common_name': common_name,
                'confidence': confidence,
                'start_time': start_time,
                'end_time': end_time
            })
        
        logger.debug(f"BirdNET found {len(detections)} detections")
        return detections
        
    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except:
            pass

def _parse_time_string(time_value) -> float:
    """
    Parse time value to seconds.
    
    Args:
        time_value: Time as float, int, or string in format "HH:MM:SS.ss"
        
    Returns:
        Time in seconds as float
    """
    # If already numeric, return as-is
    if isinstance(time_value, (int, float)):
        return float(time_value)
    
    # Parse string format "HH:MM:SS.ss"
    time_str = str(time_value)
    
    if ':' in time_str:
        parts = time_str.split(':')
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 2:
            minutes = int(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds
    
    # Fallback: try to parse as float
    try:
        return float(time_str)
    except:
        logger.warning(f"Could not parse time value: {time_value}")
        return 0.0        

