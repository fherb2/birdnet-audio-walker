"""
Configuration constants for BirdNET Batch Analyzer.
"""

from pathlib import Path

# BirdNET Analysis Parameters
OVERLAP_DURATION_S = 0.0      # Overlap for BirdNET's internal sliding window (0.0 - 2.9s)
BATCH_SIZE = 32              # Number of audio chunks to process simultaneously (optimal value

TOP_K = None                  # Number of top predictions to return (None = all above threshold)
BANDPASS_FMIN = 0             # Minimum frequency for bandpass filter (Hz)
BANDPASS_FMAX = 15000         # Maximum frequency for bandpass filter (Hz)

# GPU is always used (no CPU mode)
DEVICE = 'GPU'

# Queue Configuration
QUEUE_SIZE = 2                # Maximum number of result packages in queue
SLEEP_INTERVAL = 0.1          # Sleep time in seconds when queue is full

# BirdNET
DEFAULT_CONFIDENCE = 0.09     # Default minimum confidence threshold

# Species Translation
SPECIES_CACHE_DIR = "/tmp"
SPECIES_CACHE_MAX_AGE_DAYS = 7
SPECIES_TABLE_URL = "https://www.karlincam.cz/de_de/und-sonst-noch/artennamen-uebersetzen/vogelnamen-wissenschaftlich-sortiert"

# Index Management
INDEX_NAMES = [
    "idx_detections_segment_start",  # Time-based index
    "idx_detections_species",         # Species-based index
    "idx_detections_filename"         # Filename-based index
]

# BirdNET Labels
BIRDNET_LABELS_PATH = Path.home() / ".local/share/birdnet/acoustic-models/v2.4/pb/labels"
DEFAULT_LANGUAGE = "de"