"""
SQLite database management for BirdNET Batch Analyzer.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
import pandas as pd

from species_translation import translate_species_name


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
            name_en TEXT,
            name_de TEXT,
            name_cs TEXT,
            confidence REAL NOT NULL,
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
    translation_table: pd.DataFrame
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
                translation_table
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
                 scientific_name, name_en, name_de, name_cs, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filename,
                detection_start_utc.isoformat(),
                detection_start_local.isoformat(),
                detection_end_utc.isoformat(),
                detection_end_local.isoformat(),
                metadata['timezone'],
                names['scientific'],
                names['en'],
                names['de'],
                names['cs'],
                detection['confidence']
            ))
        
        # Commit transaction
        conn.commit()
        logger.debug(f"Batch inserted {len(detections)} detections for {filename}")
        
    except Exception as e:
        logger.error(f"Error batch inserting detections for {filename}: {e}")
        conn.rollback()
    finally:
        conn.close()


def db_writer_process(
    result_queue,
    db_path: str,
    translation_table: pd.DataFrame
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
                translation_table
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
        # Index for time-based queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_detections_time 
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