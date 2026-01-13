"""
Worker process for parallel audio analysis.
"""

import multiprocessing
from datetime import timedelta
from loguru import logger
import pandas as pd

from birdnet_analyzer import analyze_file
from species_translation import translate_species_name
from database import insert_detection


def worker_main(
    task_queue: multiprocessing.Queue,
    result_queue: multiprocessing.Queue,
    db_path: str,
    translation_table: pd.DataFrame,
    min_confidence: float
):
    """
    Worker process main function.
    
    Args:
        task_queue: Queue with tasks (file_path, metadata)
        result_queue: Queue for progress updates
        db_path: Path to SQLite database
        translation_table: Species translation table
        min_confidence: Minimum confidence threshold
    """
    worker_id = multiprocessing.current_process().name
    logger.info(f"Worker {worker_id} started")
    
    # Process tasks until poison pill
    while True:
        task = task_queue.get()
        
        # Check for poison pill (None = shutdown signal)
        if task is None:
            logger.info(f"Worker {worker_id} received shutdown signal")
            break
        
        file_path, metadata = task
        
        try:
            # Analyze entire file with BirdNET
            # BirdNET handles segmentation internally
            detections = analyze_file(
                file_path,
                latitude=metadata.get('gps_lat', 51.1657),
                longitude=metadata.get('gps_lon', 13.7372),
                timestamp=metadata['timestamp_utc'],
                min_confidence=min_confidence
            )
            
            # Process each detection
            for detection in detections:
                # Translate species names
                names = translate_species_name(
                    detection['scientific_name'],
                    translation_table
                )
                
                # Calculate absolute timestamps from detection times
                detection_start_seconds = detection['start_time']
                detection_end_seconds = detection['end_time']
                
                detection_start_utc = metadata['timestamp_utc'] + timedelta(seconds=detection_start_seconds)
                detection_end_utc = metadata['timestamp_utc'] + timedelta(seconds=detection_end_seconds)
                detection_start_local = metadata['timestamp_local'] + timedelta(seconds=detection_start_seconds)
                detection_end_local = metadata['timestamp_local'] + timedelta(seconds=detection_end_seconds)
                
                # Insert into database
                insert_detection(
                    db_path=db_path,
                    filename=metadata['filename'],
                    segment_start_utc=detection_start_utc,
                    segment_start_local=detection_start_local,
                    segment_end_utc=detection_end_utc,
                    segment_end_local=detection_end_local,
                    timezone=metadata['timezone'],
                    scientific_name=names['scientific'],
                    name_en=names['en'],
                    name_de=names['de'],
                    name_cs=names['cs'],
                    confidence=detection['confidence']
                )
            
            # Send progress update (one per file)
            result_queue.put({
                'worker_id': worker_id,
                'filename': metadata['filename'],
                'num_detections': len(detections)
            })
            
        except Exception as e:
            logger.error(
                f"Worker {worker_id} error processing {metadata['filename']}: {e}"
            )
            # Send progress update even on error
            result_queue.put({
                'worker_id': worker_id,
                'filename': metadata['filename'],
                'num_detections': 0,
                'error': str(e)
            })
    
    logger.info(f"Worker {worker_id} finished")