"""
BirdNET analyzer wrapper.
"""


#
# Hinweis zu birdnet_play (oder anderen Auswertezugriffen):
# ---------------------------------------------------------
#
# 1. HDF5-Datei wird schreibend nur in birdnet_analyzer.py verwaltet
# 2. Zum Auslesen später (in birdnet_play):
#    
#    import h5py
#    
#    # Get embedding_idx from database
#    cursor.execute("SELECT embedding_idx FROM detections WHERE id = ?", (det_id,))
#    idx = cursor.fetchone()[0]
#    
#    # Load embedding from HDF5
#    hdf5_path = get_hdf5_path(db_path)
#    with h5py.File(hdf5_path, 'r') as f:
#        embedding = f['embeddings'][idx]  # Shape: (1024,)


from pathlib import Path
from datetime import datetime
from loguru import logger
import birdnet
import numpy as np
from datetime import datetime
import h5py

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
):  # WICHTIG: Return-Type geändert!
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
        AcousticFileEncodingResult object with:
        - embeddings: array of shape (1, n_segments, 1024)
        - segment_duration_s: actual segment duration used
        - overlap_duration_s: actual overlap used
        
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
    
    # Log info
    n_segments = result.embeddings.shape[1]
    logger.info(f"Extracted {n_segments} embeddings "
               f"(segment={result.segment_duration_s}s, overlap={result.overlap_duration_s}s)")
    
    # CHANGED: Return full result object, not just embeddings array
    return result


def create_or_open_hdf5(hdf5_path: str, mode: str = 'a') -> h5py.File:
    """
    Create or open HDF5 file for embedding storage.
    
    Args:
        hdf5_path: Path to HDF5 file
        mode: File mode ('a' = append/create, 'r' = read-only)
        
    Returns:
        h5py.File object (remember to close it!)
    """
    from .config import (
        HDF5_DATASET_NAME,
        EMBEDDING_DIMENSIONS,
        HDF5_DTYPE,
        HDF5_COMPRESSION,
        HDF5_COMPRESSION_LEVEL,
        HDF5_CHUNK_SIZE
    )
    
    hdf5_path = Path(hdf5_path)
    
    # Open or create file
    f = h5py.File(str(hdf5_path), mode)
    
    # Create dataset if it doesn't exist
    if HDF5_DATASET_NAME not in f:
        logger.info(f"Creating HDF5 dataset '{HDF5_DATASET_NAME}' in {hdf5_path.name}")
        
        # Create resizable dataset
        f.create_dataset(
            HDF5_DATASET_NAME,
            shape=(0, EMBEDDING_DIMENSIONS),  # Start with 0 rows
            maxshape=(None, EMBEDDING_DIMENSIONS),  # Unlimited rows
            dtype=HDF5_DTYPE,
            compression=HDF5_COMPRESSION,
            compression_opts=HDF5_COMPRESSION_LEVEL,
            chunks=(HDF5_CHUNK_SIZE, EMBEDDING_DIMENSIONS)
        )
        
        logger.info(f"Dataset created: shape=(0, {EMBEDDING_DIMENSIONS}), dtype={HDF5_DTYPE}")
    
    return f



def write_embeddings_to_hdf5(
    hdf5_path: str,
    embeddings: np.ndarray
) -> int:
    """
    Write embeddings to HDF5 file and return start index.
    
    Args:
        hdf5_path: Path to HDF5 file
        embeddings: Array of shape (n_segments, 1024)
        
    Returns:
        Start index of written embeddings (for referencing from SQLite)
        
    Raises:
        Exception: If write fails
    """
    from .config import HDF5_DATASET_NAME
    
    # Open file in append mode
    with create_or_open_hdf5(hdf5_path, mode='a') as f:
        dataset = f[HDF5_DATASET_NAME]
        
        # Get current size (this will be the start index)
        start_idx = dataset.shape[0]
        
        # Resize dataset to fit new embeddings
        new_size = start_idx + len(embeddings)
        dataset.resize((new_size, dataset.shape[1]))
        
        # Write embeddings
        dataset[start_idx:new_size] = embeddings
        
        logger.debug(f"Wrote {len(embeddings)} embeddings to HDF5 at index {start_idx}-{new_size-1}")
        
        return start_idx



def calculate_segment_times(
    n_segments: int,
    segment_duration_s: float,
    overlap_duration_s: float
) -> list[tuple[float, float]]:
    """
    Calculate start/end times for all segments.
    
    This is the CORRECT calculation that accounts for overlap!
    
    Args:
        n_segments: Number of segments
        segment_duration_s: Duration of each segment (e.g. 3.0s)
        overlap_duration_s: Overlap between segments (e.g. 1.5s)
        
    Returns:
        List of (start_time, end_time) tuples for each segment
        
    Example with overlap_duration_s=1.5:
        Segment 0: (0.0, 3.0)
        Segment 1: (1.5, 4.5)  # NOT (3.0, 6.0)!
        Segment 2: (3.0, 6.0)
    """
    hop_size = segment_duration_s - overlap_duration_s
    
    times = []
    for i in range(n_segments):
        start = i * hop_size
        end = start + segment_duration_s
        times.append((start, end))
    
    return times


def find_needed_segments(
    detections: list[dict],
    segment_times: list[tuple[float, float]]
) -> dict[int, int]:
    """
    Find which segments are needed (have detections).
    
    Uses EXACT time matching - detection time must EXACTLY match segment time!
    This is critical because BirdNET uses the same segmentation for both
    analyze_file() and extract_embeddings(), so times will be identical.
    
    Creates a compact index mapping: old_segment_idx -> new_compact_idx
    
    Args:
        detections: List of detection dicts with 'start_time' and 'end_time'
        segment_times: List of (start, end) tuples for each segment
        
    Returns:
        Dict mapping old_segment_idx (in full array) to new_compact_idx (in filtered array)
        
    Example:
        If segments 5, 12, 13, 20 have detections:
        {5: 0, 12: 1, 13: 2, 20: 3}
    """
    needed_segments = set()
    
    for detection in detections:
        det_start = detection['start_time']
        det_end = detection['end_time']
        
        # Find segment with EXACT time match
        for seg_idx, (seg_start, seg_end) in enumerate(segment_times):
            # EXACT match - same start AND end time
            # BirdNET uses identical segmentation for analyze + encode
            if det_start == seg_start and det_end == seg_end:
                needed_segments.add(seg_idx)
                break  # Found exact match, no need to continue
    
    # Create compact mapping: old_idx -> new_compact_idx
    sorted_needed = sorted(needed_segments)
    index_mapping = {old_idx: new_idx for new_idx, old_idx in enumerate(sorted_needed)}
    
    logger.debug(f"Need {len(index_mapping)} of {len(segment_times)} segments "
                f"(ratio: {len(index_mapping)/len(segment_times)*100:.1f}%)")
    
    return index_mapping

def filter_and_write_embeddings(
    embeddings_array: np.ndarray,
    index_mapping: dict[int, int],
    hdf5_path: str
) -> int:
    """
    Filter embeddings to only needed ones and write to HDF5.
    
    Args:
        embeddings_array: Full embeddings array (n_segments, 1024)
        index_mapping: Dict {old_segment_idx -> new_compact_idx}
        hdf5_path: Path to HDF5 file
        
    Returns:
        Start index in HDF5 where these embeddings begin
    """
    # Get only needed embeddings in compact order
    sorted_indices = sorted(index_mapping.keys())
    filtered_embeddings = embeddings_array[sorted_indices]
    
    logger.debug(f"Filtered embeddings from {len(embeddings_array)} to {len(filtered_embeddings)}")
    
    # Write to HDF5
    start_idx = write_embeddings_to_hdf5(hdf5_path, filtered_embeddings)
    
    return start_idx



def match_embeddings_to_detections(
    detections: list[dict],
    segment_times: list[tuple[float, float]],
    index_mapping: dict[int, int],
    start_idx: int
) -> list[dict]:
    """
    Match detections to HDF5 embedding indices using EXACT time matching.
    
    CRITICAL: Detection time must EXACTLY match segment time!
    BirdNET uses identical segmentation for analyze_file() and extract_embeddings(),
    so a detection at time X will have an embedding at exactly the same time X.
    
    Args:
        detections: List of detection dicts from analyze_file()
        segment_times: List of (start, end) tuples for each segment
        index_mapping: Dict {old_segment_idx -> new_compact_idx}
        start_idx: Start index in HDF5 where this file's embeddings begin
        
    Returns:
        List of detections with 'embedding_idx' key added (integer or None)
        
    Example:
        Detection: 2:03:22.721 - 2:03:25.721
        Segment:   2:03:22.721 - 2:03:25.721  ← EXACT MATCH!
        → Use this segment's embedding
    """
    detections_with_indices = []
    
    logger.debug(f"Matching {len(detections)} detections to embeddings "
                f"(start_idx={start_idx}, n_filtered={len(index_mapping)})")
    
    matched_count = 0
    
    for detection in detections:
        det_start = detection['start_time']
        det_end = detection['end_time']
        
        # Find segment with EXACT time match
        matching_segment_idx = None
        
        for seg_idx, (seg_start, seg_end) in enumerate(segment_times):
            # EXACT match - same start AND end time
            if det_start == seg_start and det_end == seg_end:
                matching_segment_idx = seg_idx
                break  # Found exact match!
        
        detection_copy = detection.copy()
        
        # Check if matching segment is in our filtered set
        if matching_segment_idx is not None and matching_segment_idx in index_mapping:
            # Map to compact index and add HDF5 offset
            compact_idx = index_mapping[matching_segment_idx]
            hdf5_idx = start_idx + compact_idx
            detection_copy['embedding_idx'] = hdf5_idx
            matched_count += 1
        else:
            # This should NOT happen if BirdNET uses identical segmentation!
            logger.warning(
                f"Detection at {det_start:.3f}-{det_end:.3f}s has no exact time match! "
                f"Setting embedding_idx to None."
            )
            detection_copy['embedding_idx'] = None
        
        detections_with_indices.append(detection_copy)
    
    logger.debug(f"Successfully matched {matched_count}/{len(detections)} detections to embeddings")
    
    if matched_count < len(detections):
        logger.warning(f"{len(detections) - matched_count} detections could not be matched!")
    
    return detections_with_indices

