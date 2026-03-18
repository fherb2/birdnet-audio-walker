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
    min_confidence: float = 0.25,
    device: str = 'cpu',
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
        device=device,
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
    batch_size: int = 32,
    device: str = 'cpu',
):
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
        device=device,
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
    filename: str,
    file_start_utc: datetime,
    embeddings_array: np.ndarray,
    segment_times: list[tuple[float, float]],
    delta_t: float,
    step_width: float,
) -> None:
    """
    Write embeddings for one audio file into HDF5, one group per file.

    Segments without detections are written as zero vectors.
    The group is deleted and rewritten if it already exists (Rebuild case).

    Args:
        hdf5_path:       Path to HDF5 file
        filename:        Audio filename (used as group name)
        file_start_utc:  UTC start time of the audio file
        embeddings_array: Full embeddings array shape (n_segments, 1024)
        segment_times:   List of (start_time, end_time) tuples (seconds from file start)
        delta_t:         Segment duration in seconds (e.g. 3.0)
        step_width:      Hop size in seconds (segment_duration_s - overlap_duration_s)
    """
    from .config import HDF5_DATASET_NAME, HDF5_COMPRESSION, HDF5_COMPRESSION_LEVEL

    n_segments = len(segment_times)

    with create_or_open_hdf5(hdf5_path, mode='a') as f:
        # Delete existing group for this file (Rebuild case)
        if filename in f:
            del f[filename]
            logger.debug(f"HDF5: deleted existing group '{filename}'")

        grp = f.create_group(filename)

        # Attributes
        grp.attrs['filename']   = filename
        grp.attrs['file_start'] = file_start_utc.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        grp.attrs['delta_t']    = delta_t
        grp.attrs['step_width'] = step_width

        # Write full embeddings array (zero vectors for empty segments)
        grp.create_dataset(
            HDF5_DATASET_NAME,
            data=embeddings_array,
            dtype='float32',
            compression=HDF5_COMPRESSION,
            compression_opts=HDF5_COMPRESSION_LEVEL,
        )

    logger.debug(
        f"HDF5: wrote {n_segments} segments for '{filename}' "
        f"(delta_t={delta_t}s, step_width={step_width}s)"
    )


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





