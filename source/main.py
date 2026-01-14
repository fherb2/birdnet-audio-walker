#!/usr/bin/env python3
"""
BirdNET Batch Analyzer - Main Program (Single GPU Process + DB Writer)

Analyzes AudioMoth recordings with BirdNET and stores results in SQLite.
"""

import argparse
import multiprocessing
import sqlite3
import time
import signal
import sys
from pathlib import Path
from loguru import logger

import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

from config import (
    DEFAULT_CONFIDENCE,
    QUEUE_SIZE,
    SLEEP_INTERVAL
)
from audiomoth_import import extract_metadata
from species_translation import download_species_table
from database import init_database, insert_metadata, db_writer_process, create_indices
from birdnet_analyzer import load_model, analyze_file
from progress import ProgressDisplay


# Global references for signal handler
_shutdown_requested = False
_db_writer_process = None


def signal_handler(signum, frame):
    """Handle Ctrl+C and other termination signals."""
    global _shutdown_requested, _db_writer_process
    logger.warning(f"Received signal {signum}, initiating shutdown...")
    _shutdown_requested = True
    
    # Terminate DB writer if still running
    if _db_writer_process and _db_writer_process.is_alive():
        logger.info("Terminating DB writer process...")
        _db_writer_process.terminate()
        _db_writer_process.join(timeout=2.0)
        if _db_writer_process.is_alive():
            _db_writer_process.kill()


def find_wav_files(input_folder: Path) -> list[Path]:
    """
    Find all WAV files in input folder.
    
    Args:
        input_folder: Path to input folder
        
    Returns:
        List of WAV file paths
    """
    wav_files = []
    for ext in ['*.wav', '*.WAV']:
        wav_files.extend(input_folder.glob(ext))
    
    logger.info(f"Found {len(wav_files)} WAV files in {input_folder}")
    return wav_files


def extract_and_sort_metadata(wav_files: list[Path]) -> list[dict]:
    """
    Extract metadata from all files and sort by timestamp.
    
    Args:
        wav_files: List of WAV file paths
        
    Returns:
        List of metadata dicts, sorted by timestamp
    """
    logger.info("Extracting metadata from all files...")
    
    metadata_list = []
    for wav_file in wav_files:
        try:
            metadata = extract_metadata(str(wav_file))
            metadata['path'] = str(wav_file)
            metadata_list.append(metadata)
        except Exception as e:
            logger.error(f"Failed to extract metadata from {wav_file.name}: {e}")
    
    # Sort by timestamp
    metadata_list.sort(key=lambda m: m['timestamp_utc'])
    
    logger.info(f"Metadata extracted from {len(metadata_list)} files")
    return metadata_list


def main():
    """Main program entry point."""
    global _shutdown_requested
    global _db_writer_process

    # Setup logging
    logger.add(
        "birdnet_analyzer.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG"
    )

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="BirdNET Batch Analyzer - Analyze AudioMoth recordings"
    )
    parser.add_argument(
        "input_folder",
        type=str,
        help="Path to folder containing WAV files"
    )
    parser.add_argument(
        "--confidence", "-c",
        type=float,
        default=DEFAULT_CONFIDENCE,
        help=f"Minimum confidence threshold (default: {DEFAULT_CONFIDENCE})"
    )
    
    args = parser.parse_args()
    
    # Validate input folder
    input_folder = Path(args.input_folder)
    if not input_folder.exists():
        logger.error(f"Input folder does not exist: {input_folder}")
        return 1
    
    # Find WAV files
    wav_files = find_wav_files(input_folder)
    if not wav_files:
        logger.error("No WAV files found")
        return 1
    
    # Extract and sort metadata
    metadata_list = extract_and_sort_metadata(wav_files)
    if not metadata_list:
        logger.error("No valid WAV files with metadata")
        return 1

    # Download species translation table
    logger.info("Loading species translation table...")
    translation_table = download_species_table()
    
    # Check if BirdNET model is installed
    logger.info("Checking BirdNET model installation...")
    model_path = Path.home() / ".local/share/birdnet/acoustic-models/v2.4/pb/model-fp32"

    if not model_path.exists() or not (model_path / "saved_model.pb").exists():
        logger.error("BirdNET model not found!")
        logger.error("")
        logger.error("Please run the setup script first:")
        logger.error("  python setup_birdnet.py")
        logger.error("")
        return 1

    logger.info("BirdNET model found ✓")
    
    # Initialize database in input folder
    db_path = input_folder / "birdnet_analysis.db"

    # Delete old database if exists
    if db_path.exists():
        logger.info(f"Removing old database: {db_path}")
        db_path.unlink()

    init_database(str(db_path))
    
    # Insert file metadata
    logger.info("Inserting file metadata into database...")
    for metadata in metadata_list:
        insert_metadata(db_path, metadata)
    
    # Setup multiprocessing for Queue
    multiprocessing.set_start_method('spawn', force=True)
    
    # Create result queue with limited size
    result_queue = multiprocessing.Queue(maxsize=QUEUE_SIZE)
    
    # Start DB writer process
    logger.info("Starting database writer process...")
    db_writer = multiprocessing.Process(
        target=db_writer_process,
        args=(result_queue, db_path, translation_table),
        name="DB-Writer"
    )
    db_writer.start()
    _db_writer_process = db_writer
    
    # Load BirdNET model (once for entire run)
    logger.info("Loading BirdNET model...")
    model = load_model()
    logger.info("BirdNET model loaded ✓")
    
    # Progress display
    progress = ProgressDisplay(total_files=len(metadata_list))
    
    # Main processing loop
    completed = 0
    start_time = time.time()
    
    try:
        for metadata in metadata_list:
            # Check for shutdown signal
            if _shutdown_requested:
                logger.warning("Shutdown requested, stopping...")
                break
            
            file_path = metadata['path']
            
            try:
                # Analyze file with BirdNET (blocking call)
                detections = analyze_file(
                    file_path,
                    latitude=metadata.get('gps_lat', 51.1657),
                    longitude=metadata.get('gps_lon', 13.7372),
                    timestamp=metadata['timestamp_utc'],
                    min_confidence=args.confidence
                )
                
                # Prepare data package for DB writer
                data_package = {
                    'filename': metadata['filename'],
                    'metadata': metadata,
                    'detections': detections
                }
                
                # Non-blocking queue put with wait loop
                while True:
                    if _shutdown_requested:
                        break
                    
                    try:
                        result_queue.put(data_package, block=False)
                        break
                    except:  # Queue full
                        time.sleep(SLEEP_INTERVAL)
                
                completed += 1
                
                # Update progress
                elapsed = time.time() - start_time
                progress.update(completed, metadata['filename'], elapsed)
                
            except Exception as e:
                logger.error(f"Error processing {metadata['filename']}: {e}")
                completed += 1
        
        # Send poison pill to DB writer
        logger.info("Sending shutdown signal to DB writer...")
        result_queue.put(None)
        
        # Wait for DB writer to finish
        logger.info("Waiting for DB writer to complete...")
        db_writer.join(timeout=60.0)
        
        if db_writer.is_alive():
            logger.warning("DB writer did not finish in time, terminating...")
            db_writer.terminate()
            db_writer.join(timeout=2.0)
    
    except KeyboardInterrupt:
        logger.warning("KeyboardInterrupt received, cleaning up...")
        _shutdown_requested = True
    except Exception as e:
        logger.error(f"Error in main processing: {e}")
        _shutdown_requested = True
    finally:
        # Cleanup
        if db_writer.is_alive():
            logger.info("Terminating DB writer...")
            db_writer.terminate()
            db_writer.join(timeout=2.0)
            if db_writer.is_alive():
                db_writer.kill()
        
        # Close queue
        try:
            result_queue.close()
            result_queue.cancel_join_thread()
        except:
            pass
        
        if _shutdown_requested:
            logger.warning("Shutdown requested, exiting without final steps")
            sys.exit(1)
    
    # Count total detections
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM detections")
    total_detections = cursor.fetchone()[0]
    conn.close()
    
    # Display final progress
    elapsed = time.time() - start_time
    progress.finish(total_files=completed, total_detections=total_detections, elapsed=elapsed)
    
    # Create indices for fast queries
    logger.info("Creating database indices...")
    create_indices(db_path)
    
    logger.info("Analysis complete!")
    logger.info(f"Results saved in: {db_path}")
    return 0


if __name__ == "__main__":
    exit(main())