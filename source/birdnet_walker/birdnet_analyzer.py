"""
BirdNET analyzer wrapper.
"""

from pathlib import Path
from datetime import datetime
from loguru import logger
import birdnet
import numpy as np
from datetime import datetime

from .config import (
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
    ) # return data type: AcousticPredictionResultBase
    
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


def extract_embeddings(
    file_path: str | Path,
    overlap_duration_s: float = 0.0,
    batch_size: int = 32
) -> np.ndarray:
    """
    Extract embeddings for entire audio file using BirdNET.
    
    This function extracts 1024-dimensional feature vectors for all 3-second
    segments in the audio file. These embeddings can be used for clustering,
    similarity search, and false-positive detection.
    
    Args:
        file_path: Path to WAV file
        overlap_duration_s: Overlap for segments (should match analyze_file)
        batch_size: Batch size for GPU processing
        
    Returns:
        numpy array of shape (n_segments, 1024) with dtype float32
        
    Raises:
        Exception: If embedding extraction fails
    """
    model = load_model()
    
    logger.info(f"Extracting embeddings from {Path(file_path).name}...")
    
    # Call BirdNET encode method
    result = model.encode(
        str(file_path),
        device=DEVICE,
        batch_size=batch_size,
        overlap_duration_s=overlap_duration_s
    )
    
    # result.embeddings shape: (1, n_segments, 1024)
    # We want: (n_segments, 1024)
    embeddings = result.embeddings[0]  # Remove batch dimension
    
    logger.info(f"Extracted {len(embeddings)} embeddings (shape: {embeddings.shape})")
    
    return embeddings


def match_embeddings_to_detections(
    detections: list[dict],
    embeddings: np.ndarray,
    segment_duration_s: float = 3.0
) -> list[dict]:
    """
    Match embeddings to detections based on segment timing.
    
    BirdNET's encode() returns embeddings for ALL segments in the audio file,
    while predict() only returns detections above confidence threshold. This
    function matches each detection to its corresponding embedding vector.
    
    Matching logic:
        detection_start_time (seconds) → segment_index = int(start_time / 3.0)
        → embedding = embeddings[segment_index]
    
    Args:
        detections: List of detection dicts from analyze_file()
                   Each dict must have 'start_time' key (seconds from file start)
        embeddings: Array of shape (n_segments, 1024) from extract_embeddings()
        segment_duration_s: Duration of each BirdNET segment (default 3.0s)
        
    Returns:
        List of detections with 'embedding' key added (numpy array or None)
        
    Example:
        >>> detections = [{'start_time': 12.5, ...}, {'start_time': 15.2, ...}]
        >>> embeddings = np.array([[...], [...], ...])  # shape (100, 1024)
        >>> result = match_embeddings_to_detections(detections, embeddings)
        >>> result[0]['embedding'].shape
        (1024,)
    """
    detections_with_embeddings = []
    
    n_segments = len(embeddings)
    logger.debug(f"Matching {len(detections)} detections to {n_segments} embeddings")
    
    for detection in detections:
        # Calculate segment index from detection start time
        detection_start = detection['start_time']  # Seconds from file start
        segment_idx = int(detection_start / segment_duration_s)
        
        # Safety check: segment index must be within embeddings array
        if segment_idx >= n_segments:
            logger.warning(
                f"Segment index {segment_idx} out of range for {n_segments} "
                f"embeddings (detection at {detection_start:.1f}s). Setting embedding to None."
            )
            detection_copy = detection.copy()
            detection_copy['embedding'] = None
            detections_with_embeddings.append(detection_copy)
            continue
        
        # Get embedding for this segment
        embedding = embeddings[segment_idx]
        
        # Add embedding to detection (as numpy array)
        detection_copy = detection.copy()
        detection_copy['embedding'] = embedding
        detections_with_embeddings.append(detection_copy)
    
    logger.debug(f"Successfully matched {len(detections_with_embeddings)} detections")
    
    return detections_with_embeddings
