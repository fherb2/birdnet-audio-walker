"""
SQLite database management for BirdNET Batch Analyzer.
"""

import sqlite3
import fcntl
from pathlib import Path
from datetime import datetime
from loguru import logger
import pandas as pd
from pyexcel_ods3 import save_data
from collections import OrderedDict


def init_database(db_path: str):
    """
    Initialize SQLite database with schema.
    
    Args:
        db_path: Path to SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
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
    
    # Detections table
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
    
    # Indices for faster queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_detections_time ON detections(segment_start_local)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_detections_species ON detections(scientific_name)")
    
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


def insert_detection(
    db_path: str,
    filename: str,
    segment_start_utc: datetime,
    segment_start_local: datetime,
    segment_end_utc: datetime,
    segment_end_local: datetime,
    timezone: str,
    scientific_name: str,
    name_en: str,
    name_de: str,
    name_cs: str,
    confidence: float
):
    """
    Insert detection into database with file locking.
    
    Args:
        db_path: Path to SQLite database
        filename: Original WAV filename
        segment_start_utc: Segment start time (UTC)
        segment_start_local: Segment start time (local)
        segment_end_utc: Segment end time (UTC)
        segment_end_local: Segment end time (local)
        timezone: Timezone string ('MEZ' or 'MESZ')
        scientific_name: Scientific species name
        name_en: English name
        name_de: German name
        name_cs: Czech name
        confidence: Confidence score
    """
    # Open database file for locking (create if doesn't exist)
    db_file = open(db_path, 'a+b')
    
    try:
        # Acquire exclusive lock
        fcntl.flock(db_file.fileno(), fcntl.LOCK_EX)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO detections 
            (filename, segment_start_utc, segment_start_local, 
             segment_end_utc, segment_end_local, timezone,
             scientific_name, name_en, name_de, name_cs, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            filename,
            segment_start_utc.isoformat(),
            segment_start_local.isoformat(),
            segment_end_utc.isoformat(),
            segment_end_local.isoformat(),
            timezone,
            scientific_name,
            name_en,
            name_de,
            name_cs,
            confidence
        ))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error inserting detection: {e}")
    finally:
        # Release lock
        fcntl.flock(db_file.fileno(), fcntl.LOCK_UN)
        db_file.close()


def export_to_ods(db_path: str, output_path: str):
    """
    Export SQLite data to ODS file with two sheets.
    
    Args:
        db_path: Path to SQLite database
        output_path: Path to output ODS file
    """
    logger.info(f"Exporting database to ODS: {output_path}")
    
    conn = sqlite3.connect(db_path)
    
    # Load detections (sorted by time)
    detections_df = pd.read_sql_query("""
        SELECT 
            filename as "Dateiname",
            segment_start_utc as "Segment Start (UTC)",
            segment_start_local as "Segment Start (Lokal)",
            segment_end_utc as "Segment Ende (UTC)",
            segment_end_local as "Segment Ende (Lokal)",
            timezone as "Zeitzone",
            scientific_name as "Wissenschaftlicher Name",
            name_en as "Englischer Name",
            name_de as "Deutscher Name",
            name_cs as "Tschechischer Name",
            confidence as "Konfidenz"
        FROM detections
        ORDER BY segment_start_local
    """, conn)
    
    # Load metadata
    metadata_df = pd.read_sql_query("""
        SELECT 
            filename as "Dateiname",
            timestamp_utc as "Zeitstempel (UTC)",
            timestamp_local as "Zeitstempel (Lokal)",
            timezone as "Zeitzone",
            serial as "Geräte-ID",
            gps_lat as "GPS Latitude",
            gps_lon as "GPS Longitude",
            sample_rate as "Sample Rate",
            channels as "Kanäle",
            bit_depth as "Bit-Tiefe",
            duration_seconds as "Dauer",
            temperature_c as "Temperatur",
            battery_voltage as "Batteriespannung",
            gain as "Verstärkung",
            firmware as "Firmware"
        FROM metadata
        ORDER BY timestamp_local
    """, conn)
    
    conn.close()
    
    # Replace None with empty string (pyexcel-ods3 can't handle None)
    detections_df = detections_df.fillna('')
    metadata_df = metadata_df.fillna('')

    # Convert DataFrames to list of lists for pyexcel-ods3
    detections_data = [detections_df.columns.tolist()] + detections_df.values.tolist()
    metadata_data = [metadata_df.columns.tolist()] + metadata_df.values.tolist()

    # Create ODS with two sheets
    data = OrderedDict()
    data["Detektionen"] = detections_data
    data["Metadaten"] = metadata_data

    save_data(output_path, data)
    
    logger.info(f"Export complete: {len(detections_df)} detections, {len(metadata_df)} files")