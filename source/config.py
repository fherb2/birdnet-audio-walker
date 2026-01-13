"""
Configuration constants for BirdNET Batch Analyzer.
"""

# Audio Segmentation
SEGMENT_LENGTH_SEC = 3.0      # Length of each segment in seconds
OVERLAP_SEC = 0.7              # Overlap on each side in seconds
STRIDE_SEC = SEGMENT_LENGTH_SEC - OVERLAP_SEC  # = 2.3s stride between segments
FADE_LENGTH_SEC = 0.3          # Hann window fade in/out length in seconds

# Multiprocessing
WORKER_MULTIPLIER = 0.2        # Number of workers = CPU cores * 1.5

# Device for BirdNET inference
DEVICE = 'CPU'  # oder 'GPU' für GPU-Nutzung; for GPU use install 'pip install birdnet[and-cuda]'
                # instead only 'pip install birdnet'

# BirdNET
DEFAULT_CONFIDENCE = 0.05      # Default minimum confidence threshold

# Species Translation
SPECIES_CACHE_DIR = "/tmp"
SPECIES_CACHE_MAX_AGE_DAYS = 7
SPECIES_TABLE_URL = "https://www.karlincam.cz/de_de/und-sonst-noch/artennamen-uebersetzen/vogelnamen-wissenschaftlich-sortiert"

# Database
SQLITE_LOCK_TIMEOUT = 10.0     # Lock timeout in seconds

# Progress Display
PROGRESS_UPDATE_INTERVAL = 2.0  # Update interval in seconds
PROGRESS_UPDATE_EVERY_N_TASKS = 10  # Update after every N completed tasks
