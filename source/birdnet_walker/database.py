"""
SQLite database management for BirdNET Batch Analyzer.
"""

import sqlite3
from datetime import datetime, timedelta
from loguru import logger
import pandas as pd

from .species_translation import translate_species_name


def init_database(db_path: str):
    """
    Initialize SQLite database with schema.
    
    Args:
        db_path: Path to SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Enable WAL mode for better concurrency
    cursor.execute("PRAGMA journal_mode=WAL")
    
    # Metadata table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            id INTEGER PRIMARY KEY,
            filename TEXT NOT NULL UNIQUE,
            timestamp_utc TEXT NOT NULL,
            timestamp_local TEXT NOT NULL,
            timezone TEXT NOT NULL,
            serial TEXT,
            gps_lat REAL,
            gps_lon REAL,
            sample_rate INTEGER,
            channels INTEGER,
            bit_depth INTEGER,
            duration_seconds REAL,
            temperature_c REAL,
            battery_voltage REAL,
            gain TEXT,
            firmware TEXT
        )
    """)
    
    # Detections table (indices created later for performance)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            segment_start_utc TEXT NOT NULL,
            segment_start_local TEXT NOT NULL,
            segment_end_utc TEXT NOT NULL,
            segment_end_local TEXT NOT NULL,
            timezone TEXT NOT NULL,
            scientific_name TEXT NOT NULL,
            local_name TEXT,
            name_cs TEXT,
            confidence REAL NOT NULL,
            FOREIGN KEY (filename) REFERENCES metadata(filename)
        )
    """)

        # Processing status tracking table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_status (
            filename TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            error_message TEXT,
            FOREIGN KEY (filename) REFERENCES metadata(filename)
        )
    """)

    conn.commit()
    conn.close()
    logger.info(f"Database initialized: {db_path}")


def insert_metadata(db_path: str, metadata: dict):
    """
    Insert file metadata into database.
    
    Args:
        db_path: Path to SQLite database
        metadata: Metadata dictionary from audiomoth_import
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO metadata 
            (filename, timestamp_utc, timestamp_local, timezone, serial, 
             gps_lat, gps_lon, sample_rate, channels, bit_depth, 
             duration_seconds, temperature_c, battery_voltage, gain, firmware)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            metadata['filename'],
            metadata['timestamp_utc'].isoformat(),
            metadata['timestamp_local'].isoformat(),
            metadata['timezone'],
            metadata.get('serial'),
            metadata.get('gps_lat'),
            metadata.get('gps_lon'),
            metadata.get('sample_rate'),
            metadata.get('channels'),
            metadata.get('bit_depth'),
            metadata.get('duration_seconds'),
            metadata.get('temperature_c'),
            metadata.get('battery_voltage'),
            metadata.get('gain'),
            metadata.get('firmware')
        ))
        # Set initial processing status to pending
        cursor.execute("""
            INSERT OR IGNORE INTO processing_status (filename, status)
            VALUES (?, 'pending')
        """, (metadata['filename'],))
        
        conn.commit()
        logger.debug(f"Metadata inserted for {metadata['filename']}")
    except Exception as e:
        logger.error(f"Error inserting metadata for {metadata['filename']}: {e}")
        conn.rollback()
    finally:
        conn.close()


def batch_insert_detections(
    db_path: str,
    filename: str,
    metadata: dict,
    detections: list[dict],
    translation_table: pd.DataFrame,
    birdnet_labels: dict
):
    """
    Insert all detections from one file in a single transaction.
    
    Args:
        db_path: Path to SQLite database
        filename: Original WAV filename
        metadata: File metadata dict
        detections: List of detection dicts from BirdNET
        translation_table: Species translation table
    """
    if not detections:
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Start transaction
        cursor.execute("BEGIN TRANSACTION")
        
        for detection in detections:
            # Translate species names
            names = translate_species_name(
                detection['scientific_name'],
                translation_table,
                birdnet_labels
            )
            
            # Calculate absolute timestamps from detection times
            detection_start_seconds = detection['start_time']
            detection_end_seconds = detection['end_time']
            
            detection_start_utc = metadata['timestamp_utc'] + timedelta(seconds=detection_start_seconds)
            detection_end_utc = metadata['timestamp_utc'] + timedelta(seconds=detection_end_seconds)
            detection_start_local = metadata['timestamp_local'] + timedelta(seconds=detection_start_seconds)
            detection_end_local = metadata['timestamp_local'] + timedelta(seconds=detection_end_seconds)
            
            # Insert detection
            cursor.execute("""
                INSERT INTO detections 
                (filename, segment_start_utc, segment_start_local, 
                 segment_end_utc, segment_end_local, timezone,
                 scientific_name, local_name, name_cs, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filename,
                detection_start_utc.isoformat(),
                detection_start_local.isoformat(),
                detection_end_utc.isoformat(),
                detection_end_local.isoformat(),
                metadata['timezone'],
                names['scientific'],
                names['local'],
                names['cs'],
                detection['confidence']
            ))
        
        # Commit transaction
        conn.commit()
        
        # Mark file as completed
        cursor.execute("""
            UPDATE processing_status 
            SET status = 'completed', completed_at = ?
            WHERE filename = ?
        """, (datetime.now().isoformat(), filename))

        logger.debug(f"Batch inserted {len(detections)} detections for {filename}")
        
    except Exception as e:
        logger.error(f"Error batch inserting detections for {filename}: {e}")
        conn.rollback()
    finally:
        conn.close()


def db_writer_process(
    result_queue,
    db_path: str,
    translation_table: pd.DataFrame,
    birdnet_labels: dict
):
    """
    DB writer process - reads from queue and writes to database.
    
    Args:
        result_queue: Multiprocessing queue with detection data
        db_path: Path to SQLite database
        translation_table: Species translation table
    """
    worker_id = "DB-Writer"
    logger.info(f"{worker_id} started")
    
    files_processed = 0
    
    try:
        while True:
            # Blocking get from queue
            data_package = result_queue.get()
            
            # Check for poison pill (None = shutdown signal)
            if data_package is None:
                logger.info(f"{worker_id} received shutdown signal")
                break
            
            # Extract data
            filename = data_package['filename']
            metadata = data_package['metadata']
            detections = data_package['detections']
            
            # Batch insert all detections from this file
            batch_insert_detections(
                db_path,
                filename,
                metadata,
                detections,
                translation_table,
                birdnet_labels
            )
            
            files_processed += 1
            
    except Exception as e:
        logger.error(f"{worker_id} error: {e}")
    finally:
        logger.info(f"{worker_id} finished - processed {files_processed} files")


def create_indices(db_path: str):
    """
    Create database indices after all inserts are complete.
    
    This is much faster than maintaining indices during inserts.
    
    Args:
        db_path: Path to SQLite database
    """
    logger.info("Creating database indices...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Index for time-based queries (segment start times)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_detections_segment_start
            ON detections(segment_start_local)
        """)
        
        # Index for species-based queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_detections_species 
            ON detections(scientific_name)
        """)
        
        # Index for filename-based queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_detections_filename 
            ON detections(filename)
        """)
        
        conn.commit()
        logger.info("Database indices created ✓")
        
    except Exception as e:
        logger.error(f"Error creating indices: {e}")
    finally:
        conn.close()


def set_file_status(
    db_path: str,
    filename: str,
    status: str,
    error_message: str = None
):
    """
    Set processing status for a file.
    
    Args:
        db_path: Path to SQLite database
        filename: Filename to update
        status: One of 'pending', 'processing', 'completed', 'failed'
        error_message: Optional error message for 'failed' status
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        now = datetime.now().isoformat()
        
        if status == 'processing':
            cursor.execute("""
                INSERT OR REPLACE INTO processing_status 
                (filename, status, started_at, completed_at, error_message)
                VALUES (?, ?, ?, NULL, NULL)
            """, (filename, status, now))
        elif status == 'completed':
            cursor.execute("""
                UPDATE processing_status 
                SET status = ?, completed_at = ?
                WHERE filename = ?
            """, (status, now, filename))
        elif status == 'failed':
            cursor.execute("""
                UPDATE processing_status 
                SET status = ?, error_message = ?
                WHERE filename = ?
            """, (status, error_message, filename))
        else:  # 'pending'
            cursor.execute("""
                INSERT OR REPLACE INTO processing_status 
                (filename, status, started_at, completed_at, error_message)
                VALUES (?, ?, NULL, NULL, NULL)
            """, (filename, status))
        
        conn.commit()
    except Exception as e:
        logger.error(f"Error setting status for {filename}: {e}")
        conn.rollback()
    finally:
        conn.close()


def cleanup_incomplete_files(db_path: str):
    """
    Cleanup incomplete file processing:
    - Delete detections from files that were 'processing' but not completed
    - Reset their status to 'pending'
    
    Args:
        db_path: Path to SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Find files that were being processed but not completed
        # Note: 'pending' files were never started, so no cleanup needed
        cursor.execute("""
            SELECT filename FROM processing_status
            WHERE status IN ('processing', 'failed')
        """)
        
        incomplete_files = [row[0] for row in cursor.fetchall()]
        
        if incomplete_files:
            logger.info(f"Found {len(incomplete_files)} incomplete files, cleaning up...")
            
            for filename in incomplete_files:
                # Delete detections
                cursor.execute("""
                    DELETE FROM detections WHERE filename = ?
                """, (filename,))
                
                # Reset status to pending
                cursor.execute("""
                    UPDATE processing_status 
                    SET status = 'pending', started_at = NULL, 
                        completed_at = NULL, error_message = NULL
                    WHERE filename = ?
                """, (filename,))
                
                logger.debug(f"Cleaned up incomplete file: {filename}")
            
            conn.commit()
            logger.info(f"Cleanup complete: {len(incomplete_files)} files reset to pending")
            
            # Vacuum to reclaim space
            vacuum_database(db_path)
        else:
            logger.info("No incomplete files found, no cleanup needed")
            
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        conn.rollback()
    finally:
        conn.close()


def repair_orphaned_metadata(db_path: str):
    """
    Find files in metadata that are missing from processing_status and add them.
    
    This can happen if the program was interrupted during insert_metadata().
    
    Args:
        db_path: Path to SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Find files in metadata but not in processing_status
        cursor.execute("""
            SELECT filename FROM metadata
            WHERE filename NOT IN (SELECT filename FROM processing_status)
        """)
        
        orphaned = [row[0] for row in cursor.fetchall()]
        
        if orphaned:
            logger.warning(f"Found {len(orphaned)} files in metadata without processing status, repairing...")
            
            for filename in orphaned:
                cursor.execute("""
                    INSERT INTO processing_status (filename, status)
                    VALUES (?, 'pending')
                """, (filename,))
            
            conn.commit()
            logger.info(f"Repaired {len(orphaned)} orphaned files")
        
    except Exception as e:
        logger.error(f"Error repairing orphaned metadata: {e}")
        conn.rollback()
    finally:
        conn.close()

def get_completed_files(db_path: str) -> set[str]:
    """
    Get set of filenames that have been successfully processed.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        Set of filenames with status 'completed'
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT filename FROM processing_status
            WHERE status = 'completed'
        """)
        
        completed = {row[0] for row in cursor.fetchall()}
        logger.info(f"Found {len(completed)} already completed files")
        return completed
        
    except Exception as e:
        logger.error(f"Error getting completed files: {e}")
        return set()
    finally:
        conn.close()


def check_indices_exist(db_path: str) -> bool:
    """
    Check if any of the indices exist.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        True if any index exists, False otherwise
    """
    from config import INDEX_NAMES
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        for index_name in INDEX_NAMES:
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name=?
            """, (index_name,))
            
            if cursor.fetchone() is not None:
                return True
        
        return False
        
    finally:
        conn.close()


def drop_all_indices(db_path: str):
    """
    Drop all custom indices.
    
    Args:
        db_path: Path to SQLite database
    """
    from config import INDEX_NAMES
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        for index_name in INDEX_NAMES:
            cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
            logger.debug(f"Dropped index: {index_name}")
        
        conn.commit()
        logger.info("All indices dropped")
        
        # Vacuum to reclaim space after dropping indices
        conn.close()  # Close connection before vacuum
        vacuum_database(db_path)
        return  # Return early to skip the finally close
        
    except Exception as e:
        logger.error(f"Error dropping indices: {e}")
    finally:
        conn.close()




def get_missing_files(db_path: str, wav_files: list[str]) -> list[str]:
    """
    Get list of WAV files that are not yet in the database.
    
    Args:
        db_path: Path to SQLite database
        wav_files: List of WAV filenames in the folder
        
    Returns:
        List of filenames not yet in database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get all filenames in metadata table
        cursor.execute("SELECT filename FROM metadata")
        existing_files = {row[0] for row in cursor.fetchall()}
        
        # Find missing files
        missing = [f for f in wav_files if f not in existing_files]
        
        if missing:
            logger.info(f"Found {len(missing)} new files not yet in database")
        
        return missing
        
    finally:
        conn.close()
        

def vacuum_database(db_path: str):
    """
    Vacuum database to reclaim space after deletions.
    
    Args:
        db_path: Path to SQLite database
    """
    logger.info("Vacuuming database to reclaim space...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("VACUUM")
        conn.commit()
        logger.info("Database vacuumed ✓")
        
    except Exception as e:
        logger.error(f"Error vacuuming database: {e}")
    finally:
        conn.close()