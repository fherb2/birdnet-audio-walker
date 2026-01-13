"""
Configuration constants for BirdNET Batch Analyzer.
"""

# BirdNET Analysis Parameters
OVERLAP_DURATION_S = 0.0      # Overlap for BirdNET's internal sliding window (0.0 - 2.9s)
BATCH_SIZE = 16               # Number of audio chunks to process simultaneously
TOP_K = None                  # Number of top predictions to return (None = all above threshold)
BANDPASS_FMIN = 0             # Minimum frequency for bandpass filter (Hz)
BANDPASS_FMAX = 15000         # Maximum frequency for bandpass filter (Hz)

# Multiprocessing
WORKER_MULTIPLIER = 0.1       # Number of workers = CPU cores * multiplier

# Device for BirdNET inference
DEVICE = 'GPU'                # 'CPU' or 'GPU' - for GPU use: pip install birdnet[and-cuda]

# BirdNET
DEFAULT_CONFIDENCE = 0.05     # Default minimum confidence threshold

# Species Translation
SPECIES_CACHE_DIR = "/tmp"
SPECIES_CACHE_MAX_AGE_DAYS = 7
SPECIES_TABLE_URL = "https://www.karlincam.cz/de_de/und-sonst-noch/artennamen-uebersetzen/vogelnamen-wissenschaftlich-sortiert"

# Database
SQLITE_LOCK_TIMEOUT = 10.0    # Lock timeout in seconds

# Progress Display
PROGRESS_UPDATE_INTERVAL = 2.0      # Update interval in seconds
PROGRESS_UPDATE_EVERY_N_FILES = 1   # Update after every N completed files