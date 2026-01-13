#!/usr/bin/env python3
"""
BirdNET Batch Analyzer - Main Program

Analyzes AudioMoth recordings with BirdNET and exports results to ODS.
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
    WORKER_MULTIPLIER,
    PROGRESS_UPDATE_EVERY_N_TASKS
)
from audiomoth_import import extract_metadata
from segmentation import generate_segments
from species_translation import download_species_table
from database import init_database, insert_metadata, export_to_ods
from worker import worker_main
from progress import ProgressDisplay
from birdnet_analyzer import load_model


# Global references
_shutdown_requested = False
_workers = []

def signal_handler(signum, frame):
    """Handle Ctrl+C and other termination signals."""
    global _shutdown_requested, _workers
    logger.warning(f"Received signal {signum}, initiating shutdown...")
    _shutdown_requested = True
    
    # Immediately kill all workers
    for worker in _workers:
        if worker.is_alive():
            logger.info(f"Force-killing {worker.name}")
            worker.kill()

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


def create_tasks(metadata_list: list[dict]) -> list[tuple]:
    """
    Create task list for workers.
    
    Each task is: (file_path, segment_start, segment_end, metadata)
    
    Args:
        metadata_list: List of file metadata
        
    Returns:
        List of tasks
    """
    logger.info("Creating task list...")
    
    tasks = []
    for metadata in metadata_list:
        # Generate segments for this file
        segments = generate_segments(metadata['duration_seconds'])
        
        for segment_start, segment_end in segments:
            task = (
                metadata['path'],
                segment_start,
                segment_end,
                metadata
            )
            tasks.append(task)
    
    logger.info(f"Created {len(tasks)} tasks")
    return tasks


def main():
    """Main program entry point."""
    global _shutdown_requested
    global _workers

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
        "--output", "-o",
        type=str,
        default="results.ods",
        help="Output ODS file (default: results.ods)"
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
    
    # If output path is default, place it in input folder
    if args.output == "results.ods":
        args.output = str(input_folder / "results.ods")
    
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
    
    # Pre-load BirdNET model (avoids parallel downloads in workers)
    logger.info("Pre-loading BirdNET model...")
    try:
        load_model()
        logger.info("BirdNET model cached successfully")
    except Exception as e:
        logger.warning(f"Model pre-load failed (workers will retry): {e}")
    
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
    
    # Create task list
    tasks = create_tasks(metadata_list)
    
    # Setup multiprocessing
    multiprocessing.set_start_method('spawn', force=True)
    num_workers = int(multiprocessing.cpu_count() * WORKER_MULTIPLIER)
    
    logger.info(f"Starting {num_workers} worker processes...")
    
    # Create queues
    task_queue = multiprocessing.Queue()
    result_queue = multiprocessing.Queue()
    
    # Fill task queue
    for task in tasks:
        task_queue.put(task)
    
    # Add poison pills (one per worker)
    for _ in range(num_workers):
        task_queue.put(None)
    
    # Start workers
    workers = []

    _workers = workers  # Make workers accessible to signal handler

    try:
        for i in range(num_workers):
            worker = multiprocessing.Process(
                target=worker_main,
                args=(task_queue, result_queue, db_path, translation_table, args.confidence),
                name=f"Worker-{i+1}"
            )
            worker.start()
            workers.append(worker)
        
        # Progress display
        progress = ProgressDisplay(total_segments=len(tasks), num_workers=num_workers)
        
        # Monitor progress
        completed = 0
        last_update_time = time.time()
        current_file = ""
        
        while completed < len(tasks):
            # Check for shutdown signal
            if _shutdown_requested:
                logger.warning("Shutdown requested, stopping...")
                break
            
            # Check for results with timeout
            try:
                while not result_queue.empty():
                    result = result_queue.get(timeout=0.1)
                    completed += 1
                    current_file = result['filename']
                    
                    # Update progress display periodically
                    if completed % PROGRESS_UPDATE_EVERY_N_TASKS == 0:
                        progress.update(completed, current_file, result.get('worker_id'))
            except:
                pass  # Queue empty or timeout
            
            # Also update every 2 seconds
            if time.time() - last_update_time >= 2.0:
                progress.update(completed, current_file)
                last_update_time = time.time()
            
            time.sleep(0.1)
        
    except KeyboardInterrupt:
        logger.warning("KeyboardInterrupt received, cleaning up...")
        _shutdown_requested = True
    except Exception as e:
        logger.error(f"Error in main processing: {e}")
        _shutdown_requested = True
    finally:
        # Cleanup: Terminate all workers
        logger.info("Cleaning up workers...")
        
        # Clear queues to unblock workers
        try:
            while not task_queue.empty():
                task_queue.get_nowait()
        except:
            pass
        
        try:
            while not result_queue.empty():
                result_queue.get_nowait()
        except:
            pass
        
        # Close queues and cancel join threads
        try:
            task_queue.close()
            task_queue.cancel_join_thread()  # Verhindert Hängen beim Beenden
            result_queue.close()
            result_queue.cancel_join_thread()  # Verhindert Hängen beim Beenden
        except:
            pass
        
        # Terminate workers
        for worker in workers:
            if worker.is_alive():
                logger.debug(f"Terminating {worker.name}")
                worker.terminate()
        
        # Wait for termination (with timeout)
        for worker in workers:
            worker.join(timeout=2.0)
            if worker.is_alive():
                logger.warning(f"{worker.name} did not terminate, killing...")
                worker.kill()
                worker.join(timeout=1.0)
        
        logger.info("All workers cleaned up")
        
        if _shutdown_requested:
            logger.warning("Shutdown requested, exiting without export")
            sys.exit(1)  # Forciert sofortiges Beenden
        

    # Count total detections
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM detections")
    total_detections = cursor.fetchone()[0]
    conn.close()
    
    # Display final progress
    progress.finish(total_detections=total_detections)
    
    # Export to ODS
    logger.info(f"Exporting results to {args.output}...")
    export_to_ods(db_path, args.output)
    
    logger.info("Analysis complete!")
    return 0


if __name__ == "__main__":
    exit(main())
