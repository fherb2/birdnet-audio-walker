"""
Database query functions for BirdNET tools.
Read-only access to analysis databases.
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime, time
from loguru import logger


def get_db_connection(db_path: Path) -> sqlite3.Connection:
    """
    Open database connection with WAL mode.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        SQLite connection with Row factory for dict-like access
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def get_analysis_config(db_path: Path, key: str) -> Optional[str]:
    """
    Read value from analysis_config table.
    
    Args:
        db_path: Path to SQLite database
        key: Config key to read
        
    Returns:
        Config value or None if not found
    """
    conn = get_db_connection(db_path)
    
    try:
        cursor = conn.execute(
            "SELECT value FROM analysis_config WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        return row['value'] if row else None
    except sqlite3.OperationalError:
        # Table doesn't exist (old database)
        logger.warning(f"analysis_config table not found in {db_path}")
        return None
    finally:
        conn.close()


def get_detection_by_id(db_path: Path, detection_id: int) -> Optional[Dict]:
    """
    Load single detection with all metadata.
    
    Args:
        db_path: Path to SQLite database
        detection_id: Detection ID
        
    Returns:
        Dict with detection + metadata or None if not found
    """
    conn = get_db_connection(db_path)
    
    try:
        cursor = conn.execute("""
            SELECT 
                d.id as detection_id,
                d.filename,
                d.segment_start_utc,
                d.segment_end_utc,
                d.segment_start_local,
                d.segment_end_local,
                d.timezone,
                d.scientific_name,
                d.local_name,
                d.name_cs,
                d.confidence,
                m.timestamp_utc as file_timestamp_utc,
                m.timestamp_local as file_timestamp_local,
                m.duration_seconds as file_duration_seconds,
                m.gps_lat,
                m.gps_lon,
                m.sample_rate,
                m.channels
            FROM detections d
            JOIN metadata m ON d.filename = m.filename
            WHERE d.id = ?
        """, (detection_id,))
        
        row = cursor.fetchone()
        return dict(row) if row else None
        
    finally:
        conn.close()


def get_metadata_by_filename(db_path: Path, filename: str) -> Optional[Dict]:
    """
    Load file metadata.
    
    Args:
        db_path: Path to SQLite database
        filename: WAV filename
        
    Returns:
        Dict with metadata or None if not found
    """
    conn = get_db_connection(db_path)
    
    try:
        cursor = conn.execute("""
            SELECT * FROM metadata WHERE filename = ?
        """, (filename,))
        
        row = cursor.fetchone()
        return dict(row) if row else None
        
    finally:
        conn.close()


def query_detections(
    db_path: Path,
    species: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    time_range: Optional[Tuple[time, time]] = None,
    min_confidence: Optional[float] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Dict]:
    """
    Query detections with filters.
    
    Args:
        db_path: Path to SQLite database
        species: Species name (scientific, local, or Czech) - partial match
        date_from: Start date (inclusive)
        date_to: End date (inclusive)
        time_range: Tuple of (start_time, end_time) for time of day filter
        min_confidence: Minimum confidence threshold
        limit: Maximum number of results
        offset: Result offset for pagination
        
    Returns:
        List of detection dicts with metadata
    """
    conn = get_db_connection(db_path)
    
    try:
        # Build query
        query = """
            SELECT 
                d.id as detection_id,
                d.filename,
                d.segment_start_utc,
                d.segment_end_utc,
                d.segment_start_local,
                d.segment_end_local,
                d.timezone,
                d.scientific_name,
                d.local_name,
                d.name_cs,
                d.confidence,
                m.timestamp_utc as file_timestamp_utc,
                m.timestamp_local as file_timestamp_local,
                m.duration_seconds as file_duration_seconds,
                m.gps_lat,
                m.gps_lon,
                m.sample_rate,
                m.channels
            FROM detections d
            JOIN metadata m ON d.filename = m.filename
            WHERE 1=1
        """
        
        params = []
        
        # Species filter (match scientific OR local OR Czech name)
        if species:
            query += " AND (d.scientific_name LIKE ? OR d.local_name LIKE ? OR d.name_cs LIKE ?)"
            pattern = f"%{species}%"
            params.extend([pattern, pattern, pattern])
        
        # Date filters
        if date_from:
            query += " AND date(d.segment_start_local) >= date(?)"
            params.append(date_from.isoformat())
        
        if date_to:
            query += " AND date(d.segment_start_local) <= date(?)"
            params.append(date_to.isoformat())
        
        # Time of day filter
        if time_range:
            start_time, end_time = time_range
            query += " AND time(d.segment_start_local) BETWEEN time(?) AND time(?)"
            params.append(start_time.isoformat())
            params.append(end_time.isoformat())
        
        # Confidence filter
        if min_confidence is not None:
            query += " AND d.confidence >= ?"
            params.append(min_confidence)
        
        # Sorting
        query += " ORDER BY d.segment_start_local ASC"
        
        # Limit and offset
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        # Execute query
        cursor = conn.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        
        logger.debug(f"Query returned {len(results)} detections")
        return results
        
    finally:
        conn.close()
