"""
BirdNET analyzer wrapper.
"""

from pathlib import Path
from datetime import datetime
from loguru import logger
import birdnet

from config import (
    DEVICE,
    OVERLAP_DURATION_S,
    BATCH_SIZE,
    TOP_K,
    BANDPASS_FMIN,
    BANDPASS_FMAX
)


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
        _model = birdnet.load("acoustic", "2.4", "pb")
        logger.info("BirdNET model loaded")
    return _model


def analyze_file(
    file_path: str | Path,
    latitude: float,
    longitude: float,
    timestamp: datetime,
    min_confidence: float = 0.25
) -> list[dict]:
    """
    Analyze entire audio file with BirdNET.
    
    BirdNET handles segmentation and sliding windows internally.
    
    Args:
        file_path: Path to WAV file
        latitude: GPS latitude (for species filtering)
        longitude: GPS longitude (for species filtering)
        timestamp: Recording timestamp (for species filtering)
        min_confidence: Minimum confidence threshold
        
    Returns:
        List of detections, each dict with:
        - 'scientific_name': str
        - 'common_name': str (English)
        - 'confidence': float
        - 'start_time': float (seconds from file start)
        - 'end_time': float (seconds from file start)
    """
    model = load_model()
    
    # Run BirdNET prediction on entire file
    # BirdNET handles segmentation internally with overlap
    result = model.predict(
        str(file_path),
        device=DEVICE,
        overlap_duration_s=OVERLAP_DURATION_S,
        batch_size=BATCH_SIZE,
        top_k=TOP_K,
        bandpass_fmin=BANDPASS_FMIN,
        bandpass_fmax=BANDPASS_FMAX,
        default_confidence_threshold=min_confidence
    )
    
    # Convert to DataFrame
    df = result.to_dataframe()
    
    # Convert to detections list
    detections = []
    
    for idx, row in df.iterrows():
        confidence = float(row['confidence'])
        
        # Parse species_name format: "Scientific_Common Name"
        species_name = row["species_name"]
        if '_' in species_name:
            scientific_name, common_name = species_name.split('_', 1)
        else:
            # Fallback if format is unexpected
            scientific_name = species_name
            common_name = species_name
        
        # Parse time values (should be floats already)
        start_time = float(row["start_time"]) if row["start_time"] is not None else 0.0
        end_time = float(row["end_time"]) if row["end_time"] is not None else 0.0
        
        detections.append({
            'scientific_name': scientific_name,
            'common_name': common_name,
            'confidence': confidence,
            'start_time': start_time,
            'end_time': end_time
        })
    
    logger.info(f"BirdNET found {len(detections)} detections in {Path(file_path).name}")
    return detections