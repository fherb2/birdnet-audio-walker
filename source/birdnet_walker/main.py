#!/usr/bin/env python3
"""
BirdNET Batch Analyzer - Main Program (Simple Sequential + DB Writer)

Single BirdNET instance processes files sequentially.
Separate DB Writer process handles database inserts.
Captures and filters TensorFlow output during prediction.
"""

import argparse
import multiprocessing
import sqlite3
import time
import signal
import sys
import io
import contextlib
from pathlib import Path
from loguru import logger

import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

from .config import (
    DEFAULT_CONFIDENCE,
    QUEUE_SIZE,
    SLEEP_INTERVAL,
    DEFAULT_LANGUAGE,
    BIRDNET_LABELS_PATH
)
from .audiomoth_import import extract_metadata
from .species_translation import download_species_table
from .birdnet_labels import get_available_languages, load_birdnet_labels
from .database import (
    init_database, insert_metadata, db_writer_process, create_indices,
    cleanup_incomplete_files, get_completed_files, set_file_status,
    get_missing_files, check_indices_exist, drop_all_indices
)
from .birdnet_analyzer import load_model, analyze_file
from .progress import ProgressDisplay


# Global references for signal handler
_shutdown_requested = False
_db_writer_process = None


@contextlib.contextmanager
def capture_tf_output():
    """
    Capture TensorFlow stdout/stderr during prediction.
    
    Yields:
        Tuple of (stdout_capture, stderr_capture) StringIO objects
    """
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    try:
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture
        yield stdout_capture, stderr_capture
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def signal_handler(signum, frame):
    """Handle Ctrl+C and other termination signals."""
    global _shutdown_requested, _db_writer_process
    logger.warning(f"Received signal {signum}, initiating shutdown...")
    _shutdown_requested = True
    
    # Terminate DB writer if still running
    if _db_writer_process and _db_writer_process.is_alive():
        logger.info("Force-killing DB-Writer")
        _db_writer_process.kill()


def find_wav_files(input_folder: Path) -> list[Path]:
    """Find all WAV files in input folder."""
    wav_files = []
    for ext in ['*.wav', '*.WAV']:
        wav_files.extend(input_folder.glob(ext))
    
    logger.info(f"Found {len(wav_files)} WAV files in {input_folder}")
    return wav_files


def extract_and_sort_metadata(wav_files: list[Path]) -> list[dict]:
    """Extract metadata from all files and sort by timestamp."""
    logger.info("Extracting metadata from all files...")
    
    metadata_list = []
    for wav_file in wav_files:
        try:
            metadata = extract_metadata(str(wav_file))
            metadata['path'] = str(wav_file)
            metadata_list.append(metadata)
        except Exception as e:
            logger.error(f"Failed to extract metadata from {wav_file.name}: {e}")
    
    metadata_list.sort(key=lambda m: m['timestamp_utc'])
    logger.info(f"Metadata extracted from {len(metadata_list)} files")
    return metadata_list

def find_folders_with_wavs(root_folder: Path, recursive: bool) -> list[Path]:
    """
    Find all folders containing WAV files.
    
    Args:
        root_folder: Root folder to search
        recursive: If True, search recursively
        
    Returns:
        List of folder paths containing WAV files
    """
    folders = set()
    
    if recursive:
        # Find all WAV files recursively
        for ext in ['*.wav', '*.WAV']:
            for wav_file in root_folder.rglob(ext):
                folders.add(wav_file.parent)
    else:
        # Only check root folder
        has_wavs = False
        for ext in ['*.wav', '*.WAV']:
            if list(root_folder.glob(ext)):
                has_wavs = True
                break
        
        if has_wavs:
            folders.add(root_folder)
    
    return sorted(list(folders))


def process_folder(
    folder_path: Path,
    confidence: float,
    no_index: bool,
    translation_table,
    birdnet_labels: dict
) -> tuple[int, int]:
    """
    Process all WAV files in a single folder.
    
    Args:
        folder_path: Path to folder with WAV files
        confidence: Minimum confidence threshold
        no_index: If True, do not create time index
        translation_table: Species translation table
        model: BirdNET model instance
        
    Returns:
        Tuple of (files_processed, total_detections)
    """
    logger.info("=" * 80)
    logger.info(f"Processing folder: {folder_path}")
    logger.info("=" * 80)
    
    # Find WAV files in this folder only
    wav_files = []
    for ext in ['*.wav', '*.WAV']:
        wav_files.extend(folder_path.glob(ext))
    
    if not wav_files:
        logger.warning(f"No WAV files found in {folder_path}")
        return 0, 0
    
    logger.info(f"Found {len(wav_files)} WAV files")
    
    # Database path for this folder
    db_path = folder_path / "birdnet_analysis.db"
    db_existed = db_path.exists()
    
    # Initialize database if needed
    if not db_existed:
        init_database(str(db_path))
    
    # Get list of files already in database
    filenames_in_folder = [f.name for f in wav_files]
    missing_files = get_missing_files(str(db_path), filenames_in_folder)
    
    # Extract metadata for missing files
    metadata_list = []
    if missing_files:
        logger.info(f"Extracting metadata for {len(missing_files)} new files...")
        for wav_file in wav_files:
            if wav_file.name in missing_files:
                try:
                    metadata = extract_metadata(str(wav_file))
                    metadata['path'] = str(wav_file)
                    metadata_list.append(metadata)
                except Exception as e:
                    logger.error(f"Failed to extract metadata from {wav_file.name}: {e}")
        
        metadata_list.sort(key=lambda m: m['timestamp_utc'])
        
        # Insert new file metadata
        logger.info(f"Inserting metadata for {len(metadata_list)} new files...")
        for metadata in metadata_list:
            insert_metadata(db_path, metadata)
    
    # Cleanup incomplete files from previous runs
    logger.info("Checking for incomplete files from previous runs...")
    cleanup_incomplete_files(str(db_path))
    
    # Get list of already completed files
    completed_files = get_completed_files(str(db_path))
    
    # Filter out completed files
    files_to_process = [m for m in metadata_list if m['filename'] not in completed_files]
    
    if completed_files:
        logger.info(f"Found {len(completed_files)} already completed files")
    
    if not files_to_process:
        logger.info("All files in this folder already processed!")
        return 0, 0
    
    logger.info(f"Files to process: {len(files_to_process)}")
    
    # Setup multiprocessing queue
    result_queue = multiprocessing.Queue(maxsize=QUEUE_SIZE)
    
    # Start DB writer process
    logger.info("Starting database writer process...")
    db_writer = multiprocessing.Process(
        target=db_writer_process,
        args=(result_queue, str(db_path), translation_table, birdnet_labels),
        name="DB-Writer"
    )
    db_writer.start()
    
    # Progress display
    progress = ProgressDisplay(total_files=len(files_to_process))
    
    # Processing loop
    completed = 0
    start_time = time.time()
    
    try:
        for metadata in files_to_process:
            if _shutdown_requested:
                logger.warning("Shutdown requested, stopping...")
                break
            
            file_path = metadata['path']
            filename = metadata['filename']
            
            try:
                # Mark file as being processed
                set_file_status(str(db_path), filename, 'processing')
                
                # Capture TensorFlow output during prediction
                with capture_tf_output() as (stdout_capture, stderr_capture):
                    detections = analyze_file(
                        file_path,
                        latitude=metadata.get('gps_lat', 51.1657),
                        longitude=metadata.get('gps_lon', 13.7372),
                        timestamp=metadata['timestamp_utc'],
                        min_confidence=confidence
                    )
                
                # Log all captured output for debugging
                stdout_output = stdout_capture.getvalue()
                stderr_output = stderr_capture.getvalue()
                
                # Always log stderr if present (for debugging GPU issues)
                if stderr_output.strip():
                    logger.debug(f"TensorFlow stderr for {filename}:")
                    for line in stderr_output.strip().split('\n'):
                        logger.debug(f"  {line}")
                
                # Check for critical errors
                has_error = False
                error_keywords = ['error', 'cancelled', 'out of memory', 'oom', 
                                 'illegal memory', 'segmentation fault', 'fatal']
                
                stderr_lower = stderr_output.lower()
                for keyword in error_keywords:
                    if keyword in stderr_lower:
                        # Exclude false positives like "0 error"
                        if keyword == 'error' and '0 error' in stderr_lower:
                            continue
                        
                        logger.error(f"Critical error detected in {filename}: {keyword}")
                        logger.error("Full stderr output:")
                        logger.error(stderr_output)
                        has_error = True
                        break
                
                # Log warnings
                if "warning" in stderr_lower:
                    logger.warning(f"TensorFlow warnings for {filename}")
                
                # Log debug stdout
                if stdout_output.strip():
                    logger.debug(f"TensorFlow stdout for {filename}: {stdout_output.strip()}")
                
                # Skip file if critical error occurred
                if has_error:
                    logger.error(f"Skipping {filename} due to critical error")
                    set_file_status(str(db_path), filename, 'failed', f'TensorFlow error: {stderr_output[:200]}')
                    completed += 1
                    continue
                
                # Prepare data package for DB writer
                data_package = {
                    'filename': filename,
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
                progress.update(completed, filename, elapsed)
                
            except Exception as e:
                logger.error(f"Error processing {filename}: {e}")
                # Mark file as failed
                set_file_status(str(db_path), filename, 'failed', str(e))
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
    
    except Exception as e:
        logger.error(f"Error in processing: {e}")
    finally:
        # Cleanup: Terminate DB writer
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
    
    # Count total detections
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM detections")
    total_detections = cursor.fetchone()[0]
    conn.close()
    
    # Display final progress for this folder
    if completed > 0:
        elapsed = time.time() - start_time
        progress.finish(total_files=completed, total_detections=total_detections, elapsed=elapsed)
    
    # Index management
    if no_index:
        # User requested no indices - drop all if they exist
        if check_indices_exist(str(db_path)):
            logger.info("Removing all indices (--no-index specified)")
            drop_all_indices(str(db_path))
    else:
        # User wants indices
        create_indices(str(db_path))
    
    logger.info(f"Folder complete: {folder_path}")
    logger.info(f"Total detections in database: {total_detections}")
    
    return completed, total_detections

def main():
    """Main program entry point."""
    global _shutdown_requested
    global _db_writer_process
    
    # Try to get available languages for help text
    try:
        if BIRDNET_LABELS_PATH.exists():
            available_langs = get_available_languages()
            langs_text = f"Available: {', '.join(available_langs)}"
        else:
            langs_text = "Available languages will be shown after BirdNET installation"
    except Exception:
        langs_text = "Available languages will be shown after BirdNET installation"

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
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Process all subdirectories recursively"
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Do not create time-based index (or remove existing one if data added)"
    )
    parser.add_argument(
        "--lang", "-l",
        type=str,
        default=DEFAULT_LANGUAGE,
        metavar="CODE",
        help=f"Language code for species names (default: {DEFAULT_LANGUAGE}). {langs_text}"
    )
    
    args = parser.parse_args()
    
    # Validate input folder
    input_folder = Path(args.input_folder)
    if not input_folder.exists():
        logger.error(f"Input folder does not exist: {input_folder}")
        return 1
    
    # Find folders to process
    folders_to_process = find_folders_with_wavs(input_folder, args.recursive)
    
    if not folders_to_process:
        logger.error("No folders with WAV files found")
        return 1
    
    logger.info(f"Found {len(folders_to_process)} folder(s) with WAV files")
    
    # Download species translation table (once for all folders)
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
    
    # Check if labels directory exists
    if not BIRDNET_LABELS_PATH.exists():
        logger.error(f"BirdNET labels directory not found: {BIRDNET_LABELS_PATH}")
        logger.error("")
        logger.error("Please run the setup script first:")
        logger.error("  python setup_birdnet.py")
        logger.error("")
        return 1
    
    # Get available languages (might be already loaded for help text)
    try:
        available_languages = available_langs if 'available_langs' in locals() and available_langs else get_available_languages()
    except Exception:
        available_languages = get_available_languages()
    
    if not available_languages:
        logger.error("No language files found in BirdNET labels directory")
        return 1
    
    logger.info(f"Available languages: {', '.join(available_languages)}")
    
    # Validate selected language
    if args.lang not in available_languages:
        logger.error(f"Language '{args.lang}' not available")
        logger.error(f"Available languages: {', '.join(available_languages)}")
        return 1
    
    logger.info(f"Selected language: {args.lang}")
    
    # Load BirdNET labels for selected language
    logger.info(f"Loading BirdNET labels for language '{args.lang}'...")
    birdnet_labels = load_birdnet_labels(args.lang)
    
    if not birdnet_labels:
        logger.error(f"Failed to load BirdNET labels for language '{args.lang}'")
        return 1
    
    logger.info(f"Loaded {len(birdnet_labels)} species names in '{args.lang}'")
    
    # Setup multiprocessing
    multiprocessing.set_start_method('spawn', force=True)
    
    # Process each folder
    total_files_processed = 0
    total_detections_all = 0
    
    for idx, folder in enumerate(folders_to_process, 1):
        logger.info("")
        logger.info(f"Processing folder {idx}/{len(folders_to_process)}")
        
        try:
            files_processed, detections = process_folder(
                folder,
                args.confidence,
                args.no_index,
                translation_table,
                birdnet_labels
            )
            
            total_files_processed += files_processed
            total_detections_all += detections
            
        except KeyboardInterrupt:
            logger.warning("KeyboardInterrupt received, stopping...")
            break
        except Exception as e:
            logger.error(f"Error processing folder {folder}: {e}")
            # Continue with next folder
    
    # Final summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("All folders processed!")
    logger.info("=" * 80)
    logger.info(f"Folders processed: {len(folders_to_process)}")
    logger.info(f"Total files analyzed: {total_files_processed}")
    logger.info(f"Total detections: {total_detections_all}")
    logger.info("=" * 80)
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())